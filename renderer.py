from pathlib import Path
import webbrowser
import json

def serve_html(file_path: str):
    """Serve the HTML file locally and open in browser"""
    # Convert to absolute file URL
    file_url = Path(file_path).absolute().as_uri()
    print(f"\nOpening diagram viewer in browser: {file_url}")
    webbrowser.open(file_url)

def generate_d3_data(matches, potential_keys, potential_foreign_keys=None, untracked_tables=None, table_descriptions=None, table_columns=None):
    """
    Generate data structure for D3.js visualization
    
    Args:
        matches: List of verified matches
        potential_keys: List of (table, field) tuples for potential primary keys
        potential_foreign_keys: List of (table, field) tuples for potential foreign keys
        untracked_tables: List of tables without identifiers
        table_descriptions: Dict of table descriptions
        table_columns: Dict of table columns
    """
    # First, create a mapping of tables to their primary keys
    table_pks = {table: field for table, field in potential_keys}
    
    nodes = {}
    links = []
    
    # Track used keys
    used_pks = set((match['table_pk'], match['field_pk']) for match in matches)
    used_fks = set((match['table_fk'], match['field_fk']) for match in matches)
    
    # Process verified matches
    for match in matches:
        # Add source node if not exists
        if match['table_pk'] not in nodes:
            nodes[match['table_pk']] = {
                'id': match['table_pk'],
                'description': table_descriptions.get(match['table_pk'], ''),
                'fields': {'pk': match['field_pk'], 'fks': []},
                'columns': table_columns.get(match['table_pk'], []) if table_columns else [],
                'has_relationships': True,
                'expanded': False
            }
        
        # Add target node if not exists
        if match['table_fk'] not in nodes:
            nodes[match['table_fk']] = {
                'id': match['table_fk'],
                'description': table_descriptions.get(match['table_fk'], ''),
                'fields': {
                    'pk': table_pks.get(match['table_fk'], 'null'),  # Use PK from mapping if available
                    'fks': [match['field_fk']]
                },
                'columns': table_columns.get(match['table_fk'], []) if table_columns else [],
                'has_relationships': True,
                'expanded': False
            }
        else:
            # Add FK to existing node
            if match['field_fk'] not in nodes[match['table_fk']]['fields']['fks']:
                nodes[match['table_fk']]['fields']['fks'].append(match['field_fk'])
        
        # Add link
        links.append({
            'source': match['table_pk'],
            'target': match['table_fk'],
            'sourceField': match['field_pk'],
            'targetField': match['field_fk']
        })
    
    # Add unused primary keys
    for table, field in potential_keys:
        if (table, field) not in used_pks:
            if table not in nodes:
                nodes[table] = {
                    'id': table,
                    'description': table_descriptions.get(table, ''),
                    'fields': {'pk': field, 'fks': []},
                    'columns': table_columns.get(table, []) if table_columns else [],
                    'has_relationships': False,
                    'expanded': False
                }
            else:
                nodes[table]['fields']['pk'] = field
    
    # Add unused foreign keys
    if potential_foreign_keys:
        for table, field in potential_foreign_keys:
            if (table, field) not in used_fks:
                if table not in nodes:
                    nodes[table] = {
                        'id': table,
                        'description': table_descriptions.get(table, ''),
                        'fields': {
                            'pk': table_pks.get(table, 'null'),  # Use PK from mapping if available
                            'fks': [field]
                        },
                        'columns': table_columns.get(table, []) if table_columns else [],
                        'has_relationships': False,
                        'expanded': False
                    }
                else:
                    if field not in nodes[table]['fields']['fks']:
                        nodes[table]['fields']['fks'].append(field)
    
    # Add untracked tables
    if untracked_tables:
        for table in untracked_tables:
            if table not in nodes:
                nodes[table] = {
                    'id': table,
                    'description': table_descriptions.get(table, ''),
                    'fields': {'pk': 'null', 'fks': []},
                    'columns': table_columns.get(table, []) if table_columns else [],
                    'has_relationships': False,
                    'expanded': False
                }
    
    return {
        'nodes': list(nodes.values()),
        'links': links
    }

def create_html_viewer(data, output_file, db_name=None):
    """Create an HTML file with D3.js visualization"""
    # Get the current file's directory
    current_dir = Path(__file__).parent
    
    # Read the template HTML file
    template_path = current_dir / 'templates' / 'database_viewer.html'
    with open(template_path, 'r') as f:
        html_content = f.read()
    
    # Convert data to JavaScript format and add database name
    data['db_name'] = db_name or ''
    js_data = json.dumps(data)
    
    # Replace the placeholder with actual data
    html_content = html_content.replace('DATA_PLACEHOLDER', js_data)
    
    # Create the output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write the HTML file
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    # Copy static files to the output directory
    output_static_dir = output_path.parent / 'static'
    template_static_dir = current_dir / 'templates' / 'static'
    
    # Create static directories
    (output_static_dir / 'js').mkdir(parents=True, exist_ok=True)
    (output_static_dir / 'css').mkdir(parents=True, exist_ok=True)
    
    # Copy JS and CSS files
    import shutil
    shutil.copy2(template_static_dir / 'js' / 'database_viewer.js', output_static_dir / 'js' / 'database_viewer.js')
    shutil.copy2(template_static_dir / 'css' / 'styles.css', output_static_dir / 'css' / 'styles.css')

def create_test_viewer(output_file: str = "test_viewer.html"):
    """Create a simple test HTML file with a basic D3.js visualization"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>D3.js Test</title>
        <script src="https://d3js.org/d3.v7.min.js"></script>
        <style>
            body {
                margin: 0;
                padding: 20px;
                font-family: Arial, sans-serif;
            }
            .circle {
                fill: steelblue;
                transition: fill 0.3s ease;
            }
            .circle:hover {
                fill: red;
            }
        </style>
    </head>
    <body>
        <h1>D3.js Test Visualization</h1>
        <div id="visualization"></div>
        
        <script>
            // Simple data
            const data = [
                {x: 100, y: 100, r: 30},
                {x: 200, y: 150, r: 40},
                {x: 300, y: 200, r: 50},
                {x: 400, y: 150, r: 40},
                {x: 500, y: 100, r: 30}
            ];
            
            // Create SVG
            const svg = d3.select('#visualization')
                .append('svg')
                .attr('width', 600)
                .attr('height', 300)
                .style('border', '1px solid black');
            
            // Add circles
            const circles = svg.selectAll('circle')
                .data(data)
                .join('circle')
                .attr('class', 'circle')
                .attr('cx', d => d.x)
                .attr('cy', d => d.y)
                .attr('r', d => d.r);
            
            // Add text to show D3.js is working
            svg.append('text')
                .attr('x', 300)
                .attr('y', 50)
                .attr('text-anchor', 'middle')
                .text('If you can see circles and this text, D3.js is working!');
        </script>
    </body>
    </html>
    """
    
    with open(output_file, 'w') as f:
        f.write(html_content) 