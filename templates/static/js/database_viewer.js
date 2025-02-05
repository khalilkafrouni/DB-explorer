// Store zoom instance at module level
let activeZoom;

function initializeVisualization(data) {
    const width = window.innerWidth;
    const height = window.innerHeight - 60; // Adjust for header
    
    // Set database name
    document.getElementById('db-name').textContent = data.db_name || '';
    
    // Create permanent SVG to measure text width
    const measureSvg = d3.select('body')
        .append('svg')
        .attr('id', 'measure-svg')
        .style('visibility', 'hidden')
        .style('position', 'absolute')
        .style('pointer-events', 'none');
    
    // Function to measure text width
    function getTextWidth(text, fontSize = '14px') {
        const textElement = measureSvg
            .append('text')
            .style('font-size', fontSize)
            .style('font-family', "'JetBrains Mono', monospace")
            .text(text);
        const width = textElement.node().getBBox().width;
        textElement.remove();
        return width;
    }
    
    const svg = d3.select('#diagram')
        .append('svg')
        .attr('width', width)
        .attr('height', height);
    
    // Create and store zoom instance
    activeZoom = d3.zoom()
        .scaleExtent([0.1, 8])
        .on('zoom', (event) => {
            g.attr('transform', event.transform);
        });
    
    svg.call(activeZoom);
    
    const g = svg.append('g');
    
    // Function to identify clusters and their centers
    function updateClusters(nodes, links) {
        // Reset cluster assignments
        nodes.forEach(node => {
            node.cluster = null;
            node.isClusterCenter = false;
        });

        // Count connections for each node
        const connectionCounts = new Map();
        links.forEach(link => {
            const sourceId = link.source.id || link.source;
            const targetId = link.target.id || link.target;
            
            connectionCounts.set(sourceId, (connectionCounts.get(sourceId) || 0) + 1);
            connectionCounts.set(targetId, (connectionCounts.get(targetId) || 0) + 1);
        });

        // Identify cluster centers (nodes with 3+ connections)
        nodes.forEach(node => {
            if ((connectionCounts.get(node.id) || 0) >= 3) {
                node.isClusterCenter = true;
                node.cluster = node.id; // Use node's ID as cluster identifier
            }
        });

        // Assign nodes to clusters based on connections to cluster centers
        links.forEach(link => {
            const source = nodes.find(n => n.id === (link.source.id || link.source));
            const target = nodes.find(n => n.id === (link.target.id || link.target));
            
            if (source.isClusterCenter && !target.cluster) {
                target.cluster = source.id;
            } else if (target.isClusterCenter && !source.cluster) {
                source.cluster = target.id;
            }
        });
    }

    // Calculate collision radius function (for reuse)
    function getCollisionRadius(d) {
        // Base padding for all nodes
        const basePadding = 40;
        
        // Ensure dimensions are calculated
        if (!d.rectWidth || !d.rectHeight) {
            updateNodeDimensions(d);
        }
        
        // Calculate the current node dimensions
        const currentWidth = d.rectWidth || 250;
        const currentHeight = d.rectHeight + (d.expanded ? (d.columns?.length || 0) * 25 : 0);
        
        // Calculate the diagonal of the rectangle (distance from center to corner)
        const diagonal = Math.sqrt(Math.pow(currentWidth, 2) + Math.pow(currentHeight, 2)) / 2;
        
        // Add extra padding for expanded nodes
        const expansionPadding = d.expanded ? 60 : 30;
        
        // Return the total radius including padding
        return diagonal + basePadding + expansionPadding;
    }

    const simulation = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(data.links).id(d => d.id).distance(300))
        .force('charge', d3.forceManyBody()
            .strength(d => d.expanded ? -3000 : -1500)
            .distanceMin(200)
            .distanceMax(1000))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('x', d3.forceX(width / 2).strength(node => {
            return node.has_relationships ? 0.01 : 0.1;
        }))
        .force('y', d3.forceY(height / 2).strength(node => {
            return node.has_relationships ? 0.01 : 0.1;
        }))
        .force('collision', d3.forceCollide().radius(getCollisionRadius).strength(1).iterations(4))
        // Add clustering force
        .force('cluster', d3.forceRadial(100, width / 2, height / 2).strength(node => {
            if (!node.cluster) return 0;
            // Very subtle clustering force
            return 25.0;
        }))
        .alpha(1)           // Initial high energy
        .alphaDecay(0.1);   // Initial normal decay

    // Update clusters initially
    updateClusters(data.nodes, data.links);

    simulation.on('tick', () => {
        // Update cluster centers' positions
        data.nodes.forEach(node => {
            if (node.cluster && !node.isClusterCenter) {
                const center = data.nodes.find(n => n.id === node.cluster);
                if (center) {
                    // Very subtle direct position adjustment
                    const dx = center.x - node.x;
                    const dy = center.y - node.y;
                    node.x += dx * 0.05;  // Reduced from 0.2
                    node.y += dy * 0.05;  // Reduced from 0.2
                }
            }
        });

        link.attr('d', d => {
            const dx = d.target.x - d.source.x;
            const dy = d.target.y - d.source.y;
            const dr = Math.sqrt(dx * dx + dy * dy);
            return `M${d.source.x},${d.source.y}A${dr},${dr} 0 0,1 ${d.target.x},${d.target.y}`;
        });
        
        linkLabel.attr('transform', d => {
            const x = (d.source.x + d.target.x) / 2;
            const y = (d.source.y + d.target.y) / 2;
            return `translate(${x},${y})`;
        });
        
        node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
    
    const link = g.selectAll('.link')
        .data(data.links)
        .join('path')
        .attr('class', 'link');
    
    const linkLabel = g.selectAll('.link-label')
        .data(data.links)
        .join('text')
        .attr('class', 'link-label')
        .text(d => `${d.sourceField} → ${d.targetField}`);
    
    const node = g.selectAll('.node')
        .data(data.nodes)
        .join('g')
        .attr('class', 'node')
        .call(d3.drag()
            .on('start', dragstarted)
            .on('drag', dragged)
            .on('end', dragended));
    
    // Calculate rectangle dimensions based on content
    function updateNodeDimensions(d) {
        const numFields = (d.fields.pk ? 1 : 0) + d.fields.fks.length;
        const padding = 40;  // Padding inside rectangle
        const fieldHeight = 20;  // Height per field
        const titleHeight = 30;  // Height for title
        
        // Calculate width based on longest text
        const titleWidth = getTextWidth(d.id, '14px');  // Use larger font size for title
        console.log(`\nNode: ${d.id}`);
        console.log(`Title width: ${titleWidth} - "${d.id}"`);
        
        const textsToMeasure = [
            d.fields.pk ? `PK ${d.fields.pk}` : '',  // Primary key
            ...d.fields.fks.map(fk => `FK ${fk}`),  // Foreign keys
            ...(d.expanded ? d.columns.map(col => `${col.column_name} (${col.data_type})`) : [])  // Full column strings
        ].filter(Boolean);  // Remove empty strings
        
        // Log each text width
        const textWidths = textsToMeasure.map(text => ({
            text,
            width: getTextWidth(text, '12px')
        }));
        textWidths.forEach(({text, width}) => {
            console.log(`Text width: ${width} - "${text}"`);
        });
        
        // Get the maximum text width from fields and columns
        const maxContentWidth = Math.max(...textWidths.map(t => t.width));
        
        // Use the larger of title width or content width, plus padding
        d.rectWidth = Math.max(300, Math.max(titleWidth, maxContentWidth) + padding * 2);
        console.log(`Final rectangle width: ${d.rectWidth} (including ${padding * 2}px padding)\n`);
        
        // Calculate height including all elements
        d.rectHeight = titleHeight + (numFields * fieldHeight) + (padding * 2) + 
            (d.expanded ? (d.columns.length * fieldHeight + (d.columns.length > 0 ? 20 : 0)) : 0);  // Add extra space for separator
    }
    
    node.each(updateNodeDimensions);
    
    // Add rectangles to nodes with calculated dimensions
    node.append('rect')
        .attr('width', d => d.rectWidth)
        .attr('height', d => d.rectHeight)
        .attr('x', d => -d.rectWidth / 2)
        .attr('y', d => -d.rectHeight / 2)
        .style('stroke', d => d.has_relationships ? 'var(--node-border)' : 'var(--node-border-inactive)');
    
    // Add fields with proper positioning
    function updateNodeContent(node) {
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
        
        // Track shown columns to avoid duplication
        const shownColumns = new Set();
        
        // Add key fields and track them
        if (d.fields.pk) {
            node.append('text')
                .attr('class', 'field-text')
                .attr('y', y)
                .attr('text-anchor', 'middle')
                .text(`PK ${d.fields.pk}`)
                .style('fill', d.has_relationships ? 'var(--pk-color)' : 'var(--node-border-inactive)')
                .style('font-size', '12px');
            y += 20;
            shownColumns.add(d.fields.pk);
        }
        
        // Get all FK relationships for this node
        const connectedFks = new Set(data.links
            .filter(l => l.source.id === d.id || l.target.id === d.id)
            .map(l => l.source.id === d.id ? l.sourceField : l.targetField));
        
        d.fields.fks.forEach(fk => {
            node.append('text')
                .attr('class', 'field-text')
                .attr('y', y)
                .attr('text-anchor', 'middle')
                .text(`FK ${fk}`)
                .style('fill', connectedFks.has(fk) ? 'var(--fk-color)' : 'var(--node-border-inactive)')
                .style('font-size', '12px');
            y += 20;
            shownColumns.add(fk);
        });
        
        // Add separator line if expanded and there are columns to show
        if (d.expanded && d.columns.length > 0) {
            // Filter out columns that are already shown as PK or FK
            const remainingColumns = d.columns.filter(col => !shownColumns.has(col.column_name));
            
            if (remainingColumns.length > 0) {
                node.append('line')
                    .attr('class', 'field-text')
                    .attr('x1', -d.rectWidth/2 + 10)
                    .attr('x2', d.rectWidth/2 - 10)
                    .attr('y1', y + 5)
                    .attr('y2', y + 5)
                    .style('stroke', 'var(--node-border-inactive)')
                    .style('stroke-width', '1px')
                    .style('stroke-dasharray', '4,4');
                y += 25;
                
                // Add remaining columns
                remainingColumns.forEach(col => {
                    node.append('text')
                        .attr('class', 'column-text')
                        .attr('y', y)
                        .attr('text-anchor', 'middle')
                        .text(`${col.column_name} (${col.data_type})`)
                        .style('fill', 'var(--text-color)')
                        .style('font-size', '11px');
                    y += 20;
                });
            }
        }
    }
    
    node.each(function(d) { updateNodeContent(d3.select(this)); });
    
    // Handle click to expand/collapse
    node.on('click', function(event, d) {
        // Bring clicked node to front by moving it to the end of its parent container
        const clickedNode = this;
        clickedNode.parentNode.appendChild(clickedNode);

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
        
        // Find connected nodes
        const connectedNodes = new Set();
        data.links.forEach(link => {
            if (link.source.id === d.id) {
                connectedNodes.add(link.target);
            } else if (link.target.id === d.id) {
                connectedNodes.add(link.source);
            }
        });

        // Calculate new positions for connected nodes
        connectedNodes.forEach(connectedNode => {
            const dx = connectedNode.x - d.x;
            const dy = connectedNode.y - d.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            
            // Calculate minimum required distance based on both nodes' collision radii
            const minDistance = getCollisionRadius(d) + getCollisionRadius(connectedNode);
            
            // If nodes are too close, push the connected node outward
            if (distance < minDistance) {
                const scale = minDistance / (distance || 1); // Avoid division by zero
                const newX = d.x + dx * scale;
                const newY = d.y + dy * scale;
                
                // Store current position before updating
                const oldX = connectedNode.x;
                const oldY = connectedNode.y;
                
                // Update position with transition
                connectedNode.x = newX;
                connectedNode.y = newY;
                
                // If node was fixed, update fixed position too
                if (connectedNode.fx !== null) {
                    connectedNode.fx += (newX - oldX);
                }
                if (connectedNode.fy !== null) {
                    connectedNode.fy += (newY - oldY);
                }
            }
        });

        // Reset simulation with low energy and high decay for recalculations
        simulation
            .alpha(0.3)        // Low energy for subsequent updates
            .alphaDecay(0.2)   // Higher decay for faster stabilization
            .restart();
    });
    
    const tooltip = d3.select('#tooltip');
    
    // Node tooltips
    node.on('mouseover', function(event, d) {
        tooltip.style('display', 'block')
            .html(`<div class="title">${d.id}</div>${d.description}`)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY + 10) + 'px');
    })
    .on('mousemove', function(event) {
        tooltip.style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY + 10) + 'px');
    })
    .on('mouseout', function() {
        tooltip.style('display', 'none');
    });
    
    // Link tooltips
    link.on('mouseover', function(event, d) {
        tooltip.style('display', 'block')
            .html(`<strong>Relationship:</strong><div class="relationship">${d.source.id}.${d.sourceField}<br>↓<br>${d.target.id}.${d.targetField}</div>`)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY + 10) + 'px');
    })
    .on('mousemove', function(event) {
        tooltip.style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY + 10) + 'px');
    })
    .on('mouseout', function() {
        tooltip.style('display', 'none');
    });
    
    function dragstarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.1).restart();  // Reduced alpha target
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;

        // Find connected nodes
        const connectedNodes = new Set();
        data.links.forEach(link => {
            if (link.source.id === d.id) {
                connectedNodes.add(link.target);
            } else if (link.target.id === d.id) {
                connectedNodes.add(link.source);
            }
        });

        // Move connected nodes with dampened movement (30% of the main node's movement)
        const damping = 0.3;
        connectedNodes.forEach(connectedNode => {
            if (!connectedNode.fx && !connectedNode.fy) {  // Only move nodes that aren't being dragged
                const dx = event.x - d.x;
                const dy = event.y - d.y;
                connectedNode.x += dx * damping;
                connectedNode.y += dy * damping;
            }
        });
    }
    
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        // Keep the node fixed at its final position
        d.fx = d.x;
        d.fy = d.y;

        // Reset any temporary position adjustments on connected nodes
        data.links.forEach(link => {
            const connectedNode = link.source.id === d.id ? link.target : (link.target.id === d.id ? link.source : null);
            if (connectedNode && !connectedNode.fx && !connectedNode.fy) {
                // Only reset if the node isn't being dragged
                connectedNode.fx = null;
                connectedNode.fy = null;
            }
        });
    }
    
    // Remove auto-zoom on simulation end
    simulation.on('end', () => {
        // Do nothing, let user control zoom
    });
}

// Update zoom control functions to use activeZoom
window.zoomIn = function() {
    const svg = d3.select('#diagram svg');
    svg.transition().duration(300).call(activeZoom.scaleBy, 1.2);
};

window.zoomOut = function() {
    const svg = d3.select('#diagram svg');
    svg.transition().duration(300).call(activeZoom.scaleBy, 0.8);
};

window.resetZoom = function() {
    const svg = d3.select('#diagram svg');
    svg.transition().duration(300).call(activeZoom.transform, d3.zoomIdentity);
}; 