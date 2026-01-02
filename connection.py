import pyodbc

def get_connection(server: str, database: str):
    """
    Returns a pyodbc connection object to the specified SQL Server database.
    """
    conn = pyodbc.connect(
        f'DRIVER={{SQL Server}};SERVER={server};DATABASE={database};Trusted_Connection=yes;'
    )
    return conn
