from pathlib import Path
import webbrowser

def create_html_viewer(markdown_file: str, output_file: str = "diagram_viewer.html"):
    """Create a standalone HTML file to view the Mermaid diagram with zoom/pan support"""
    with open(markdown_file, 'r') as f:
        md_content = f.read()
    
    # Debug print to check content
    print("\nDebug: Content being processed:")
    print(md_content[:500])  # Print first 500 chars
    
    # Properly escape the content for JavaScript
    md_content = (
        md_content
        .replace('\\', '\\\\')
        .replace('`', '\\`')
        .replace('${', '\\${')
        .replace('\n', '\\n')
    )
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Database Relationships</title>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: #fff;
            }}
            #content {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            #diagram {{
                margin-top: 40px;
                border-top: 1px solid #ddd;
                padding-top: 20px;
            }}
            .mermaid {{
                text-align: center;
            }}
            #zoom-controls {{
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: white;
                border-radius: 4px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.1);
                z-index: 1000;
                display: flex;
            }}
            #zoom-controls button {{
                border: 1px solid #ddd;
                background: white;
                padding: 8px 12px;
                font-size: 14px;
                cursor: pointer;
            }}
            #zoom-controls button:not(:last-child) {{
                border-right: none;
            }}
        </style>
    </head>
    <body>
        <div id="content"></div>
        <div id="zoom-controls">
            <button onclick="zoomIn()">+</button>
            <button onclick="resetZoom()">Reset</button>
            <button onclick="zoomOut()">−</button>
        </div>
        
        <script>
            // For debugging
            console.log("Raw content:", `{md_content}`);
            
            // Initialize mermaid
            mermaid.initialize({{ startOnLoad: false, theme: 'default' }});
            
            // Split content into descriptions and diagram
            const content = `{md_content}`;
            console.log("Content after template:", content);
            
            const [descriptions, diagramSection] = content.split('```mermaid');
            console.log("Descriptions:", descriptions);
            console.log("Diagram section:", diagramSection);
            
            const diagram = diagramSection.split('```')[0];
            console.log("Final diagram:", diagram);
            
            // Setup content
            const contentDiv = document.getElementById('content');
            
            // Add descriptions
            contentDiv.innerHTML = marked.parse(descriptions);
            
            // Add diagram container
            const diagramDiv = document.createElement('div');
            diagramDiv.id = 'diagram';
            contentDiv.appendChild(diagramDiv);
            
            // Render mermaid diagram
            mermaid.render('mermaid-diagram', diagram.trim()).then(result => {{
                diagramDiv.innerHTML = result.svg;
                
                // Setup zoom functionality
                const svg = diagramDiv.querySelector('svg');
                let scale = 1;
                
                function updateZoom() {{
                    svg.style.transform = `scale(${{scale}})`;
                    svg.style.transformOrigin = 'center';
                }}
                
                window.zoomIn = function() {{
                    scale = Math.min(5, scale + 0.2);
                    updateZoom();
                }};
                
                window.zoomOut = function() {{
                    scale = Math.max(0.1, scale - 0.2);
                    updateZoom();
                }};
                
                window.resetZoom = function() {{
                    scale = 1;
                    updateZoom();
                }};
                
                // Mouse wheel zoom
                diagramDiv.addEventListener('wheel', (e) => {{
                    e.preventDefault();
                    const delta = -Math.sign(e.deltaY) * 0.1;
                    scale = Math.min(Math.max(0.1, scale + delta), 5);
                    updateZoom();
                }});
            }}).catch(error => {{
                console.error('Mermaid rendering error:', error);
                diagramDiv.innerHTML = '<pre>' + diagram + '</pre>';
            }});
        </script>
    </body>
    </html>
    """
    
    with open(output_file, 'w') as f:
        f.write(html_content)
    
    # Debug print to verify file was written
    print(f"\nDebug: HTML file written to {output_file}")
    with open(output_file, 'r') as f:
        print("First 500 chars of generated HTML:")
        print(f.read()[:500])

def serve_html(file_path: str):
    """Serve the HTML file locally and open in browser"""
    # Convert to absolute file URL
    file_url = Path(file_path).absolute().as_uri()
    print(f"\nOpening diagram viewer in browser: {file_url}")
    webbrowser.open(file_url)

def generate_mermaid_diagram(verified_matches, primary_keys, filename="database_relationships.md", table_descriptions=None):
    """Generate a Mermaid entity-relationship diagram"""
    mermaid = [
        "# Database Schema Relationships\n",
        "```mermaid",
        "classDiagram",
        "    %% Style for tables",
        ""
    ]
    
    # Collect all tables and their fields
    tables = {}
    for table, field in primary_keys:
        if table not in tables:
            tables[table] = {'pk': field, 'fks': []}
    
    for match in verified_matches:
        fk_table = match['table_fk']
        if fk_table not in tables:
            tables[fk_table] = {'pk': None, 'fks': []}
        tables[fk_table]['fks'].append(match['field_fk'])
    
    # Add table nodes
    for table, fields in tables.items():
        table_def = [f"    class {table} {{"]
        if fields['pk']:
            table_def.append(f"        PK {fields['pk']}")
        if fields['fks']:
            for fk in fields['fks']:
                table_def.append(f"        FK {fk}")
        table_def.append("    }")
        mermaid.extend(table_def)
    
    # Add relationships
    mermaid.append("\n    %% Relationships")
    for match in verified_matches:
        mermaid.append(
            f"    {match['table_pk']} ..> {match['table_fk']} : {match['field_pk']} → {match['field_fk']}"
        )
    
    mermaid.append("```")
    
    with open(filename, 'w') as f:
        f.write('\n'.join(mermaid))
    
    return filename 