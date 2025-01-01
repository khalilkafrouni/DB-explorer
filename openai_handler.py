from typing import List, Dict, Any
import json
from openai import OpenAI
import tomli

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