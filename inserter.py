# filepath: g:\Nextech\Projects\db_merge_tool\inserter.py
import pyodbc
import json
import os
from connection import get_connection
from value_mapping import add_mapping

# ----------------------------------
# Load config
# ----------------------------------
def load_config():
    path = os.path.join(os.path.dirname(__file__), "ignore_tables.json")
    if not os.path.exists(path):
        return {"ignore_tables": [], "static_foreign_keys": {}}
    with open(path, "r") as f:
        return json.load(f)

# ----------------------------------
# Metadata helpers
# ----------------------------------
def get_primary_key(cursor, table):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE OBJECTPROPERTY(
            OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME),
            'IsPrimaryKey'
        ) = 1 AND TABLE_NAME = ?
    """, table)
    row = cursor.fetchone()
    if not row:
        raise Exception(f"No PK found for {table}")
    return row[0]

def get_identity_column(cursor, table):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
        AND COLUMNPROPERTY(
            OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME),
            COLUMN_NAME,
            'IsIdentity'
        ) = 1
    """, table)
    row = cursor.fetchone()
    return row[0] if row else None

def get_all_tables(cursor):
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
        AND TABLE_NAME != 'primary_key_mapping_table'
    """)
    return [r[0] for r in cursor.fetchall()]

def get_foreign_keys(cursor, table):
    cursor.execute("""
        SELECT
            cu.COLUMN_NAME,
            pk.TABLE_NAME
        FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE cu
            ON cu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE pk
            ON pk.CONSTRAINT_NAME = rc.UNIQUE_CONSTRAINT_NAME
        WHERE cu.TABLE_NAME = ?
    """, table)
    return {r[0]: r[1] for r in cursor.fetchall()}

def lookup_mapped_id(cursor, source_db, table, old_id):
    cursor.execute("""
        SELECT mapped_pk_value
        FROM primary_key_mapping_table
        WHERE source_db_name = ?
        AND source_table_name = ?
        AND source_pk_value = ?
    """, (source_db, table, old_id))
    row = cursor.fetchone()
    if not row:
        raise Exception(f"❌ Missing mapping: {source_db}.{table}.id={old_id}")
    return int(row[0])

# ----------------------------------
# Dependency-safe insert
# ----------------------------------
def insert_database(source_db, dest_db, server="localhost", config=None):
    if config is None:
        config = load_config()

    ignore_tables = [t.lower() for t in config.get("ignore_tables", [])]
    static_fk_cfg = config.get("static_foreign_keys", {})

    src_conn = get_connection(server, source_db)
    dest_conn = get_connection(server, dest_db)

    src_cur = src_conn.cursor()
    dest_cur = dest_conn.cursor()

    tables = get_all_tables(src_cur)

    # ---- IMPORTANT: parent tables first
    tables.sort(key=lambda t: len(get_foreign_keys(src_cur, t)))

    for table in tables:
        if table.lower() in ignore_tables:
            print(f"Skipping table '{table}' (ignored)\n")
            continue

        print(f"Merging {source_db}.{table}")

        pk = get_primary_key(src_cur, table)
        identity_col = get_identity_column(dest_cur, table)
        fks = get_foreign_keys(src_cur, table)
        static_fks = static_fk_cfg.get(table, [])

        src_cur.execute(f"SELECT * FROM {table}")
        rows = src_cur.fetchall()
        cols = [c[0] for c in src_cur.description]

        for row in rows:
            data = dict(zip(cols, row))
            old_pk = data[pk]

            # ---- FK REMAP (skip nulls and static fks)
            for fk_col, ref_table in fks.items():
                if fk_col in static_fks:
                    continue
                fk_value = data.get(fk_col)
                if fk_value is None:
                    continue
                data[fk_col] = lookup_mapped_id(dest_cur, source_db, ref_table, fk_value)

            # ---- Ensure student_id is remapped even if FK metadata is missing
            if table.lower() == "student_enrolled" and "student_id" in data:
                sid = data.get("student_id")
                if sid is not None:
                    data["student_id"] = lookup_mapped_id(dest_cur, source_db, "students", sid)

            # ---- INSERT
            if identity_col:
                insert_cols = [c for c in cols if c != identity_col]
                values = [data[c] for c in insert_cols]
                placeholders = ",".join("?" for _ in insert_cols)
                names = ",".join(f"[{c}]" for c in insert_cols)

                # Use OUTPUT INSERTED to reliably get the new identity value
                sql = f"INSERT INTO {table} ({names}) OUTPUT INSERTED.[{identity_col}] VALUES ({placeholders})"
                dest_cur.execute(sql, values)
                row_out = dest_cur.fetchone()
                if not row_out or row_out[0] is None:
                    raise Exception(f"Failed to retrieve new identity for {dest_db}.{table}")
                new_pk = int(row_out[0])
            else:
                dest_cur.execute(f"SELECT ISNULL(MAX({pk}),0) FROM {table}")
                new_pk = dest_cur.fetchone()[0] + 1
                data[pk] = new_pk

                placeholders = ",".join("?" for _ in cols)
                names = ",".join(f"[{c}]" for c in cols)
                dest_cur.execute(f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                                 [data[c] for c in cols])

            # ---- SAVE MAPPING
            dest_cur.execute("""
                INSERT INTO primary_key_mapping_table
                (source_db_name, source_table_name, source_pk_column, source_pk_value,
                 mapped_db_name, mapped_table_name, mapped_pk_column, mapped_pk_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_db, table, pk, old_pk, dest_db, table, pk, new_pk))

            add_mapping(source_db, table, old_pk, dest_db, table, new_pk)

        dest_conn.commit()
        print(f"Inserted {len(rows)} rows into {dest_db}.{table}\n")

    src_conn.close()
    dest_conn.close()