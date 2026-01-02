# inserter.py

import pyodbc
from connection import get_connection
from value_mapping import add_mapping

def get_primary_key(cursor, table_name):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE OBJECTPROPERTY(OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME), 'IsPrimaryKey') = 1
          AND TABLE_NAME = ?
    """, table_name)
    result = cursor.fetchone()
    if result:
        return result[0]
    raise Exception(f"No primary key found for table '{table_name}'.")

def get_identity_column(cursor, table_name):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ?
          AND COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, 'IsIdentity') = 1
    """, table_name)
    result = cursor.fetchone()
    return result[0] if result else None

def get_all_tables(cursor):
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE='BASE TABLE'
          AND TABLE_NAME != 'primary_key_mapping_table'
    """)
    return [row[0] for row in cursor.fetchall()]

def insert_database(source_db, dest_db, server='localhost'):
    src_conn = get_connection(server, source_db)
    dest_conn = get_connection(server, dest_db)

    src_cursor = src_conn.cursor()
    dest_cursor = dest_conn.cursor()

    tables = get_all_tables(src_cursor)

    for table_name in tables:
        print(f"Inserting data from {source_db}.{table_name}")

        pk_column = get_primary_key(src_cursor, table_name)
        dest_identity_col = get_identity_column(dest_cursor, table_name)

        src_cursor.execute(f"SELECT * FROM {table_name}")
        rows = src_cursor.fetchall()
        columns = [col[0] for col in src_cursor.description]

        for row in rows:
            row_dict = dict(zip(columns, row))
            source_pk_value = row_dict[pk_column]

            # Handle IDENTITY or PK conflicts
            if dest_identity_col:
                # Remove identity column from insert to let SQL Server auto-generate new ID
                insert_columns = [c for c in columns if c != dest_identity_col]
                insert_values = [row_dict[c] for c in insert_columns]
                placeholders = ','.join(['?'] * len(insert_columns))
                col_names = ','.join(f"[{c}]" for c in insert_columns)

                dest_cursor.execute(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})", insert_values)

                # Get the new generated ID
                dest_cursor.execute("SELECT SCOPE_IDENTITY()")
                new_id = int(dest_cursor.fetchone()[0])
            else:
                # No identity, manually generate new ID to avoid duplicates
                dest_cursor.execute(f"SELECT MAX({pk_column}) FROM {table_name}")
                max_id = dest_cursor.fetchone()[0] or 0
                new_id = max_id + 1
                row_dict[pk_column] = new_id
                placeholders = ','.join(['?'] * len(columns))
                col_names = ','.join(f"[{c}]" for c in columns)
                values = [row_dict[c] for c in columns]
                dest_cursor.execute(f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})", values)

            # Update mapping table
            dest_cursor.execute("""
                INSERT INTO primary_key_mapping_table
                (source_db_name, source_table_name, source_pk_column, source_pk_value,
                 mapped_db_name, mapped_table_name, mapped_pk_column, mapped_pk_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_db, table_name, pk_column, source_pk_value,
                  dest_db, table_name, pk_column, new_id))

            # Also add mapping in memory
            add_mapping(source_db, table_name, source_pk_value, dest_db, table_name, new_id)

        dest_conn.commit()
        print(f"Inserted {len(rows)} rows from {source_db}.{table_name} into {dest_db}.{table_name}\n")

    src_conn.close()
    dest_conn.close()
