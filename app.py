from sqlalchemy import create_engine
import pandas as pd
import tomli
from typing import List, Dict, Set
from openai import OpenAI
from openai_handler import (
    get_matches_from_openai, 
    format_matches_for_openai,
    get_table_descriptions
)
from pathlib import Path
import shutil
from renderer import create_html_viewer, serve_html, generate_d3_data, create_test_viewer
from datetime import datetime
import os
from package_viewer import package_viewer
import argparse
from create_tables import generate_create_tables_sql

def create_output_directory(db_name: str) -> Path:
    """Create a timestamped output directory for the current run"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"{db_name}_{timestamp}")
    output_dir.mkdir(exist_ok=True)
    return output_dir

def initialize_engine(username, password, url, name, port):
    engine = create_engine(f'mysql+pymysql://{username}:{password}@{url}:{port}/{name}')
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

def is_auto_incrementing(table: str, field: str, engine) -> bool:
    """Check if field follows auto-increment pattern (each value = previous + 1)"""
    print('\tChecking auto-incrementing:', table, field)
    query = f"""
        WITH numbered AS (
            SELECT 
                {field},
                LAG({field}) OVER (ORDER BY {field}) as prev_value
            FROM {table}
            WHERE {field} IS NOT NULL
            ORDER BY {field}
        )
        SELECT 
            COUNT(*) as total_rows,
            SUM(CASE WHEN {field} = prev_value + 1 THEN 1 ELSE 0 END) as sequential_rows
        FROM numbered
        WHERE prev_value IS NOT NULL
    """
    try:
        result = get_query(query, engine).iloc[0]
        if result['total_rows'] == 0:
            return False
        # Consider it auto-incrementing if at least 95% of rows follow the pattern
        return (result['sequential_rows'] / result['total_rows']) > 0.95
    except Exception:
        return False

def find_potential_keys(engine):
    tables = get_all_tables(engine)
    primary_keys = []
    untracked_tables = []
    
    for table in tables['tables_in_database']:
        # First try to get defined primary keys that are auto-incrementing
        pk_columns = get_primary_keys(table, engine)
        
        if pk_columns:
            # Only add primary keys that are auto-incrementing
            for pk in pk_columns:
                if is_field_unique(table, pk, engine) and is_auto_incrementing(table, pk, engine):
                    primary_keys.append((table, pk))
            # If none of the primary keys are auto-incrementing, treat as untracked
            if not any((table, pk) in primary_keys for pk in pk_columns):
                untracked_tables.append(table)
            continue

        # Check for 'id' or 'ID' columns that are unique AND auto-incrementing
        columns = get_table_columns(table, engine)
        id_cols = columns[columns['Field'].str.lower() == 'id']['Field'].tolist()
        
        if id_cols:
            for id_col in id_cols:
                if is_field_unique(table, id_col, engine) and is_auto_incrementing(table, id_col, engine):
                    primary_keys.append((table, id_col))
                    break
            if table not in [pk[0] for pk in primary_keys]:
                untracked_tables.append(table)
            continue

        # If no primary key or 'id' field, look for auto-incrementing '*_id' fields
        id_like_cols = columns[
            columns['Field'].str.contains('_id', case=False) |
            columns['Field'].str.contains('ID', regex=False)
        ]['Field'].tolist()

        # Only accept auto-incrementing fields
        auto_inc_fields = [
            field for field in id_like_cols
            if is_field_unique(table, field, engine) and is_auto_incrementing(table, field, engine)
        ]
        
        if auto_inc_fields:
            # Add auto-incrementing fields
            for field in auto_inc_fields:
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

def generate_all_possible_matches(primary_keys, foreign_keys):
    """Generate all possible combinations between foreign keys and primary keys"""
    matches = []
    for pk_table, pk_field in primary_keys:
        for fk_table, fk_field in foreign_keys:
            if pk_table != fk_table:  # Avoid self-references
                matches.append({
                    'table_pk': pk_table,
                    'field_pk': pk_field,
                    'table_fk': fk_table,
                    'field_fk': fk_field
                })
    return matches

def verify_relationship(engine, table_pk, field_pk, table_fk, field_fk, threshold=0.1):
    """Verify if a foreign key actually points to a primary key"""
    try:
        # Check: Count distinct FK values not present in PK and calculate ratio
        integrity_check = get_query(f"""
            WITH invalid_fks AS (
                SELECT DISTINCT fk.{field_fk}
                FROM {table_fk} fk
                LEFT JOIN {table_pk} pk ON fk.{field_fk} = pk.{field_pk}
                WHERE fk.{field_fk} IS NOT NULL 
                AND pk.{field_pk} IS NULL
            )
            SELECT 
                COUNT(*) as invalid_distinct_count,
                (
                    SELECT COUNT(DISTINCT {field_fk})
                    FROM {table_fk}
                    WHERE {field_fk} IS NOT NULL
                ) as total_distinct_count
            FROM invalid_fks
        """, engine).iloc[0]
        
        invalid_count = integrity_check['invalid_distinct_count']
        total_distinct = integrity_check['total_distinct_count']
        invalid_ratio = invalid_count / total_distinct if total_distinct > 0 else 0
        
        if invalid_ratio > threshold:
            return {
                'verified': False,
                'reason': f"Found {invalid_count} distinct FK values ({invalid_ratio:.1%} of all distinct values) not present in PK"
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

def save_verified_matches(matches, verification_results, potential_keys=None, potential_foreign_keys=None, untracked_tables=None, filename="verified_relationships.csv"):
    """
    Save FK-PK relationships and their statistics to a CSV file, including unmatched and untracked tables
    
    Args:
        matches: List of verified matches
        verification_results: List of verification results
        potential_keys: List of (table, field) tuples for potential primary keys
        potential_foreign_keys: List of (table, field) tuples for potential foreign keys
        untracked_tables: List of tables without identifiers
        filename: Output CSV file
    """
    # First, save all verified relationships
    verified_data = []
    
    # Track which tables and keys are used in relationships
    used_pks = set()
    used_fks = set()
    tables_in_relationships = set()
    
    # Process verified matches
    for match, result in zip(matches, verification_results):
        data = {
            'table_name': match['table_pk'],
            'field_name': match['field_pk'],
            'field_type': 'PK',
            'relationship': f"→ {match['table_fk']}.{match['field_fk']}",
            'verified': result['verified'],
            'status': 'verified' if result['verified'] else result['reason']
        }
        
        if result['verified']:
            data.update({
                'referential_integrity': True,
                'null_percentage': result['stats']['null_percentage'],
                'distinct_values_source': result['stats']['distinct_values_pk'],
                'distinct_values_target': result['stats']['distinct_values_fk'],
                'coverage': result['stats']['coverage']
            })
        else:
            data.update({
                'referential_integrity': False,
                'null_percentage': None,
                'distinct_values_source': None,
                'distinct_values_target': None,
                'coverage': None
            })
            
        verified_data.append(data)
        
        # Add FK entry
        fk_data = {
            'table_name': match['table_fk'],
            'field_name': match['field_fk'],
            'field_type': 'FK',
            'relationship': f"← {match['table_pk']}.{match['field_pk']}",
            'verified': result['verified'],
            'status': 'verified' if result['verified'] else result['reason'],
            'referential_integrity': data['referential_integrity'],
            'null_percentage': data['null_percentage'],
            'distinct_values_source': data['distinct_values_target'],
            'distinct_values_target': data['distinct_values_source'],
            'coverage': data['coverage']
        }
        verified_data.append(fk_data)
        
        # Track used keys and tables
        used_pks.add((match['table_pk'], match['field_pk']))
        used_fks.add((match['table_fk'], match['field_fk']))
        tables_in_relationships.add(match['table_pk'])
        tables_in_relationships.add(match['table_fk'])
    
    # Add unused primary keys if provided
    if potential_keys:
        for table, field in potential_keys:
            if (table, field) not in used_pks:
                verified_data.append({
                    'table_name': table,
                    'field_name': field,
                    'field_type': 'PK',
                    'relationship': 'No relationships',
                    'verified': False,
                    'status': 'unused primary key',
                    'referential_integrity': None,
                    'null_percentage': None,
                    'distinct_values_source': None,
                    'distinct_values_target': None,
                    'coverage': None
                })
                tables_in_relationships.add(table)
    
    # Add unused foreign keys if provided
    if potential_foreign_keys:
        for table, field in potential_foreign_keys:
            if (table, field) not in used_fks:
                verified_data.append({
                    'table_name': table,
                    'field_name': field,
                    'field_type': 'FK',
                    'relationship': 'No relationships',
                    'verified': False,
                    'status': 'unused foreign key',
                    'referential_integrity': None,
                    'null_percentage': None,
                    'distinct_values_source': None,
                    'distinct_values_target': None,
                    'coverage': None
                })
                tables_in_relationships.add(table)
    
    # Add untracked tables if provided
    if untracked_tables:
        for table in untracked_tables:
            if table not in tables_in_relationships:
                verified_data.append({
                    'table_name': table,
                    'field_name': None,
                    'field_type': None,
                    'relationship': None,
                    'verified': False,
                    'status': 'no identifiers detected',
                    'referential_integrity': None,
                    'null_percentage': None,
                    'distinct_values_source': None,
                    'distinct_values_target': None,
                    'coverage': None
                })
    
    df = pd.DataFrame(verified_data)
    df.to_csv(filename, index=False)
    return filename

def read_verified_matches(csv_file):
    """Read and parse verified matches from CSV file"""
    df = pd.read_csv(csv_file)
    verified_matches = []
    
    # First get all PK entries
    pk_df = df[df['field_type'] == 'PK']
    for _, pk_row in pk_df.iterrows():
        if pd.isna(pk_row['relationship']) or pk_row['relationship'] == 'No relationships':
            continue
            
        # Extract FK info from relationship string (format: "→ table.field")
        try:
            fk_info = pk_row['relationship'].split(' ')[1]  # Get "table.field"
            fk_table, fk_field = fk_info.split('.')
            
            match = {
                'table_pk': pk_row['table_name'],
                'field_pk': pk_row['field_name'],
                'table_fk': fk_table,
                'field_fk': fk_field
            }
            verified_matches.append(match)
        except (IndexError, ValueError):
            print(f"Warning: Could not parse relationship '{pk_row['relationship']}' for {pk_row['table_name']}.{pk_row['field_name']}")
    
    # Get unique primary keys
    potential_keys = set(
        (row['table_name'], row['field_name'])
        for _, row in df[df['field_type'] == 'PK'].iterrows()
    )
    
    # Get unique foreign keys
    potential_foreign_keys = set(
        (row['table_name'], row['field_name'])
        for _, row in df[df['field_type'] == 'FK'].iterrows()
    )
    
    # Get untracked tables
    untracked_tables = [
        row['table_name']
        for _, row in df[df['status'] == 'no identifiers detected'].iterrows()
    ]
    
    return verified_matches, potential_keys, potential_foreign_keys, untracked_tables

def get_and_save_table_descriptions(engine, tables, openai_client, filename="table_descriptions.csv"):
    """
    Get descriptions for all tables and save them to a CSV file
    
    Args:
        engine: SQLAlchemy engine
        tables: Set of table names
        openai_client: OpenAI client instance
        filename: Output CSV file name
    
    Returns:
        Dict[str, str]: Dictionary of table descriptions
    """
    # Get descriptions
    table_descriptions = get_table_descriptions(engine, tables, openai_client)
    
    # Save to CSV
    df = pd.DataFrame([
        {'table': table, 'description': desc}
        for table, desc in table_descriptions.items()
    ])
    df.to_csv(filename, index=False)
    print(f"\nTable descriptions saved to: {filename}")
    
    return table_descriptions

def get_all_table_columns(engine, output_file: str = "table_columns.csv"):
    """
    Get all columns for each table in the database and save to CSV
    
    Args:
        engine: SQLAlchemy engine
        output_file: Path to save the CSV file
    """
    tables = get_all_tables(engine)
    table_columns = []
    
    for table in tables['tables_in_database']:
        columns = get_table_columns(table, engine)
        for _, column in columns.iterrows():
            table_columns.append({
                'table_name': table,
                'column_name': column['Field'],
                'data_type': column['Type'],
                'is_nullable': column['Null'],
                'key_type': column['Key'],
                'default_value': column['Default'],
                'extra': column['Extra']
            })
    
    df = pd.DataFrame(table_columns)
    df.to_csv(output_file, index=False)
    print(f"\nSaved table columns to: {output_file}")
    return df

def main(csv_file: str = None, should_package: bool = False):
    """
    Main function to analyze database relationships or plot from existing CSV
    
    Args:
        csv_file (str, optional): Path to CSV file containing verified relationships
        should_package (bool, optional): Whether to create a shareable package
    """
    # Initialize OpenAI client first (we'll need it in both paths)
    with open("secrets.toml", "rb") as f:
        secrets = tomli.load(f)
    
    openai_client = OpenAI(api_key=secrets['openai']['api_key'])
    
    if csv_file:
        # Read relationships from CSV
        csv_path = Path(csv_file)
        verified_matches, potential_keys, potential_foreign_keys, untracked_tables = read_verified_matches(csv_file)
        
        # Initialize database connection to get table descriptions
        engine = initialize_engine(
            secrets['db']['username'],
            secrets['db']['password'],
            secrets['db']['url'],
            secrets['db']['name'],
            secrets['db']['port']
        )
        
        # Get all unique tables
        all_tables = set(match['table_pk'] for match in verified_matches) | set(match['table_fk'] for match in verified_matches)
        
        # Add tables without relationships
        all_tables.update(table for table, _ in potential_keys)
        all_tables.update(table for table, _ in potential_foreign_keys)
        all_tables.update(untracked_tables)
        
        # Get table descriptions from saved file or generate new ones
        desc_file = csv_path.parent / "table_descriptions.csv"
        if desc_file.exists():
            desc_df = pd.read_csv(desc_file)
            table_descriptions = dict(zip(desc_df['table'], desc_df['description']))
            print(f"\nLoaded table descriptions from {desc_file}")
        else:
            print(f"\nWarning: Could not find {desc_file}, generating new descriptions...")
            table_descriptions = get_and_save_table_descriptions(engine, all_tables, openai_client)
        
        # Get table columns from saved file or generate new ones
        columns_file = csv_path.parent / "table_columns.csv"
        if columns_file.exists():
            print(f"\nLoaded table columns from {columns_file}")
            columns_df = pd.read_csv(columns_file)
            table_columns = {
                table: columns_df[columns_df['table_name'] == table].to_dict('records')
                for table in all_tables
            }
        else:
            print(f"\nWarning: Could not find {columns_file}, retrieving table columns...")
            columns_df = get_all_table_columns(engine, columns_file)
            table_columns = {
                table: columns_df[columns_df['table_name'] == table].to_dict('records')
                for table in all_tables
            }
        
        # Generate D3.js data and create HTML viewer
        d3_data = generate_d3_data(
            verified_matches, 
            potential_keys,
            potential_foreign_keys=potential_foreign_keys,
            untracked_tables=untracked_tables,
            table_descriptions=table_descriptions,
            table_columns=table_columns
        )
        html_file = csv_path.parent / "diagram_viewer.html"
        create_html_viewer(d3_data, html_file, db_name=secrets['db']['name'])
        
        # Create a package for sharing if requested
        if should_package:
            zip_path = package_viewer(csv_path.parent)
            print(f"\nCreated shareable package at: {zip_path}")
        
        serve_html(html_file)
        return

    # Initialize database connection
    with open("secrets.toml", "rb") as f:
        secrets = tomli.load(f)

    username = secrets['db']['username']
    password = secrets['db']['password']
    url = secrets['db']['url']
    name = secrets['db']['name']
    port = secrets['db']['port']

    engine = initialize_engine(username, password, url, name, port)

    # Create output directory
    output_dir = create_output_directory(name)
    print(f"\nCreated output directory: {output_dir}")

    # Get and save all table columns
    columns_file = output_dir / "table_columns.csv"
    get_all_table_columns(engine, columns_file)

    # 1. Find potential keys
    potential_keys, untracked_tables = find_potential_keys(engine)
    potential_foreign_keys = find_potential_foreign_keys(engine, potential_keys)

    print("\nPotential primary keys found:", len(potential_keys))
    for table, field in potential_keys:
        print(f"- {table}.{field}")

    print("\nPotential foreign keys found:", len(potential_foreign_keys))
    for table, field in potential_foreign_keys:
        print(f"- {table}.{field}")

    # 2. Generate potential matches using naming patterns
    potential_matches = generate_fk_pk_matches(potential_keys, potential_foreign_keys)

    print(f"\nFound {len(potential_matches)} potential relationships to verify")

    # 3. Verify relationships
    verified_matches = []
    verification_results = []

    for match in potential_matches:
        result = verify_relationship(
            engine,
            match['table_pk'],
            match['field_pk'],
            match['table_fk'],
            match['field_fk']
        )
        
        print(f"\n{match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']}")
        if result['verified']:
            verified_matches.append(match)
            verification_results.append(result)
            stats = result['stats']
            print("✓ Verified")
            print(f"- Null percentage: {stats['null_percentage']:.1f}%")
            print(f"- Distinct values: FK={stats['distinct_values_fk']}, PK={stats['distinct_values_pk']}")
            print(f"- PK coverage: {stats['coverage']:.1f}%")
        else:
            print("✗ Failed:", result['reason'])

    # 4. Save results
    if verified_matches:
        csv_filename = save_verified_matches(
            verified_matches, 
            verification_results,
            potential_keys=potential_keys,
            potential_foreign_keys=potential_foreign_keys,
            untracked_tables=untracked_tables,
            filename=output_dir / "verified_relationships.csv"
        )
        print(f"\nVerified relationships saved to: {csv_filename}")

    # 5. Print detailed summary
    print(f"\nSummary:")
    print(f"Total potential primary keys: {len(potential_keys)}")
    print(f"Total potential foreign keys: {len(potential_foreign_keys)}")
    print(f"Total potential relationships: {len(potential_matches)}")
    print(f"Verified relationships: {len(verified_matches)}")
    print(f"Tables without unique identifiers: {len(untracked_tables)}")

    # Print verified relationships
    print("\nVerified Relationships:")
    for match in verified_matches:
        print(f"✓ {match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']}")

    # Find and print unused primary keys
    used_pks = set((match['table_pk'], match['field_pk']) for match in verified_matches)
    unused_pks = [(table, field) for table, field in potential_keys if (table, field) not in used_pks]
    print("\nUnused Primary Keys:")
    for table, field in unused_pks:
        print(f"- {table}.{field}")

    # Find and print unused foreign keys
    used_fks = set((match['table_fk'], match['field_fk']) for match in verified_matches)
    unused_fks = [(table, field) for table, field in potential_foreign_keys if (table, field) not in used_fks]
    print("\nUnused Foreign Keys:")
    for table, field in unused_fks:
        print(f"- {table}.{field}")

    # Generate new potential matches from unused keys
    print("\nAnalyzing remaining possible relationships...")
    remaining_matches = generate_all_possible_matches(unused_pks, unused_fks)  # Use the new function here

    if remaining_matches:
        # Initialize OpenAI client
        openai_client = OpenAI(api_key=secrets['openai']['api_key'])
        
        # Get OpenAI strength ratings
        openai_formatted_matches = format_matches_for_openai(remaining_matches)
        strengths = get_matches_from_openai(openai_formatted_matches, openai_client)

        # Filter for strong matches only
        strong_matches = []
        for match, strength in zip(remaining_matches, strengths):
            if strength in {'normal', 'strong', 'very strong'}:
                strong_matches.append((match, strength))

        if strong_matches:
            print("\nVerifying promising relationships found between unused keys:")
            print(strong_matches)
            for match, strength in strong_matches:
                print(f"\nChecking {match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']} ({strength})")
                
                result = verify_relationship(
                    engine,
                    match['table_pk'],
                    match['field_pk'],
                    match['table_fk'],
                    match['field_fk']
                )
                
                if result['verified']:
                    verified_matches.append(match)
                    verification_results.append(result)
                    stats = result['stats']
                    print("✓ Verified")
                    print(f"- Null percentage: {stats['null_percentage']:.1f}%")
                    print(f"- Distinct values: FK={stats['distinct_values_fk']}, PK={stats['distinct_values_pk']}")
                    print(f"- PK coverage: {stats['coverage']:.1f}%")
                else:
                    print("✗ Failed:", result['reason'])

            # Update the CSV file with all verified relationships
            if verified_matches:
                csv_filename = save_verified_matches(
                    verified_matches, 
                    verification_results,
                    potential_keys=potential_keys,
                    potential_foreign_keys=potential_foreign_keys,
                    untracked_tables=untracked_tables,
                    filename=output_dir / "verified_relationships.csv"
                )
                print(f"\nUpdated verified relationships saved to: {csv_filename}")
        else:
            print("\nNo promising relationships found between unused keys")
    else:
        print("\nNo additional potential relationships found between unused keys")

    # Print final summary of all verified relationships
    print(f"\nFinal Summary (including newly verified relationships):")
    print(f"Total verified relationships: {len(verified_matches)}")
    for match in verified_matches:
        print(f"✓ {match['table_pk']}.{match['field_pk']} <- {match['table_fk']}.{match['field_fk']}")

    # Before generating the final diagram, get table descriptions
    all_tables = set(table for table, _ in potential_keys) | set(match['table_fk'] for match in verified_matches)
    
    # Get table descriptions from saved file or generate new ones
    desc_file = output_dir / "table_descriptions.csv"
    table_descriptions = get_and_save_table_descriptions(engine, all_tables, openai_client, filename=desc_file)
    
    # Get table columns
    columns_file = output_dir / "table_columns.csv"
    columns_df = get_all_table_columns(engine, columns_file)
    table_columns = {
        table: columns_df[columns_df['table_name'] == table].to_dict('records')
        for table in all_tables
    }
    
    # Generate D3.js data and create HTML viewer
    d3_data = generate_d3_data(
        verified_matches, 
        potential_keys,
        potential_foreign_keys=potential_foreign_keys,
        untracked_tables=untracked_tables,
        table_descriptions=table_descriptions,
        table_columns=table_columns
    )
    html_file = output_dir / "diagram_viewer.html"
    create_html_viewer(d3_data, html_file, db_name=secrets['db']['name'])
    
    # Create a package for sharing if requested
    if should_package:
        zip_path = package_viewer(output_dir)
        print(f"\nCreated shareable package at: {zip_path}")
    
    serve_html(html_file)
    return

def main_cli():
    parser = argparse.ArgumentParser(description='Database Explorer CLI')
    parser.add_argument('--create-tables', action='store_true', help='Generate CREATE TABLE statements')
    parser.add_argument('--csv-dir', type=str, help='Directory containing CSV files', default=None)
    parser.add_argument('--wait-for-csv', action='store_true', help='Wait for CSV files if they don\'t exist')
    
    args = parser.parse_args()
    
    if args.create_tables:
        success = generate_create_tables_sql(args.csv_dir, args.wait_for_csv)
        if not success:
            print("Failed to create tables. Make sure the required CSV files exist.")
            return 1
    return 0

if __name__ == "__main__":
    exit(main_cli())
