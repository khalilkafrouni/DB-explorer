import csv
import os
from pathlib import Path

def generate_create_tables_sql(csv_directory: str = None, wait_for_csv: bool = False):
    """
    Generate SQL CREATE TABLE statements from relationship and column CSV files.
    
    Args:
        csv_directory (str): Directory containing the CSV files. If None, will wait for the latest directory.
        wait_for_csv (bool): Whether to wait for CSV files to be created if they don't exist.
    
    Returns:
        bool: True if tables were created successfully, False otherwise.
    """
    # If no directory specified, find the latest one
    if not csv_directory:
        directories = [d for d in os.listdir() if d.startswith('bettorfantasy_sisense_staging_')]
        if not directories:
            if not wait_for_csv:
                print("No CSV directory found and wait_for_csv is False")
                return False
            print("Waiting for CSV files to be created...")
            return False
        csv_directory = max(directories)  # Get the latest directory

    relationships_file = os.path.join(csv_directory, 'verified_relationships.csv')
    columns_file = os.path.join(csv_directory, 'table_columns.csv')
    
    # Check if required files exist
    if not os.path.exists(relationships_file) or not os.path.exists(columns_file):
        if not wait_for_csv:
            print(f"Required CSV files not found in {csv_directory}")
            return False
        print("Waiting for CSV files to be created...")
        return False

    # Read relationships from CSV
    relationships = []
    with open(relationships_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only consider forward relationships (→) to avoid redundancy
            if row['relationship'].startswith('→') and row['verified'] == 'True':
                relationships.append(row)

    # Read table columns from CSV
    table_columns = {}
    with open(columns_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            table_name = row['table_name']
            if table_name not in table_columns:
                table_columns[table_name] = []
            
            # Build column definition
            col_def = {
                'name': row['column_name'],
                'type': row['data_type'],
                'nullable': row['is_nullable'] == 'YES',
                'key_type': row['key_type'],
                'default': row['default_value'],
                'extra': row['extra']
            }
            table_columns[table_name].append(col_def)

    # Create dictionaries to store relationships and primary keys
    fk_relationships = {}
    pk_fields = {}
    
    # Process relationships
    for rel in relationships:
        source_table = rel['table_name']
        source_field = rel['field_name']
        
        # Parse target table and field from the relationship
        target_info = rel['relationship'].split('.')
        target_table = target_info[-2].split(' ')[-1]
        target_field = target_info[-1]
        
        # Store primary key
        if rel['field_type'] == 'PK':
            pk_fields[source_table] = source_field
            
        # Store foreign key relationship from target's perspective
        if target_table not in fk_relationships:
            fk_relationships[target_table] = []
            
        fk_relationships[target_table].append({
            'field': target_field,
            'references_table': source_table,
            'references_field': source_field
        })

    # SQL file header
    sql_content = """-- Auto-generated CREATE TABLE statements with foreign key relationships
SET FOREIGN_KEY_CHECKS=0;
"""

    # Generate CREATE TABLE statements
    for table_name in table_columns.keys():
        sql_content += f"\nCREATE TABLE `{table_name}` (\n"
        
        # Add columns
        columns = []
        for col in table_columns[table_name]:
            col_def = [f"  `{col['name']}` {col['type']}"]
            
            if not col['nullable']:
                col_def.append('NOT NULL')
                
            if col['default'] not in [None, '', 'NULL']:
                if col['type'].lower() in ['varchar', 'text', 'longtext', 'char', 'datetime', 'date']:
                    col_def.append(f"DEFAULT '{col['default']}'")
                else:
                    col_def.append(f"DEFAULT {col['default']}")
                    
            if col['extra']:
                col_def.append(col['extra'])
                
            columns.append(' '.join(col_def))
        
        # Add primary key if it exists in the relationships
        if table_name in pk_fields:
            columns.append(f"  PRIMARY KEY (`{pk_fields[table_name]}`)")
        # If not in relationships but has a PRI key_type in columns, use that
        else:
            pri_keys = [col['name'] for col in table_columns[table_name] if col['key_type'] == 'PRI']
            if pri_keys:
                columns.append(f"  PRIMARY KEY (`{pri_keys[0]}`)")
        
        # Add foreign key constraints
        if table_name in fk_relationships:
            for fk in fk_relationships[table_name]:
                fk_constraint = f"  FOREIGN KEY (`{fk['field']}`) REFERENCES `{fk['references_table']}`(`{fk['references_field']}`)"
                columns.append(fk_constraint)
        
        # Join columns with commas
        sql_content += ',\n'.join(columns)
        
        # Add table suffix
        sql_content += "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n"

    # Re-enable foreign key checks
    sql_content += "\nSET FOREIGN_KEY_CHECKS=1;\n"

    # Write the generated SQL to file in the same directory as the CSV files
    output_file = os.path.join(csv_directory, 'create_tables.sql')
    with open(output_file, 'w') as f:
        f.write(sql_content)
        
    print(f"Successfully created {output_file}")
    return True

if __name__ == "__main__":
    generate_create_tables_sql() 