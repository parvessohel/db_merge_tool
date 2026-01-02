# main.py

from connection import get_connection
from schema_cloner import clone_schema
from inserter import insert_database
import pyodbc

def create_database(server, db_name):
    """
    Create a new database if it does not exist.
    Use autocommit for CREATE DATABASE to avoid multi-statement transaction errors.
    """
    # Direct pyodbc connection with autocommit
    conn = pyodbc.connect(
        f'DRIVER={{SQL Server}};SERVER={server};Trusted_Connection=yes;',
        autocommit=True
    )
    cursor = conn.cursor()

    # Check if database exists
    cursor.execute("SELECT name FROM sys.databases WHERE name = ?", db_name)
    if cursor.fetchone():
        print(f"Database '{db_name}' already exists. Using existing database.")
    else:
        print(f"Creating database '{db_name}'...")
        cursor.execute(f"CREATE DATABASE [{db_name}]")
        print(f"Database '{db_name}' created successfully.")

    cursor.close()
    conn.close()


def create_mapping_table(server, dest_db):
    """
    Create the primary_key_mapping_table if it doesn't exist.
    """
    conn = get_connection(server, dest_db)
    cursor = conn.cursor()

    cursor.execute("""
    IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'primary_key_mapping_table')
    BEGIN
        CREATE TABLE primary_key_mapping_table (
            source_db_name NVARCHAR(255),
            source_table_name NVARCHAR(255),
            source_pk_column NVARCHAR(255),
            source_pk_value BIGINT,
            mapped_db_name NVARCHAR(255),
            mapped_table_name NVARCHAR(255),
            mapped_pk_column NVARCHAR(255),
            mapped_pk_value BIGINT,
            created_at DATETIME DEFAULT GETDATE()
        )
    END
    """)
    conn.commit()
    conn.close()
    print("Mapping table created successfully.\n")


def main():
    print("Welcome to DB Merge Tool!")

    server = input("Enter SQL Server name (e.g., localhost or SERVER\\INSTANCE): ").strip()

    # Number of source databases
    while True:
        num_sources_input = input("How many source databases do you want to merge? ").strip()
        if num_sources_input.isdigit():
            num_sources = int(num_sources_input)
            break
        else:
            print("Please enter a valid number.")

    source_dbs = []
    for i in range(num_sources):
        db_name = input(f"Enter source database name {i+1}: ").strip()
        source_dbs.append(db_name)

    # Default destination DB name
    default_dest_db = "_".join(source_dbs) + "_merged"
    dest_db = input(f"\nDefault destination database name: {default_dest_db}\nPress Enter to accept or type a new name: ").strip()
    if not dest_db:
        dest_db = default_dest_db

    # Create destination database
    create_database(server, dest_db)

    # Clone schema from first source DB
    print("\nCloning schema from first source database...")
    clone_schema(source_dbs[0], dest_db, server)
    print("Schema cloned successfully.\n")

    # Create mapping table
    create_mapping_table(server, dest_db)

    # Merge data from all source DBs
    print(f"Merging all tables from {num_sources} source(s) into '{dest_db}'...\n")
    for src_db in source_dbs:
        print(f"Processing source database: {src_db}")
        insert_database(src_db, dest_db, server)
        print(f"Data from '{src_db}' merged successfully.\n")

    print(f"\nMerge completed successfully! All data is now in '{dest_db}'.")


if __name__ == "__main__":
    main()
