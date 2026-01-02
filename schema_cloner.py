from connection import get_connection

def clone_schema(source_db, dest_db, server):
    src_conn = get_connection(server, source_db)
    dest_conn = get_connection(server, dest_db)

    src_cursor = src_conn.cursor()
    dest_cursor = dest_conn.cursor()

    # Get all tables except mapping table
    src_cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
          AND TABLE_NAME != 'primary_key_mapping_table'
    """)
    tables = [row[0] for row in src_cursor.fetchall()]

    for table in tables:
        # Get column definitions
        src_cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   IS_NULLABLE,
                   COLUMNPROPERTY(
                       OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME),
                       COLUMN_NAME, 'IsIdentity'
                   ) AS IS_IDENTITY
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION
        """, table)

        columns = src_cursor.fetchall()

        column_defs = []
        identity_column = None

        for col in columns:
            name, dtype, length, nullable, is_identity = col

            col_def = f"[{name}] {dtype}"

            if dtype in ("varchar", "nvarchar", "char", "nchar") and length:
                col_def += f"({length})"
            elif dtype in ("decimal", "numeric"):
                col_def += "(18,2)"

            if is_identity:
                col_def += " IDENTITY(1,1)"
                identity_column = name

            if nullable == "NO":
                col_def += " NOT NULL"

            column_defs.append(col_def)

        # Primary key
        src_cursor.execute("""
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_NAME = ?
              AND OBJECTPROPERTY(
                OBJECT_ID(CONSTRAINT_SCHEMA + '.' + CONSTRAINT_NAME),
                'IsPrimaryKey'
              ) = 1
        """, table)

        pk = src_cursor.fetchone()
        if pk:
            column_defs.append(f"PRIMARY KEY ([{pk[0]}])")

        create_sql = f"""
        CREATE TABLE [{table}] (
            {', '.join(column_defs)}
        )
        """

        dest_cursor.execute(create_sql)
        dest_conn.commit()

    src_conn.close()
    dest_conn.close()
