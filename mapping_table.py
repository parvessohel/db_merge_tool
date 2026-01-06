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
