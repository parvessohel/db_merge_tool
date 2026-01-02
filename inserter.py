# inserter.py

from connection import get_connection
from value_mapping import add_mapping

def get_primary_key(cursor, table_name):
    cursor.execute("""
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE OBJECTPROPERTY(
            OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME), 'IsPrimaryKey') = 1
          AND TABLE_NAME = ?
    """, table_name)
    result = cursor.fetchone()
    if result:
        return result[0]
    raise Exception(f"No primary key found for table '{table_name}'.")

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
        pk_column = get_primary_key(src_cursor, table_name)

        # Check if PK column is identity in destination
        dest_cursor.execute("""
            SELECT COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, 'IsIdentity')
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ? AND COLUMN_NAME = ?
        """, table_name, pk_column)
        identity_result = dest_cursor.fetchone()
        identity_column = pk_column if identity_result and identity_result[0] == 1 else None

        # Fetch all rows from source
        src_cursor.execute(f"SELECT * FROM {table_name}")
        rows = src_cursor.fetchall()
        columns = [col[0] for col in src_cursor.description]

        # Enable IDENTITY_INSERT if identity column exists
        if identity_column:
            dest_cursor.execute(f"SET IDENTITY_INSERT {table_name} ON")

        for row in rows:
            values = list(row)  # make mutable
            source_pk_value = row[columns.index(pk_column)]

            # Check if PK already exists in destination
            dest_cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {pk_column} = ?", source_pk_value)
            if dest_cursor.fetchone()[0] > 0:
                # PK exists, generate a new unique ID
                dest_cursor.execute(f"SELECT ISNULL(MAX({pk_column}), 0) FROM {table_name}")
                new_id = dest_cursor.fetchone()[0] + 1
                # Update the value in the row
                values[columns.index(pk_column)] = new_id
            else:
                # PK not present, use source PK
                new_id = source_pk_value

            # Insert row into destination
            placeholders = ', '.join(['?'] * len(columns))
            col_names_str = ', '.join(columns)
            dest_cursor.execute(
                f"INSERT INTO {table_name} ({col_names_str}) VALUES ({placeholders})",
                values
            )

            # Update mapping table
            add_mapping(
                source_db, table_name, source_pk_value,
                dest_db, table_name, new_id
            )

            dest_cursor.execute("""
                INSERT INTO primary_key_mapping_table
                (source_db_name, source_table_name, source_pk_column, source_pk_value,
                 mapped_db_name, mapped_table_name, mapped_pk_column, mapped_pk_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_db, table_name, pk_column, source_pk_value,
                  dest_db, table_name, pk_column, new_id))

        # Commit after finishing table
        dest_conn.commit()

        # Disable IDENTITY_INSERT if used
        if identity_column:
            dest_cursor.execute(f"SET IDENTITY_INSERT {table_name} OFF")
            dest_conn.commit()

        print(f"Inserted {len(rows)} rows from {source_db}.{table_name} into {dest_db}.{table_name}")

    src_conn.close()
    dest_conn.close()
