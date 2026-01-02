# main.py

from inserter import insert_database

def main():
    print("Welcome to DB Merge Tool!")

    # Prompt for SQL Server name
    server = input("Enter SQL Server name (e.g., localhost or SERVER\\INSTANCE): ").strip()

    # Prompt for number of source databases
    while True:
        try:
            num_sources = int(input("How many source databases do you want to merge? ").strip())
            if num_sources < 1:
                print("Please enter a number >= 1.")
                continue
            break
        except ValueError:
            print("Please enter a valid number.")

    # Prompt for source DB names
    source_dbs = []
    for i in range(1, num_sources + 1):
        name = input(f"Enter source database name {i}: ").strip()
        source_dbs.append(name)

    # Prompt for destination DB
    dest_db = input("Enter destination database name: ").strip()

    print(f"\nMerging all tables from {num_sources} source(s) into '{dest_db}'...\n")

    # Merge each source database
    for src_db in source_dbs:
        print(f"Processing source database: {src_db}")
        insert_database(src_db, dest_db, server=server)

    print("\nAll merges completed successfully!")

if __name__ == "__main__":
    main()
