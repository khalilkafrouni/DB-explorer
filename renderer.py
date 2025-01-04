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
    import json
    
    # Convert data to proper JavaScript format
    js_data = json.dumps(data)
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Database Relationships</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #ffffff;
            --text-color: #2d3436;
            --header-bg: rgba(45, 52, 54, 0.95);
            --header-text: #ffffff;
            --node-bg: #ffffff;
            --node-border: #2d3436;
            --node-border-inactive: #95a5a6;
            --link-color: #636e72;
            --pk-color: #2980b9;
            --fk-color: #c0392b;
            --tooltip-bg: rgba(45, 52, 54, 0.95);
            --tooltip-text: #ffffff;
            --controls-bg: #ffffff;
            --controls-hover: #f1f2f6;
            --controls-border: #dfe6e9;
            --column-bg: rgba(45, 52, 54, 0.05);
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg-color: #1a1a1a;
                --text-color: #ecf0f1;
                --header-bg: rgba(30, 30, 30, 0.95);
                --header-text: #ecf0f1;
                --node-bg: #2d3436;
                --node-border: #ecf0f1;
                --node-border-inactive: #636e72;
                --link-color: #95a5a6;
                --pk-color: #3498db;
                --fk-color: #e74c3c;
                --tooltip-bg: rgba(30, 30, 30, 0.95);
                --tooltip-text: #ecf0f1;
                --controls-bg: #2d3436;
                --controls-hover: #34495e;
                --controls-border: #4a4a4a;
                --column-bg: rgba(255, 255, 255, 0.05);
            }}
        }}

        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: 'JetBrains Mono', monospace;
            background-color: var(--bg-color);
            color: var(--text-color);
        }}
        #header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            background: var(--header-bg);
            color: var(--header-text);
            padding: 16px;
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            z-index: 1000;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }}
        #diagram {{
            width: 100%;
            height: 100%;
            background: var(--bg-color);
            padding-top: 60px; /* Make space for header */
        }}
        .node rect {{
            fill: var(--node-bg);
            stroke-width: 2px;
            cursor: pointer;
            rx: 4;
            ry: 4;
        }}
        .node text {{
            font-size: 12px;
            pointer-events: none;
            fill: var(--text-color);
        }}
        .link {{
            fill: none;
            stroke: var(--link-color);
            stroke-width: 1.5px;
            stroke-dasharray: 5,5;
            cursor: pointer;
        }}
        .link-label {{
            font-size: 10px;
            fill: var(--link-color);
            text-anchor: middle;
            pointer-events: none;
        }}
        #tooltip {{
            position: absolute;
            display: none;
            background: var(--tooltip-bg);
            color: var(--tooltip-text);
            padding: 12px 16px;
            border-radius: 6px;
            font-size: 12px;
            min-width: 200px;
            max-width: 500px;
            z-index: 1000;
            pointer-events: none;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
            word-wrap: break-word;
            white-space: pre-wrap;
        }}
        #tooltip .title {{
            font-weight: bold;
            font-size: 14px;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.2);
        }}
        #tooltip .relationship {{
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid rgba(255, 255, 255, 0.2);
            font-family: 'JetBrains Mono', monospace;
        }}
        .column-list {{
            font-size: 11px;
            background: var(--column-bg);
            padding: 4px 8px;
            margin: 2px 0;
            border-radius: 2px;
        }}
        .column-type {{
            color: var(--link-color);
            font-size: 10px;
        }}
        .column-pk {{
            color: var(--pk-color);
        }}
        .column-fk {{
            color: var(--fk-color);
        }}
        #zoom-controls {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: var(--controls-bg);
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
            z-index: 1000;
            display: flex;
            overflow: hidden;
        }}
        #zoom-controls button {{
            border: none;
            background: var(--controls-bg);
            color: var(--text-color);
            padding: 12px 16px;
            font-size: 16px;
            cursor: pointer;
            transition: background-color 0.2s;
        }}
        #zoom-controls button:hover {{
            background: var(--controls-hover);
        }}
        #zoom-controls button:not(:last-child) {{
            border-right: 1px solid var(--controls-border);
        }}
    </style>
</head>
<body>
    <div id="header">DB Explorer: {db_name}</div>
    <div id="diagram"></div>
    <div id="tooltip"></div>
    <div id="zoom-controls">
        <button onclick="zoomIn()">+</button>
        <button onclick="resetZoom()">Reset</button>
        <button onclick="zoomOut()">−</button>
    </div>
    
    <script>
        window.addEventListener('load', function() {{
            const data = {js_data};
            const width = window.innerWidth;
            const height = window.innerHeight - 60; // Adjust for header
            
            // Create temporary SVG to measure text width
            const measureSvg = d3.select('body')
                .append('svg')
                .style('visibility', 'hidden')
                .style('position', 'absolute');
            
            // Function to measure text width
            function getTextWidth(text, fontSize = '14px') {{
                const textElement = measureSvg
                    .append('text')
                    .style('font-size', fontSize)
                    .style('font-family', "'JetBrains Mono', monospace")
                    .text(text);
                const width = textElement.node().getBBox().width;
                textElement.remove();
                return width;
            }}
            
            const svg = d3.select('#diagram')
                .append('svg')
                .attr('width', width)
                .attr('height', height);
            
            const zoom = d3.zoom()
                .scaleExtent([0.1, 8])
                .on('zoom', (event) => {{
                    g.attr('transform', event.transform);
                }});
            
            svg.call(zoom);
            
            const g = svg.append('g');
            
            const simulation = d3.forceSimulation(data.nodes)
                .force('link', d3.forceLink(data.links).id(d => d.id).distance(250))
                .force('charge', d3.forceManyBody().strength(-2000))
                .force('center', d3.forceCenter(width / 2, height / 2))
                .force('x', d3.forceX(width / 2).strength(node => {{
                    return node.has_relationships ? 0.01 : 0.1;
                }}))
                .force('y', d3.forceY(height / 2).strength(node => {{
                    return node.has_relationships ? 0.01 : 0.1;
                }}))
                .force('collision', d3.forceCollide().radius(150));
            
            const link = g.selectAll('.link')
                .data(data.links)
                .join('path')
                .attr('class', 'link');
            
            const linkLabel = g.selectAll('.link-label')
                .data(data.links)
                .join('text')
                .attr('class', 'link-label')
                .text(d => `${{d.sourceField}} → ${{d.targetField}}`);
            
            const node = g.selectAll('.node')
                .data(data.nodes)
                .join('g')
                .attr('class', 'node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended));
            
            // Calculate rectangle dimensions based on content
            function updateNodeDimensions(d) {{
                const numFields = (d.fields.pk ? 1 : 0) + d.fields.fks.length;
                const padding = 20;  // Padding inside rectangle
                const fieldHeight = 20;  // Height per field
                const titleHeight = 30;  // Height for title
                
                // Calculate width based on longest text
                const textsToMeasure = [
                    d.id,
                    d.fields.pk ? `PK ${{d.fields.pk}}` : '',
                    ...d.fields.fks.map(fk => `FK ${{fk}}`),
                    ...(d.expanded ? d.columns.map(col => `${{col.column_name}} (${{col.data_type}})`) : [])
                ];
                
                const maxWidth = Math.max(...textsToMeasure.map(text => getTextWidth(text)));
                d.rectWidth = Math.max(200, maxWidth + 40);  // Minimum 200px, add padding
                d.rectHeight = titleHeight + (numFields * fieldHeight) + (padding * 2) + 
                    (d.expanded ? d.columns.length * fieldHeight : 0);
            }}
            
            node.each(updateNodeDimensions);
            
            // Remove temporary SVG
            measureSvg.remove();
            
            // Add rectangles to nodes with calculated dimensions
            node.append('rect')
                .attr('width', d => d.rectWidth)
                .attr('height', d => d.rectHeight)
                .attr('x', d => -d.rectWidth / 2)
                .attr('y', d => -d.rectHeight / 2)
                .style('stroke', d => d.has_relationships ? 'var(--node-border)' : 'var(--node-border-inactive)');
            
            // Add fields with proper positioning
            function updateNodeContent(node) {{
                // Remove existing content
                node.selectAll('.field-text').remove();
                node.selectAll('.column-text').remove();
                
                const d = node.datum();
                let y = -d.rectHeight/2 + 45;  // Start position after title
                
                // Add title first
                node.append('text')
                    .attr('class', 'field-text')
                    .attr('y', -d.rectHeight/2 + 20)
                    .attr('text-anchor', 'middle')
                    .text(d.id)
                    .style('font-weight', 'bold')
                    .style('font-size', '14px')
                    .style('fill', d.has_relationships ? 'var(--text-color)' : 'var(--node-border-inactive)');
                
                // Add key fields
                if (d.fields.pk) {{
                    node.append('text')
                        .attr('class', 'field-text')
                        .attr('y', y)
                        .attr('text-anchor', 'middle')
                        .text(`PK ${{d.fields.pk}}`)
                        .style('fill', d.has_relationships ? 'var(--pk-color)' : 'var(--node-border-inactive)')
                        .style('font-size', '12px');
                    y += 20;
                }}
                
                // Get all FK relationships for this node
                const connectedFks = new Set(data.links
                    .filter(l => l.source.id === d.id || l.target.id === d.id)
                    .map(l => l.source.id === d.id ? l.sourceField : l.targetField));
                
                d.fields.fks.forEach(fk => {{
                    node.append('text')
                        .attr('class', 'field-text')
                        .attr('y', y)
                        .attr('text-anchor', 'middle')
                        .text(`FK ${{fk}}`)
                        .style('fill', connectedFks.has(fk) ? 'var(--fk-color)' : 'var(--node-border-inactive)')
                        .style('font-size', '12px');
                    y += 20;
                }});
                
                // Add separator line if expanded
                if (d.expanded && d.columns.length > 0) {{
                    node.append('line')
                        .attr('class', 'field-text')
                        .attr('x1', -d.rectWidth/2 + 10)
                        .attr('x2', d.rectWidth/2 - 10)
                        .attr('y1', y + 5)
                        .attr('y2', y + 5)
                        .style('stroke', 'var(--node-border-inactive)')
                        .style('stroke-width', '1px')
                        .style('stroke-dasharray', '4,4');
                    y += 15;
                }}
                
                // Add columns if expanded
                if (d.expanded) {{
                    d.columns.forEach(col => {{
                        const isPK = col.key_type === 'PRI';
                        const isFK = col.key_type === 'MUL';
                        node.append('text')
                            .attr('class', 'column-text')
                            .attr('y', y)
                            .attr('text-anchor', 'middle')
                            .text(`${{col.column_name}} (${{col.data_type}})`)
                            .style('fill', isPK ? 'var(--pk-color)' : (isFK ? 'var(--fk-color)' : 'var(--text-color)'))
                            .style('font-size', '11px');
                        y += 20;
                    }});
                }}
            }}
            
            node.each(function(d) {{ updateNodeContent(d3.select(this)); }});
            
            // Remove the separate table name addition since it's now part of updateNodeContent
            node.selectAll('.table-name').remove();
            
            // Handle click to expand/collapse
            node.on('click', function(event, d) {{
                d.expanded = !d.expanded;
                updateNodeDimensions(d);
                
                // Update rectangle size
                d3.select(this).select('rect')
                    .transition()
                    .duration(300)
                    .attr('width', d.rectWidth)
                    .attr('height', d.rectHeight)
                    .attr('x', -d.rectWidth / 2)
                    .attr('y', -d.rectHeight / 2);
                
                // Update content
                updateNodeContent(d3.select(this));
                
                // Restart simulation to adjust layout
                simulation.alpha(0.3).restart();
            }});
            
            const tooltip = d3.select('#tooltip');
            
            // Node tooltips
            node.on('mouseover', function(event, d) {{
                if (!d.expanded) {{  // Only show tooltip when not expanded
                    tooltip.style('display', 'block')
                        .html(`<div class="title">${{d.id}}</div>${{d.description}}`)
                        .style('left', (event.pageX + 10) + 'px')
                        .style('top', (event.pageY + 10) + 'px');
                }}
            }})
            .on('mousemove', function(event) {{
                tooltip.style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY + 10) + 'px');
            }})
            .on('mouseout', function() {{
                tooltip.style('display', 'none');
            }});
            
            // Link tooltips
            link.on('mouseover', function(event, d) {{
                tooltip.style('display', 'block')
                    .html(`<strong>Relationship:</strong><div class="relationship">${{d.source.id}}.${{d.sourceField}}<br>↓<br>${{d.target.id}}.${{d.targetField}}</div>`)
                    .style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY + 10) + 'px');
            }})
            .on('mousemove', function(event) {{
                tooltip.style('left', (event.pageX + 10) + 'px')
                    .style('top', (event.pageY + 10) + 'px');
            }})
            .on('mouseout', function() {{
                tooltip.style('display', 'none');
            }});
            
            simulation.on('tick', () => {{
                link.attr('d', d => {{
                    const dx = d.target.x - d.source.x;
                    const dy = d.target.y - d.source.y;
                    const dr = Math.sqrt(dx * dx + dy * dy);
                    return `M${{d.source.x}},${{d.source.y}}A${{dr}},${{dr}} 0 0,1 ${{d.target.x}},${{d.target.y}}`;
                }});
                
                linkLabel.attr('transform', d => {{
                    const x = (d.source.x + d.target.x) / 2;
                    const y = (d.source.y + d.target.y) / 2;
                    return `translate(${{x}},${{y}})`;
                }});
                
                node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
            }});
            
            function dragstarted(event, d) {{
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }}
            
            function dragged(event, d) {{
                d.fx = event.x;
                d.fy = event.y;
            }}
            
            function dragended(event, d) {{
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }}
            
            window.zoomIn = function() {{
                svg.transition().duration(300).call(zoom.scaleBy, 1.2);
            }};
            
            window.zoomOut = function() {{
                svg.transition().duration(300).call(zoom.scaleBy, 0.8);
            }};
            
            window.resetZoom = function() {{
                svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
            }};
            
            // Wait for simulation to settle before calculating initial zoom
            simulation.on('end', () => {{
                const bounds = g.node().getBBox();
                const fullWidth = width;
                const fullHeight = height;
                
                // Calculate scale with more padding (0.6 instead of 0.8)
                const scale = 0.6 / Math.max(
                    bounds.width / fullWidth,
                    bounds.height / fullHeight
                );
                
                const transform = d3.zoomIdentity
                    .translate(
                        fullWidth/2 - scale * (bounds.x + bounds.width/2),
                        fullHeight/2 - scale * (bounds.y + bounds.height/2)
                    )
                    .scale(scale);
                
                svg.call(zoom.transform, transform);
            }});
        }});
    </script>
</body>
</html>"""

    with open(output_file, 'w') as f:
        f.write(html_content)

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