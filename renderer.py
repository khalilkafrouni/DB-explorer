from pathlib import Path
import webbrowser

def create_html_viewer(markdown_file: str, output_file: str = "diagram_viewer.html"):
    """Create a standalone HTML file to view the Mermaid diagram with zoom/pan support"""
    with open(markdown_file, 'r') as f:
        md_content = f.read()
    
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
                margin: 0;
                padding: 0;
                overflow: hidden;
                height: 100vh;
                width: 100vw;
                font-family: Arial, sans-serif;
            }}
            #diagram {{
                width: 100vw;
                height: 100vh;
                cursor: grab;
                background: white;
            }}
            #diagram.panning {{
                cursor: grabbing;
            }}
            .mermaid {{
                width: 100%;
                height: 100%;
                display: flex;
                justify-content: center;
                align-items: center;
            }}
            .mermaid svg {{
                max-width: none;
                max-height: none;
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
        <div id="diagram"></div>
        <div id="zoom-controls">
            <button onclick="zoomIn()">+</button>
            <button onclick="resetZoom()">Reset</button>
            <button onclick="zoomOut()">−</button>
        </div>
        
        <script>
            // Initialize mermaid
            mermaid.initialize({{ startOnLoad: false, theme: 'default' }});
            
            // Get the diagram content
            const content = `{md_content}`;
            const diagram = content.split('```mermaid')[1].split('```')[0];
            
            // Render mermaid diagram
            mermaid.render('mermaid-diagram', diagram.trim()).then(result => {{
                const diagramDiv = document.getElementById('diagram');
                diagramDiv.innerHTML = result.svg;
                
                // Setup zoom and pan functionality
                const svg = diagramDiv.querySelector('svg');
                let scale = 1;
                let translateX = 0;
                let translateY = 0;
                let isDragging = false;
                let startX, startY;
                
                function updateTransform() {{
                    svg.style.transform = `translate(${{translateX}}px, ${{translateY}}px) scale(${{scale}})`;
                }}
                
                // Initial centering
                function centerDiagram() {{
                    const svgRect = svg.getBoundingClientRect();
                    const containerRect = diagramDiv.getBoundingClientRect();
                    
                    scale = Math.min(
                        containerRect.width / svgRect.width,
                        containerRect.height / svgRect.height
                    ) * 0.9;
                    
                    translateX = (containerRect.width - svgRect.width * scale) / 2;
                    translateY = (containerRect.height - svgRect.height * scale) / 2;
                    
                    updateTransform();
                }}
                
                // Center on load
                centerDiagram();
                
                window.zoomIn = function() {{
                    scale = Math.min(5, scale + 0.2);
                    updateTransform();
                }};
                
                window.zoomOut = function() {{
                    scale = Math.max(0.1, scale - 0.2);
                    updateTransform();
                }};
                
                window.resetZoom = function() {{
                    centerDiagram();
                }};
                
                // Mouse wheel zoom
                diagramDiv.addEventListener('wheel', (e) => {{
                    e.preventDefault();
                    const rect = diagramDiv.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    const y = e.clientY - rect.top;
                    
                    const delta = -Math.sign(e.deltaY) * 0.1;
                    const newScale = Math.min(Math.max(0.1, scale + delta), 5);
                    
                    // Adjust position to zoom toward mouse
                    if (newScale !== scale) {{
                        translateX = x - (x - translateX) * newScale / scale;
                        translateY = y - (y - translateY) * newScale / scale;
                        scale = newScale;
                        updateTransform();
                    }}
                }});
                
                // Pan functionality
                diagramDiv.addEventListener('mousedown', (e) => {{
                    isDragging = true;
                    diagramDiv.classList.add('panning');
                    startX = e.clientX - translateX;
                    startY = e.clientY - translateY;
                }});
                
                window.addEventListener('mousemove', (e) => {{
                    if (!isDragging) return;
                    translateX = e.clientX - startX;
                    translateY = e.clientY - startY;
                    updateTransform();
                }});
                
                window.addEventListener('mouseup', () => {{
                    isDragging = false;
                    diagramDiv.classList.remove('panning');
                }});
            }}).catch(error => {{
                console.error('Mermaid rendering error:', error);
                document.getElementById('diagram').innerHTML = '<pre>' + diagram + '</pre>';
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