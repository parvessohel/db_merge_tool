# mapping_table.py

from connection import get_connection

TABLE_NAME = "primary_key_mapping_table"

def ensure_mapping_table(server, db_name):
    """
    Create primary_key_mapping_table if it does not exist.
    """
    conn = get_connection(server, db_name)
    cursor = conn.cursor()

    cursor.execute(f"""
    IF NOT EXISTS (
        SELECT * FROM sys.tables WHERE name = '{TABLE_NAME}'
    )
    BEGIN
        CREATE TABLE {TABLE_NAME} (
            source_db_name NVARCHAR(255) NOT NULL,
            source_table_name NVARCHAR(255) NOT NULL,
            source_pk_column NVARCHAR(255) NOT NULL,
            source_pk_value BIGINT NOT NULL,

            mapped_db_name NVARCHAR(255) NOT NULL,
            mapped_table_name NVARCHAR(255) NOT NULL,
            mapped_pk_column NVARCHAR(255) NOT NULL,
            mapped_pk_value BIGINT NOT NULL,

            created_at DATETIME NOT NULL DEFAULT GETDATE()
        )
    END
    """)

    conn.commit()
    conn.close()


def insert_mapping(
    server, db_name,
    source_db, source_table, source_column, source_value,
    mapped_db, mapped_table, mapped_column, mapped_value
):
    """
    Insert a new mapping into the mapping table.
    """
    conn = get_connection(server, db_name)
    cursor = conn.cursor()

    cursor.execute(f"""
    INSERT INTO {TABLE_NAME} (
        source_db_name, source_table_name, source_pk_column, source_pk_value,
        mapped_db_name, mapped_table_name, mapped_pk_column, mapped_pk_value
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_db, source_table, source_column, source_value,
        mapped_db, mapped_table, mapped_column, mapped_value
    ))

    conn.commit()
    conn.close()


def get_mapped_id(server, db_name, source_table, source_id):
    """
    Get the mapped PK value from the mapping table.
    Returns None if not found.
    """
    conn = get_connection(server, db_name)
    cursor = conn.cursor()

    cursor.execute(f"""
    SELECT mapped_pk_value 
    FROM {TABLE_NAME}
    WHERE source_table_name = ? AND source_pk_value = ?
    """, (source_table, source_id))

    result = cursor.fetchone()
    conn.close()

    if result:
        return result[0]
    return None


def get_new_id(server, db_name, table_name, pk_column, original_id):
    """
    Compute a new ID for insertion into the merged table if original_id exists.
    """
    conn = get_connection(server, db_name)
    cursor = conn.cursor()

    # Check if the ID already exists
    cursor.execute(f"SELECT 1 FROM {table_name} WHERE {pk_column} = ?", (original_id,))
    exists = cursor.fetchone() is not None

    if exists:
        # Get the current max ID and increment
        cursor.execute(f"SELECT MAX({pk_column}) FROM {table_name}")
        max_id = cursor.fetchone()[0]
        new_id = (max_id or 0) + 1
    else:
        new_id = original_id

    conn.close()
    return new_id
