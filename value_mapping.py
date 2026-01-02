# value_mapping.py

# Dictionary to store mapping: (source_db, table, source_id) -> mapped_id
pk_mapping = {}

def add_mapping(source_db, source_table, source_pk_value, mapped_db, mapped_table, mapped_pk_value):
    """
    Store the mapping in memory
    """
    key = (source_db, source_table, source_pk_value)
    pk_mapping[key] = mapped_pk_value

def get_mapped_id(source_db, source_table, source_pk_value):
    """
    Retrieve mapped ID for a given source
    """
    key = (source_db, source_table, source_pk_value)
    return pk_mapping.get(key)
