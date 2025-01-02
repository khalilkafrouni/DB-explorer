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
  - Hover tooltips with table descriptions
  - Color-coded relationships:
    - Connected tables with black borders and text
    - Unconnected tables with grey borders and text
    - Used foreign keys in red
    - Unused foreign keys in grey

- **Comprehensive Analysis**
  - Tracks both used and unused keys
  - Shows tables without detected identifiers
  - Provides detailed statistics about relationships
  - Exports findings to CSV for further analysis

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
   [database]
   db_username = "your_username"
   db_password = "your_password"
   db_url = "localhost"
   db_name = "your_database"
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
   - Implements force-directed layout
   - Provides intuitive navigation and exploration

## Output Files

- `verified_relationships.csv`: Detailed analysis of all relationships
- `table_descriptions.csv`: AI-generated descriptions of tables
- `diagram_viewer.html`: Interactive visualization of the database schema

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 