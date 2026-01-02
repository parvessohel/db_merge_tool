# db_utils.py

import pyodbc
from connection import get_connection

def database_exists(server, db_name):
    conn = get_connection(server, "master")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM sys.databases WHERE name = ?",
        db_name
    )

    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def create_database(server, db_name):
    conn = get_connection(server, "master")
    cursor = conn.cursor()

    cursor.execute(f"CREATE DATABASE [{db_name}]")
    conn.commit()
    conn.close()
