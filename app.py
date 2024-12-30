from sqlalchemy import create_engine
import pandas as pd
import tomli
from openai import OpenAI
import json
from openai_handler import get_matches_from_openai

def initialize_engine(username, password, url, db_name, port):
    engine = create_engine(f'mysql+pymysql://{username}:{password}@{url}:{port}/{db_name}')
    return engine

def get_query(query, engine):
    df = pd.read_sql_query(query, con=engine)
    return df

def get_all_tables(engine):
    query = "SHOW TABLES"
    df = get_query(query, engine)
    df.columns = ['tables_in_database']
    return df

def get_table_columns(table_name, engine):
    query = f"SHOW COLUMNS FROM {table_name}"
    df = get_query(query, engine)
    df.columns = ['Field', 'Type', 'Null', 'Key', 'Default', 'Extra']
    return df

def get_primary_keys(table_name, engine):
    """Get primary key columns for a table"""
    df = get_query(f"""
        SELECT COLUMN_NAME 
        FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = '{table_name}'
        AND CONSTRAINT_NAME = 'PRIMARY'
    """, engine)
    return df['COLUMN_NAME'].tolist() if not df.empty else []

def is_field_unique(table: str, field: str, engine) -> bool:
    """Check if a field contains only unique values (excluding nulls)"""
    query = f"""
        SELECT COUNT(*) = COUNT(DISTINCT {field}) as is_unique
        FROM {table}
        WHERE {field} IS NOT NULL
    """
    result = get_query(query, engine)
    return bool(result['is_unique'].iloc[0])

def find_potential_keys(engine):
    tables = get_all_tables(engine)
    primary_keys = []
    untracked_tables = []
    
    for table in tables['tables_in_database']:
        # First try to get defined primary keys
        pk_columns = get_primary_keys(table, engine)
        
        if pk_columns:
            # Add each primary key column
            for pk in pk_columns:
                primary_keys.append((table, pk))
            continue

        # Check for 'id' or 'ID' columns
        columns = get_table_columns(table, engine)
        id_cols = columns[columns['Field'].str.lower() == 'id']['Field'].tolist()
        
        if id_cols:
            # Use the first found id column
            primary_keys.append((table, id_cols[0]))
            continue

        # If no primary key or 'id' field, look for unique '*_id' fields
        id_like_cols = columns[
            columns['Field'].str.contains('_id', case=False) |
            columns['Field'].str.contains('ID', regex=False)
        ]['Field'].tolist()

        unique_id_fields = [
            field for field in id_like_cols
            if is_field_unique(table, field, engine)
        ]

        if unique_id_fields:
            # Add all unique ID-like fields as potential keys
            for field in unique_id_fields:
                primary_keys.append((table, field))
        else:
            untracked_tables.append(table)
    
    return primary_keys, untracked_tables

def find_potential_foreign_keys(engine, primary_keys):
    """Find all fields that could be foreign keys (contain '_id' or 'ID' and aren't primary keys)"""
    tables = get_all_tables(engine)
    foreign_keys = []
    primary_key_set = set(primary_keys)  # for faster lookups
    
    for table in tables['tables_in_database']:
        columns = get_table_columns(table, engine)
        # Find all ID-like columns
        id_cols = columns[
            columns['Field'].str.contains('_id', case=False) |
            columns['Field'].str.contains('ID', regex=False)
        ]['Field'].tolist()
        
        # Add fields that aren't in primary_keys
        for field in id_cols:
            if (table, field) not in primary_key_set:
                foreign_keys.append((table, field))
    
    return foreign_keys

def generate_all_possible_matches(unique_keys):
    """Generate all possible matches between verified unique keys"""
    matches = []
    for i, (table1, field1) in enumerate(unique_keys):
        for table2, field2 in unique_keys[i+1:]:
            if table1 != table2:  # Avoid self-joins
                matches.append({
                    'table1': table1,
                    'field1': field1,
                    'table2': table2,
                    'field2': field2
                })
    return matches

def split_into_chunks(matches, chunk_size=30):
    return [matches[i:i + chunk_size] for i in range(0, len(matches), chunk_size)]

def find_untracked_keys(potential_keys, openai_matches):
    # Create a set of all keys that were matched by OpenAI
    matched_keys = set()
    for match in openai_matches:
        matched_keys.add((match['table1'], match['field1']))
        matched_keys.add((match['table2'], match['field2']))
    
    # Find keys that weren't matched
    untracked = set(potential_keys) - matched_keys
    return list(untracked)

def generate_fk_pk_matches(primary_keys, foreign_keys):
    """Generate all possible matches between foreign keys and primary keys"""
    matches = []
    primary_key_dict = {}
    
    # Group primary keys by field name for faster lookup
    for table, field in primary_keys:
        # Strip '_id' suffix if present for matching
        base_field = field.lower().replace('_id', '')
        primary_key_dict[base_field] = primary_key_dict.get(base_field, []) + [(table, field)]
    
    for fk_table, fk_field in foreign_keys:
        # Strip '_id' suffix for matching
        base_fk = fk_field.lower().replace('_id', '')
        
        # Look for matching primary keys
        if base_fk in primary_key_dict:
            for pk_table, pk_field in primary_key_dict[base_fk]:
                if pk_table != fk_table:  # Avoid self-references
                    matches.append({
                        'table_pk': pk_table,
                        'field_pk': pk_field,
                        'table_fk': fk_table,
                        'field_fk': fk_field
                    })
    
    return matches

def find_unmatched_foreign_keys(foreign_keys, fk_pk_matches):
    """Find foreign keys that weren't matched with any primary key"""
    matched_fks = set(
        (match['table_fk'], match['field_fk']) 
        for match in fk_pk_matches
    )
    unmatched = [
        (table, field) 
        for table, field in foreign_keys 
        if (table, field) not in matched_fks
    ]
    return unmatched

def verify_relationship(engine, table_pk, field_pk, table_fk, field_fk):
    """Verify if a foreign key actually points to a primary key"""
    try:
        # Check 2: All non-null FK values must exist in PK (referential integrity)
        integrity_check = get_query(f"""
            SELECT COUNT(*) as invalid_count
            FROM {table_fk} fk
            LEFT JOIN {table_pk} pk ON fk.{field_fk} = pk.{field_pk}
            WHERE fk.{field_fk} IS NOT NULL 
            AND pk.{field_pk} IS NULL
        """, engine).iloc[0]['invalid_count']
        
        if integrity_check > 0:
            return {
                'verified': False,
                'reason': f"Found {integrity_check} FK values not present in PK"
            }
        
        # Check 3: Usage patterns and statistics
        usage_stats = get_query(f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT({field_fk}) as non_null_count,
                COUNT(DISTINCT {field_fk}) as fk_distinct_values,
                (
                    SELECT COUNT(DISTINCT {field_pk})
                    FROM {table_pk}
                ) as pk_distinct_values
            FROM {table_fk}
        """, engine).iloc[0]
        
        return {
            'verified': True,
            'stats': {
                'referential_integrity': True,
                'null_percentage': (usage_stats['total_rows'] - usage_stats['non_null_count']) / usage_stats['total_rows'] * 100,
                'distinct_values_fk': usage_stats['fk_distinct_values'],
                'distinct_values_pk': usage_stats['pk_distinct_values'],
                'coverage': usage_stats['fk_distinct_values'] / usage_stats['pk_distinct_values'] * 100
            }
        }
        
    except Exception as e:
        return {
            'verified': False,
            'reason': f"Error during verification: {str(e)}"
        }

def save_verified_matches(matches, verification_results, filename="verified_relationships.csv"):
    """Save verified FK-PK relationships and their statistics to a CSV file"""
    verified_data = []
    
    for match, result in zip(matches, verification_results):
        data = {
            'pk_table': match['table_pk'],
            'pk_field': match['field_pk'],
            'fk_table': match['table_fk'],
            'fk_field': match['field_fk'],
            'verified': result['verified']
        }
        
        if result['verified']:
            data.update({
                'reason': 'verified',
                **result['stats']
            })
        else:
            data.update({
                'reason': result['reason'],
                'referential_integrity': False,
                'null_percentage': None,
                'distinct_values_fk': None,
                'distinct_values_pk': None,
                'coverage': None
            })
            
        verified_data.append(data)
    
    df = pd.DataFrame(verified_data)
    df.to_csv(filename, index=False)
    return filename

# Example usage
with open("secrets.toml", "rb") as f:
    secrets = tomli.load(f)

username = secrets['bettor_fantasy']['db_username']
password = secrets['bettor_fantasy']['db_password']
db_url = secrets['bettor_fantasy']['db_url']
db_name = secrets['bettor_fantasy']['db_name']
port = secrets['bettor_fantasy']['port']
engine = initialize_engine(username, password, db_url, db_name, port)

# Get primary keys and potential foreign keys
potential_keys, untracked_tables = find_potential_keys(engine)
potential_foreign_keys = find_potential_foreign_keys(engine, potential_keys)
fk_pk_matches = generate_fk_pk_matches(potential_keys, potential_foreign_keys)
unmatched_fks = find_unmatched_foreign_keys(potential_foreign_keys, fk_pk_matches)

print("\nPrimary Keys found:", potential_keys)
print("\nPotential Foreign Keys found:", potential_foreign_keys)
print("\nPotential FK-PK Matches:")
for match in fk_pk_matches:
    print(f"{match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']}")

print("\nUnmatched Foreign Keys:")
for table, field in unmatched_fks:
    print(f"{table}.{field}")

print("\nTables without unique identifiers:", untracked_tables)

print("\nVerifying FK-PK relationships:")
verification_results = []
for match in fk_pk_matches:
    result = verify_relationship(
        engine,
        match['table_pk'],
        match['field_pk'],
        match['table_fk'],
        match['field_fk']
    )
    verification_results.append(result)
    
    print(f"\n{match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']}")
    if result['verified']:
        stats = result['stats']
        print("✓ Verified")
        print(f"- Null percentage: {stats['null_percentage']:.1f}%")
        print(f"- Distinct values: FK={stats['distinct_values_fk']}, PK={stats['distinct_values_pk']}")
        print(f"- PK coverage: {stats['coverage']:.1f}%")
    else:
        print("✗ Failed:", result['reason'])

# Save results to CSV
csv_filename = save_verified_matches(fk_pk_matches, verification_results)
print(f"\nVerification results saved to: {csv_filename}")

print(f"\nVerification Summary:")
print(f"Total relationships analyzed: {len(fk_pk_matches)}")
print(f"Verified relationships: {sum(1 for r in verification_results if r['verified'])}")
print(f"Failed relationships: {len(fk_pk_matches) - sum(1 for r in verification_results if r['verified'])}")

# Use OpenAI to rate relationships between the verified unique keys

# try:
#     matches_df = pd.read_csv('matches.csv')
# except:
#     openai_matches = get_openai_matches(potential_keys)  # Now using verified unique keys
#     print('\nRating relationships with OpenAI...')
    
#     # Create DataFrame with original field names (without table prefix)
#     matches_df = pd.DataFrame(openai_matches)
#     matches_df = matches_df[['table1', 'field1', 'table2', 'field2', 'strength']]

#     # Create display columns for viewing only
#     matches_df['display_field1'] = matches_df.apply(
#         lambda x: f"{x['table1']}.{x['field1']}" if x['field1'].lower() == 'id' else x['field1'], 
#         axis=1
#     )
#     matches_df['display_field2'] = matches_df.apply(
#         lambda x: f"{x['table2']}.{x['field2']}" if x['field2'].lower() == 'id' else x['field2'], 
#         axis=1
#     )

#     print('\nMatches DataFrame (sorted by strength):')
#     strength_order = ['very strong', 'strong', 'normal', 'weak', 'very weak']
#     matches_df['strength_rank'] = pd.Categorical(matches_df['strength'], categories=strength_order, ordered=True)
    
#     # Save the original fields (without display versions)
#     save_df = matches_df[['table1', 'field1', 'table2', 'field2', 'strength']].sort_values('strength_rank')
#     save_df.to_csv('matches.csv', index=False)
    
#     # Display with the formatted fields
#     display_df = matches_df.sort_values('strength_rank')[['table1', 'display_field1', 'table2', 'display_field2', 'strength']]
#     print(display_df.head())

# # Filter and verify matches
# min_strength = 'normal'  # Can be changed to 'strong' or 'very strong'
# filtered_matches = filter_matches_by_strength(matches_df, min_strength).reset_index(drop=True)
# print(f'\nFiltered Matches ({min_strength} or higher):')
# print(filtered_matches)

# print('\nVerifying matches in database...')
# verified_matches = find_matches(engine, filtered_matches, timeout_seconds=45)

# # Save verification results
# timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
# verified_matches.to_csv(f'verified_matches_{timestamp}.csv', index=False)
# verified_matches[verified_matches['verified']].to_csv(f'verified_matches_{timestamp}_successful_only.csv', index=False)

# print('\nVerified Matches Summary:')
# print('Status counts:')
# print(verified_matches['status'].value_counts())
# print('\nVerified matches with details:')
# successful_matches = verified_matches[verified_matches['verified']]
# if not successful_matches.empty:
#     for _, match in successful_matches.iterrows():
#         print(f"\n{match['table1']}.{match['field1']} -> {match['table2']}.{match['field2']}")
#         print(f"Strength: {match['strength']}")
#         print(f"Types match: {match.get('types_match', 'N/A')}")
#         print(f"Target is unique: {match.get('target_is_unique', 'N/A')}")
#         print(f"Referential integrity: {match.get('referential_integrity', 'N/A')}")
#         print(f"Cardinality ratio: {match.get('cardinality_ratio', 'N/A'):.2f}")
#         print(f"Non-null percentage: {match.get('non_null_percentage', 'N/A'):.1f}%")

# # print('\nUntracked Keys:')
# # untracked_keys = find_untracked_keys(potential_keys, openai_matches)
# # print(untracked_keys)

# # matches_df = find_matches(engine, potential_keys)
# # print(matches_df)

