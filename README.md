<img width="1530" alt="image" src="https://github.com/user-attachments/assets/dd5a7ca6-2053-4753-ad48-0849af70eb93" />

# DB Explorer

DB Explorer is a powerful tool that automatically analyzes MySQL database relationships and generates an interactive visualization of the database schema. It detects primary and foreign key relationships, verifies them through data analysis, and presents them in an intuitive, interactive diagram.

## Features

- **Automatic Relationship Detection**
  - Identifies primary keys based on uniqueness and auto-increment patterns
  - Discovers potential foreign keys through naming patterns
  - Verifies relationships through data analysis
  - Handles both explicit and implicit relationships

- **Interactive Visualization**
  - Dynamic force-directed graph layout
  - Zoom and pan functionality
  - Drag and drop nodes to rearrange
  - Expandable nodes showing full table structure
  - Hover tooltips with table descriptions and relationships
  - Connected nodes follow with dampened movement
  - Color-coded relationships:
    - Connected tables with black borders and text
    - Unconnected tables with grey borders and text
    - Used foreign keys in red
    - Unused foreign keys in grey
  - Automatic dark mode based on system preferences

- **Comprehensive Analysis**
  - Tracks both used and unused keys
  - Shows tables without detected identifiers
  - Provides detailed statistics about relationships
  - Exports findings to CSV for further analysis
  - AI-powered table descriptions

## Requirements

- Python 3.7+
- MySQL database
- Required Python packages (install via `pip install -r requirements.txt`):
  - SQLAlchemy
  - pandas
  - PyMySQL
  - openai
  - tomli

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd db-explorer
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `secrets.toml` file with your database and OpenAI credentials:
   ```toml
   [db]
   username = "your_username"
   password = "your_password"
   url = "localhost"
   name = "your_database"
   port = 3306

   [openai]
   api_key = "your_openai_api_key"
   ```

## Usage

1. Run the analysis:
   ```bash
   python app.py
   ```
   This will:
   - Analyze your database structure
   - Detect and verify relationships
   - Generate a visualization
   - Save results to `verified_relationships.csv`

2. View existing analysis:
   ```bash
   python app.py --csv verified_relationships.csv
   ```
   This will load previously saved analysis and show the visualization.

3. Refresh table descriptions:
   ```bash
   python app.py --refresh-descriptions
   ```
   This will regenerate AI-powered table descriptions.

4. Create a shareable package:
   ```bash
   python app.py --package
   ```
   This will:
   - Run the analysis (or use `--csv` to load existing analysis)
   - Create a zip file containing all necessary files for sharing
   - The recipient can extract the zip and open `diagram_viewer.html` in any modern browser

You can combine flags as needed:
```bash
python app.py --csv verified_relationships.csv --package  # Package existing analysis
python app.py --refresh-descriptions --package  # Fresh analysis with new descriptions and package
```

## How It Works

1. **Primary Key Detection**
   - Looks for defined primary keys
   - Identifies unique, auto-incrementing columns
   - Recognizes common naming patterns (id, *_id)

2. **Foreign Key Discovery**
   - Finds columns with ID-like names
   - Matches potential relationships based on naming
   - Verifies relationships through data analysis

3. **Relationship Verification**
   - Checks referential integrity
   - Analyzes data patterns
   - Calculates usage statistics

4. **Visualization**
   - Uses D3.js for interactive visualization
   - Implements force-directed layout with collision detection
   - Expandable nodes showing complete table structure
   - Connected nodes move together with dampened motion
   - Provides intuitive navigation and exploration
   - Supports system-based dark mode

## Interactive Features

- **Node Expansion**: Click on any node to expand it and view all columns
- **Node Dragging**: Drag nodes to rearrange the layout. Connected nodes will follow with dampened movement
- **Tooltips**: Hover over nodes to see table descriptions and relationship details
- **Zoom Controls**: Use the buttons in the bottom-right corner to zoom in/out or reset the view
- **Automatic Spacing**: Nodes automatically maintain proper spacing when expanded or collapsed

## Output Files

The tool generates several files in a timestamped directory:
- `verified_relationships.csv`: Detailed analysis of all relationships
- `table_descriptions.csv`: AI-generated descriptions of tables
- `table_columns.csv`: Complete listing of all table columns and their properties
- `diagram_viewer.html`: Interactive visualization of the database schema

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 
