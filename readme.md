# DB Merge Tool ✅

**A lightweight Python utility to merge multiple SQL Server databases into a single destination database.** It preserves primary keys, handles identity (auto-increment) columns, and maintains a mapping log for traceability.

---

## 🔧 Features

- Merge tables from one or more source databases into a single destination database
- Handle **primary key conflicts** by generating new IDs when needed
- Support **IDENTITY** (auto-increment) columns via `SET IDENTITY_INSERT` when required
- Maintain a **primary key mapping table** for each inserted row (source → destination mapping)
- Simple CLI prompts to specify server, sources, and destination

---

## ⚙️ Prerequisites

- Python 3.8+ (or 3.x)
- `pyodbc` (install with pip)
- Access to a SQL Server instance containing the source and destination databases

Install dependencies:

```bash
pip install pyodbc
```

---

## 📁 Project Structure

```
db_merge_tool/
│
├─ connection.py        # Database connection helpers
├─ value_mapping.py     # Manage source-to-destination PK mappings
├─ inserter.py          # Core merge logic (reads, maps, inserts)
├─ main.py              # CLI entry point
└─ README.md            # This file
```

---

## ▶️ Usage

Run the tool:

```bash
python main.py
```

Follow the prompts to enter:
- SQL Server name (e.g., `localhost` or `SERVER\INSTANCE`)
- Number of source databases
- Each source database name
- Destination database name

Example (interactive):

```
Enter SQL Server name: sh1kari
How many source databases do you want to merge? 2
Enter source database name 1: School_Source_1
Enter source database name 2: School_Source_2
Enter destination database name: School
```

Expected output (sample):

```
Merging all tables from 2 source(s) into 'School'...
Processing source database: School_Source_1
Inserted 50 rows from School_Source_1.students into School.students
Processing source database: School_Source_2
Inserted 50 rows from School_Source_2.students into School.students
Merge completed successfully!
```

---

## 🔍 What the tool does

- Iterates every table in each source database (except the `primary_key_mapping_table`)
- Reads all rows, checks for PK conflicts in the destination
- If conflict, generates a new PK and records the mapping in `primary_key_mapping_table`
- Handles IDENTITY columns properly using `IDENTITY_INSERT` where necessary

---

## 🧾 Inspecting results

Query merged rows and mapping data (example):

```sql
SELECT s.*, m.source_db_name, m.source_pk_value AS source_id, m.created_at AS mapping_time
FROM students s
JOIN primary_key_mapping_table m
  ON s.id = m.mapped_pk_value
ORDER BY s.id;
```

---

## ⚠️ Notes & Recommendations

- Ensure **destination database already exists** and you have appropriate permissions
- The mapping table prevents duplicate mappings and provides traceability; do not merge it
- Test on a small subset or a copy of databases before running on production data

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome. Please open issues or pull requests.

---

## 📜 License

This project is licensed under the **MIT License**.