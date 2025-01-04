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
        .force('collision', d3.forceCollide().radius(getCollisionRadius).strength(1).iterations(4));

    simulation.on('tick', () => {
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
        
        // Add key fields
        if (d.fields.pk) {
            node.append('text')
                .attr('class', 'field-text')
                .attr('y', y)
                .attr('text-anchor', 'middle')
                .text(`PK ${d.fields.pk}`)
                .style('fill', d.has_relationships ? 'var(--pk-color)' : 'var(--node-border-inactive)')
                .style('font-size', '12px');
            y += 20;
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
        });
        
        // Add separator line if expanded
        if (d.expanded && d.columns.length > 0) {
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
        }
        
        // Add columns if expanded
        if (d.expanded) {
            d.columns.forEach(col => {
                const isPK = col.key_type === 'PRI';
                const isFK = col.key_type === 'MUL';
                node.append('text')
                    .attr('class', 'column-text')
                    .attr('y', y)
                    .attr('text-anchor', 'middle')
                    .text(`${col.column_name} (${col.data_type})`)
                    .style('fill', isPK ? 'var(--pk-color)' : (isFK ? 'var(--fk-color)' : 'var(--text-color)'))
                    .style('font-size', '11px');
                y += 20;
            });
        }
    }
    
    node.each(function(d) { updateNodeContent(d3.select(this)); });
    
    // Handle click to expand/collapse
    node.on('click', function(event, d) {
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
        
        // Gently adjust simulation
        simulation.alpha(0.3).restart();
    });
    
    const tooltip = d3.select('#tooltip');
    
    // Node tooltips
    node.on('mouseover', function(event, d) {
        if (!d.expanded) {  // Only show tooltip when not expanded
            tooltip.style('display', 'block')
                .html(`<div class="title">${d.id}</div>${d.description}`)
                .style('left', (event.pageX + 10) + 'px')
                .style('top', (event.pageY + 10) + 'px');
        }
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
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    function dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    function dragended(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
    
    // Wait for simulation to settle before calculating initial zoom
    simulation.on('end', () => {
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
        
        svg.call(activeZoom.transform, transform);
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