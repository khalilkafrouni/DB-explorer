from typing import List, Dict, Any
import json
from openai import OpenAI
import tomli
import pandas as pd
from typing import Dict, Set

with open("secrets.toml", "rb") as f:
    secrets = tomli.load(f)

# client = OpenAI(api_key=secrets['openai']['api_key'])  # Uncomment this line

def format_matches_for_openai(matches: List[Dict]) -> List[Dict]:
    """Convert FK-PK matches to format expected by OpenAI function"""
    return [
        {
            'table1': match['table_pk'],
            'field1': match['field_pk'],
            'table2': match['table_fk'],
            'field2': match['field_fk']
        }
        for match in matches
    ]

# Define the function that OpenAI will be forced to use
matches_function = {
    "name": "rate_matches",
    "description": "Returns strength ratings for each potential match",
    "parameters": {
        "type": "object",
        "properties": {
            "strengths": {
                "type": "array",
                "description": "Array of strength ratings for each match",
                "items": {
                    "type": "string",
                    "enum": ["very weak", "weak", "normal", "strong", "very strong"],
                    "description": "Strength rating based on naming patterns and database conventions"
                }
            }
        },
        "required": ["strengths"]
    }
}

def get_matches_from_openai(matches: List[Dict], client) -> List[str]:
    # Format matches to always include table names
    matches_text = "\n".join([
        f"{m['table1']}.{m['field1']} -> {m['table2']}.{m['field2']}"
        for m in matches
    ])
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": """Rate each potential database relationship:
            - very strong: Almost certain relationship (e.g., identical names, clear parent-child)
            - strong: High confidence in relationship
            - normal: Reasonable relationship possible
            - weak: Possible but unlikely relationship
            - very weak: Minimal indication of relationship"""},
            {"role": "user", "content": f"Rate the strength of these potential matches:\n{matches_text}"}
        ],
        functions=[matches_function],
        function_call={"name": "rate_matches"}
    )

    function_call = response.choices[0].message.function_call
    if function_call:
        result = json.loads(function_call.arguments)
        return result["strengths"]
    return ["weak"] * len(matches)  # fallback

def get_table_descriptions(engine, tables: Set[str], openai_client: OpenAI) -> Dict[str, str]:
    """Get OpenAI-generated descriptions for each table based on sample data"""
    descriptions = {}
    total_tables = len(tables)
    
    print(f"\nGetting descriptions for {total_tables} tables...")
    
    for i, table in enumerate(tables, 1):
        print(f"Processing table {i}/{total_tables}: {table}")
        # Get 5 sample rows
        try:
            sample_df = pd.read_sql_query(f"SELECT * FROM {table} LIMIT 5", con=engine)
            
            # Format the sample data for OpenAI
            sample_data = sample_df.to_string()
            
            # Create the prompt
            prompt = f"""Given this sample of 5 rows from the '{table}' table:

{sample_data}

Write a brief (max 2 lines) description of what kind of data this table contains. 
Focus on the business purpose of the table."""
            
            # Get description from OpenAI
            response = openai_client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=100
            )
            
            # Store the description
            description = response.choices[0].message.content.strip().replace('\n', ' ')
            descriptions[table] = description
            print(f"✓ Got description for {table}")
            
        except Exception as e:
            descriptions[table] = f"Error getting description: {str(e)}"
            print(f"✗ Error getting description for {table}: {str(e)}")
    
    print("\nFinished getting table descriptions")
    return descriptions