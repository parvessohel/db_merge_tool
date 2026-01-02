
# main_ui.py

import tkinter as tk
from tkinter import messagebox
from inserter import insert_database
from schema_cloner import clone_schema
from connection import get_connection

def create_database(server, db_name):
    # Autocommit connection to allow CREATE DATABASE
    conn = get_connection(server, 'master')
    conn.autocommit = True
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

def start_merge():
    server = server_entry.get().strip()
    source_input = source_entry.get().strip()
    dest_db = dest_entry.get().strip()

    if not server or not source_input:
        messagebox.showerror("Input Error", "Please enter server and source databases.")
        return

    # Parse source DBs
    source_dbs = [db.strip() for db in source_input.split(',') if db.strip()]
    if not source_dbs:
        messagebox.showerror("Input Error", "Please enter at least one source database.")
        return

    # Set default destination if empty
    if not dest_db:
        dest_db = "_".join(source_dbs) + "_merged"
    
    try:
        print(f"\nCreating database '{dest_db}'...")
        create_database(server, dest_db)

        print("\nCloning schema from first source database...")
        clone_schema(source_dbs[0], dest_db, server)
        print("Schema cloned successfully.")

        create_mapping_table(server, dest_db)
        print("Mapping table created successfully.\n")

        print(f"Merging all tables from {len(source_dbs)} source(s) into '{dest_db}'...\n")
        for src_db in source_dbs:
            print(f"Processing source database: {src_db}")
            insert_database(src_db, dest_db, server)
            print(f"Data from '{src_db}' merged successfully.\n")

        messagebox.showinfo("Success", f"Merge completed! All data is now in '{dest_db}'.")
    except Exception as e:
        messagebox.showerror("Error", str(e))

# -------------------- GUI --------------------
root = tk.Tk()
root.title("DB Merge Tool")

tk.Label(root, text="SQL Server Name (e.g., localhost\\INSTANCE):").grid(row=0, column=0, sticky="w")
server_entry = tk.Entry(root, width=50)
server_entry.grid(row=0, column=1, padx=5, pady=5)

tk.Label(root, text="Source Databases (comma separated):").grid(row=1, column=0, sticky="w")
source_entry = tk.Entry(root, width=50)
source_entry.grid(row=1, column=1, padx=5, pady=5)

tk.Label(root, text="Destination Database (optional):").grid(row=2, column=0, sticky="w")
dest_entry = tk.Entry(root, width=50)
dest_entry.grid(row=2, column=1, padx=5, pady=5)

start_button = tk.Button(root, text="Start Merge", command=start_merge, bg="green", fg="white")
start_button.grid(row=3, column=0, columnspan=2, pady=10)

root.mainloop()
