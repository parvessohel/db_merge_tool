# DB Merge Tool — Deep Architecture & Developer Notes

Purpose: deeper design, invariants, data flows, known gaps, and actionable TODOs to make the repo production-ready.

---

## High-level goals & invariants
- Produce a single destination DB containing all rows from N source DBs.
- Preserve referential integrity by remapping PKs and all referencing FKs.
- Maintain durable source→destination mapping (persistent and in-memory) so merges can be resumed and verified.
- Skip/ignore configured tables and treat certain FK columns as static (no remap).

---

## Key components & responsibilities (concise)
- connection.py: create pyodbc connections.
- schema_cloner.py: create destination table schemas (currently incomplete for constraints/indexes).
- mapping_table.py: persistent mapping table helpers; create/insert/lookup mappings (some methods unimplemented).
- value_mapping.py: in-memory dict cache for source→mapped values during run.
- inserter.py: core merge algorithm: table ordering, row iteration, FK resolution, inserts, mapping writes.
- main.py / main.ui.py: orchestration and CLI/GUI UX.
- ignore_tables.json: user config for ignore/static-FK behavior.

---

## Mapping table (persistent store)
Schema (current file uses this create SQL):
- source_db_name NVARCHAR(255)
- source_table_name NVARCHAR(255)
- source_pk_column NVARCHAR(255)
- source_pk_value BIGINT
- mapped_db_name NVARCHAR(255)
- mapped_table_name NVARCHAR(255)
- mapped_pk_column NVARCHAR(255)
- mapped_pk_value BIGINT
- created_at DATETIME DEFAULT GETDATE()

Recommendations:
- Add a unique index on (source_db_name, source_table_name, source_pk_column, source_pk_value) to prevent duplicates.
- Add an index on (mapped_table_name, mapped_pk_value) to speed lookups.
- Use appropriate types if non-BIGINT PKs may exist (support GUIDs/text).

Example lookup SQL:
```sql
SELECT mapped_pk_value
FROM primary_key_mapping_table
WHERE source_db_name = ?
  AND source_table_name = ?
  AND source_pk_value = ?
```

Insert mapping after successful insert to destination (atomic if possible).

---

## In-memory mapping (value_mapping.py)
- Meant as a fast cache. Keyed by (source_db, source_table, source_pk).
- Must be populated by:
  - reading existing mappings at start for all source DBs (to allow resuming)
  - writing new mappings as inserts occur

Recommendation: on importer start, load mapping_table rows relevant to the run into value_mapping.pk_mapping.

---

## clone_schema — detailed expectations & current gaps
Expected responsibilities:
- Recreate tables and columns (datatype, nullability, lengths)
- Mark IDENTITY columns and allow identity inserts temporarily when seeding
- Recreate PK constraints (PRIMARY KEY), FK constraints (optionally), indexes (optional)
- Skip mapping table and ignored tables

Gaps in current implementation:
- column_defs assembly is incomplete
- PK extraction present but not applied to CREATE TABLE
- No schema/namespace handling, no FK recreation or index cloning

Actionable: implement assembly building steps:
- For each column: include [name] [datatype](length) NULL/NOT NULL, IDENTITY(1,1) if identity.
- After columns, define PRIMARY KEY ([col1, col2]) in CREATE TABLE or add constraint via ALTER TABLE.
- Consider deferring FK recreation until after data is inserted or recreate with check constraint NOCHECK then re-enable.

---

## insert_database — algorithm & details

1. Load ignore config: ignore_tables, static_foreign_keys.
2. List tables: all base tables except mapping table and ignore_tables.
3. Determine table order:
   - Best: build a directed graph where edge A→B exists if A depends on B (A has FK to B). Topologically sort.
   - Fallback: sort by number of FKs ascending (parents first).
4. For each table T in order:
   - Retrieve PK column and identity column (if any).
   - Retrieve FK metadata: for each FK column, the referenced table and referenced column.
   - For each row R in source table:
     - For each FK column:
       - If column in static_foreign_keys[T], leave value as-is.
       - Else if FK value is NULL, leave NULL.
       - Else lookup mapped_id = get_mapped_id(source_db, ref_table, fk_value) via:
         - in-memory cache
         - mapping_table DB lookup if cache miss
         - If still missing -> policy: error / skip / queue for later (choose configurable behavior).
     - Determine new PK value:
       - If PK column is identity:
         - Insert row with SET IDENTITY_INSERT ON (preserve source ID) only if destination doesn't have conflict and you want to keep IDs;
         - OR insert letting destination generate a new ID via OUTPUT inserted.[pk]
       - If non-identity PK: compute new PK if conflict, else reuse.
     - Insert row into destination via parameterized query and capture mapped_pk_value.
     - Persist mapping: mapping_table.insert_mapping(...) and value_mapping.add_mapping(...)
5. Commit periodically (per-table or per-batch). Prefer larger transactions for performance but small for recoverability.

Notes:
- Use parameterized prepared statements for performance.
- Use OUTPUT INSERTED.[pk] to capture auto-generated PK values.

---

## Foreign key metadata SQL (helper)
Get FK information for a table (columns, referenced_table, referenced_column):

```sql
SELECT fk.name AS fk_name,
       pc.name AS fk_column,
       rc.name AS referenced_column,
       rt.name AS referenced_table
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables pt ON fk.parent_object_id = pt.object_id
JOIN sys.columns pc ON fkc.parent_column_id = pc.column_id AND pc.object_id = pt.object_id
JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
JOIN sys.columns rc ON fkc.referenced_column_id = rc.column_id AND rc.object_id = rt.object_id
WHERE pt.name = ?
```

Implement get_foreign_keys(cursor, table) in inserter.py to return list of dicts describing each FK.

---

## Ordering algorithm (table dependency graph)
- Build graph nodes = tables; edges from child -> parent (child depends on parent).
- Topological sort; detect cycles:
  - If cycles exist, handle by:
    - Temporarily disable FK checks (INSERT with constraints NOCHECK)
    - Insert data in any order and re-enable constraints with CHECK (and verify)
- If graph building not possible, fallback to heuristic: tables sorted by number of FKs ascending.

---

## Transactions, retries & error handling
- Transactions: group per-table or per-batch; use try/except to rollback on failure.
- Retries: transient DB errors should be retried with backoff.
- Missing mapping policy:
  - default: raise and stop (safer)
  - alternative flags: --skip-unresolvable (skip offending rows), --defer (queue rows to insert after parents)
- Logs: add structured logging (info/warn/error) rather than prints.
- Ensure connections/cursors are closed in finally blocks.

---

## Concurrency & resumability
- Persist mapping_table after each inserted row (or batch) to allow resumption.
- Before starting a source DB run, load mapping rows to in-memory cache.
- Consider using a run id column in mapping table to track which run inserted which mapping.

---

## Security & configuration
- Avoid plaintext credentials in repo. Current approach uses Trusted Connection; for SQL auth, use environment variables or secure store.
- Add CLI flags or env vars for server and credentials.
- Consider allowing JSON config override for ignore tables and static FK settings.

---

## Testing suggestions
- Unit tests:
  - get_primary_key, get_identity_column, get_foreign_keys
  - mapping_table.insert_mapping/get_mapped_id
  - value_mapping add/get behavior
- Integration tests:
  - Use local SQL Server (Docker mssql) with small schema examples:
    - Parent/child relations, identity PKs, composite PKs, nullable FKs, static FK columns
  - End-to-end: create two small source DBs, run tool into a dest DB, validate FK integrity and mapping table contents.
- Add tests/fixtures and CI (GitHub Actions) with a lightweight DB emulator or dockerized mssql for integration.

---

## Performance improvements
- Batch inserts instead of per-row inserts where possible.
- Bulk lookup of mappings for sets of FK values to reduce DB round-trips.
- Use prepared statements and transactions for batches.
- Add progress metrics/logging.

---

## Known gaps & TODOs (actionable)
- [ ] Implement complete column SQL generation & PK/constraint creation in schema_cloner.py.
- [ ] Implement get_foreign_keys(cursor, table) in inserter.py.
- [ ] Implement lookup_mapped_id(cursor, source_db, table, old_id) and mapping_table.get_mapped_id & get_new_id.
- [ ] Add unique index on mapping table to avoid dupes.
- [ ] Add initial load of mapping table into in-memory cache for resumable runs.
- [ ] Add CLI flags (argparse) for non-interactive runs, skip/continue policies, verbose logging.
- [ ] Add unit and integration tests.
- [ ] Centralize DB creation and existence checks into db_utils.py and use it in main.py.
- [ ] Add structured logging and exception handling across modules.

---

## Example helper implementations (sketches)

get_mapped_id (mapping_table.py) sketch:
```python
def get_mapped_id(server, db_name, source_table, source_id):
    conn = get_connection(server, db_name)
    cur = conn.cursor()
    cur.execute("""SELECT mapped_pk_value FROM primary_key_mapping_table
                   WHERE source_table_name=? AND source_pk_value=?""",
                source_table, source_id)
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
```

get_foreign_keys (inserter.py) sketch:
```python
def get_foreign_keys(cursor, table):
    cursor.execute("<FK metadata SQL from this doc>", table)
    return [
       {"fk_column": r[1], "referenced_table": r[3], "referenced_column": r[2]}
       for r in cursor.fetchall()
    ]
```

---

## Developer workflow recommendations
- Add a `DEV.md` with local docker-based SQL Server setup and sample seed scripts.
- Add linters and pre-commit hooks (flake8/black).
- Use small incremental PRs for each TODO.

---

If you'd like, I can:
- Create docs/ARCHITECTURE-DEEP.md in the repo with this content.
- Implement any of the TODO functions (e.g., get_foreign_keys, mapping lookups) with tests.

Which task should I do next?// filepath: g:\Nextech\Projects\db_merge_tool\docs\ARCHITECTURE-DEEP.md
# DB Merge Tool — Deep Architecture & Developer Notes

Purpose: deeper design, invariants, data flows, known gaps, and actionable TODOs to make the repo production-ready.

---

## High-level goals & invariants
- Produce a single destination DB containing all rows from N source DBs.
- Preserve referential integrity by remapping PKs and all referencing FKs.
- Maintain durable source→destination mapping (persistent and in-memory) so merges can be resumed and verified.
- Skip/ignore configured tables and treat certain FK columns as static (no remap).

---

## Key components & responsibilities (concise)
- connection.py: create pyodbc connections.
- schema_cloner.py: create destination table schemas (currently incomplete for constraints/indexes).
- mapping_table.py: persistent mapping table helpers; create/insert/lookup mappings (some methods unimplemented).
- value_mapping.py: in-memory dict cache for source→mapped values during run.
- inserter.py: core merge algorithm: table ordering, row iteration, FK resolution, inserts, mapping writes.
- main.py / main.ui.py: orchestration and CLI/GUI UX.
- ignore_tables.json: user config for ignore/static-FK behavior.

---

## Mapping table (persistent store)
Schema (current file uses this create SQL):
- source_db_name NVARCHAR(255)
- source_table_name NVARCHAR(255)
- source_pk_column NVARCHAR(255)
- source_pk_value BIGINT
- mapped_db_name NVARCHAR(255)
- mapped_table_name NVARCHAR(255)
- mapped_pk_column NVARCHAR(255)
- mapped_pk_value BIGINT
- created_at DATETIME DEFAULT GETDATE()

Recommendations:
- Add a unique index on (source_db_name, source_table_name, source_pk_column, source_pk_value) to prevent duplicates.
- Add an index on (mapped_table_name, mapped_pk_value) to speed lookups.
- Use appropriate types if non-BIGINT PKs may exist (support GUIDs/text).

Example lookup SQL:
```sql
SELECT mapped_pk_value
FROM primary_key_mapping_table
WHERE source_db_name = ?
  AND source_table_name = ?
  AND source_pk_value = ?
```

Insert mapping after successful insert to destination (atomic if possible).

---

## In-memory mapping (value_mapping.py)
- Meant as a fast cache. Keyed by (source_db, source_table, source_pk).
- Must be populated by:
  - reading existing mappings at start for all source DBs (to allow resuming)
  - writing new mappings as inserts occur

Recommendation: on importer start, load mapping_table rows relevant to the run into value_mapping.pk_mapping.

---

## clone_schema — detailed expectations & current gaps
Expected responsibilities:
- Recreate tables and columns (datatype, nullability, lengths)
- Mark IDENTITY columns and allow identity inserts temporarily when seeding
- Recreate PK constraints (PRIMARY KEY), FK constraints (optionally), indexes (optional)
- Skip mapping table and ignored tables

Gaps in current implementation:
- column_defs assembly is incomplete
- PK extraction present but not applied to CREATE TABLE
- No schema/namespace handling, no FK recreation or index cloning

Actionable: implement assembly building steps:
- For each column: include [name] [datatype](length) NULL/NOT NULL, IDENTITY(1,1) if identity.
- After columns, define PRIMARY KEY ([col1, col2]) in CREATE TABLE or add constraint via ALTER TABLE.
- Consider deferring FK recreation until after data is inserted or recreate with check constraint NOCHECK then re-enable.

---

## insert_database — algorithm & details

1. Load ignore config: ignore_tables, static_foreign_keys.
2. List tables: all base tables except mapping table and ignore_tables.
3. Determine table order:
   - Best: build a directed graph where edge A→B exists if A depends on B (A has FK to B). Topologically sort.
   - Fallback: sort by number of FKs ascending (parents first).
4. For each table T in order:
   - Retrieve PK column and identity column (if any).
   - Retrieve FK metadata: for each FK column, the referenced table and referenced column.
   - For each row R in source table:
     - For each FK column:
       - If column in static_foreign_keys[T], leave value as-is.
       - Else if FK value is NULL, leave NULL.
       - Else lookup mapped_id = get_mapped_id(source_db, ref_table, fk_value) via:
         - in-memory cache
         - mapping_table DB lookup if cache miss
         - If still missing -> policy: error / skip / queue for later (choose configurable behavior).
     - Determine new PK value:
       - If PK column is identity:
         - Insert row with SET IDENTITY_INSERT ON (preserve source ID) only if destination doesn't have conflict and you want to keep IDs;
         - OR insert letting destination generate a new ID via OUTPUT inserted.[pk]
       - If non-identity PK: compute new PK if conflict, else reuse.
     - Insert row into destination via parameterized query and capture mapped_pk_value.
     - Persist mapping: mapping_table.insert_mapping(...) and value_mapping.add_mapping(...)
5. Commit periodically (per-table or per-batch). Prefer larger transactions for performance but small for recoverability.

Notes:
- Use parameterized prepared statements for performance.
- Use OUTPUT INSERTED.[pk] to capture auto-generated PK values.

---

## Foreign key metadata SQL (helper)
Get FK information for a table (columns, referenced_table, referenced_column):

```sql
SELECT fk.name AS fk_name,
       pc.name AS fk_column,
       rc.name AS referenced_column,
       rt.name AS referenced_table
FROM sys.foreign_keys fk
JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
JOIN sys.tables pt ON fk.parent_object_id = pt.object_id
JOIN sys.columns pc ON fkc.parent_column_id = pc.column_id AND pc.object_id = pt.object_id
JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
JOIN sys.columns rc ON fkc.referenced_column_id = rc.column_id AND rc.object_id = rt.object_id
WHERE pt.name = ?
```

Implement get_foreign_keys(cursor, table) in inserter.py to return list of dicts describing each FK.

---

## Ordering algorithm (table dependency graph)
- Build graph nodes = tables; edges from child -> parent (child depends on parent).
- Topological sort; detect cycles:
  - If cycles exist, handle by:
    - Temporarily disable FK checks (INSERT with constraints NOCHECK)
    - Insert data in any order and re-enable constraints with CHECK (and verify)
- If graph building not possible, fallback to heuristic: tables sorted by number of FKs ascending.

---

## Transactions, retries & error handling
- Transactions: group per-table or per-batch; use try/except to rollback on failure.
- Retries: transient DB errors should be retried with backoff.
- Missing mapping policy:
  - default: raise and stop (safer)
  - alternative flags: --skip-unresolvable (skip offending rows), --defer (queue rows to insert after parents)
- Logs: add structured logging (info/warn/error) rather than prints.
- Ensure connections/cursors are closed in finally blocks.

---

## Concurrency & resumability
- Persist mapping_table after each inserted row (or batch) to allow resumption.
- Before starting a source DB run, load mapping rows to in-memory cache.
- Consider using a run id column in mapping table to track which run inserted which mapping.

---

## Security & configuration
- Avoid plaintext credentials in repo. Current approach uses Trusted Connection; for SQL auth, use environment variables or secure store.
- Add CLI flags or env vars for server and credentials.
- Consider allowing JSON config override for ignore tables and static FK settings.

---

## Testing suggestions
- Unit tests:
  - get_primary_key, get_identity_column, get_foreign_keys
  - mapping_table.insert_mapping/get_mapped_id
  - value_mapping add/get behavior
- Integration tests:
  - Use local SQL Server (Docker mssql) with small schema examples:
    - Parent/child relations, identity PKs, composite PKs, nullable FKs, static FK columns
  - End-to-end: create two small source DBs, run tool into a dest DB, validate FK integrity and mapping table contents.
- Add tests/fixtures and CI (GitHub Actions) with a lightweight DB emulator or dockerized mssql for integration.

---

## Performance improvements
- Batch inserts instead of per-row inserts where possible.
- Bulk lookup of mappings for sets of FK values to reduce DB round-trips.
- Use prepared statements and transactions for batches.
- Add progress metrics/logging.

---

## Known gaps & TODOs (actionable)
- [ ] Implement complete column SQL generation & PK/constraint creation in schema_cloner.py.
- [ ] Implement get_foreign_keys(cursor, table) in inserter.py.
- [ ] Implement lookup_mapped_id(cursor, source_db, table, old_id) and mapping_table.get_mapped_id & get_new_id.
- [ ] Add unique index on mapping table to avoid dupes.
- [ ] Add initial load of mapping table into in-memory cache for resumable runs.
- [ ] Add CLI flags (argparse) for non-interactive runs, skip/continue policies, verbose logging.
- [ ] Add unit and integration tests.
- [ ] Centralize DB creation and existence checks into db_utils.py and use it in main.py.
- [ ] Add structured logging and exception handling across modules.

---

## Example helper implementations (sketches)

get_mapped_id (mapping_table.py) sketch:
```python
def get_mapped_id(server, db_name, source_table, source_id):
    conn = get_connection(server, db_name)
    cur = conn.cursor()
    cur.execute("""SELECT mapped_pk_value FROM primary_key_mapping_table
                   WHERE source_table_name=? AND source_pk_value=?""",
                source_table, source_id)
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None
```

get_foreign_keys (inserter.py) sketch:
```python
def get_foreign_keys(cursor, table):
    cursor.execute("<FK metadata SQL from this doc>", table)
    return [
       {"fk_column": r[1], "referenced_table": r[3], "referenced_column": r[2]}
       for r in cursor.fetchall()
    ]
```

---