import shutil
from pathlib import Path
import zipfile
import os

def package_viewer(output_dir: Path) -> Path:
    """
    Package the database viewer files into a zip archive.
    
    Args:
        output_dir: Path to the directory containing the generated files
        
    Returns:
        Path to the created zip file
    """
    # Create a zip file with the same name as the output directory
    zip_path = output_dir.with_suffix('.zip')
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add the main HTML file
        html_file = output_dir / 'diagram_viewer.html'
        if html_file.exists():
            zipf.write(html_file, html_file.name)
        
        # Add the static directory
        static_dir = output_dir / 'static'
        if static_dir.exists():
            for root, _, files in os.walk(static_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(output_dir)
                    zipf.write(file_path, arcname)
        
        # Add the data files
        data_files = [
            'table_columns.csv',
            'table_descriptions.csv',
            'verified_relationships.csv'
        ]
        
        for file in data_files:
            file_path = output_dir / file
            if file_path.exists():
                zipf.write(file_path, file_path.name)
    
    return zip_path

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python package_viewer.py <output_directory>")
        sys.exit(1)
    
    output_dir = Path(sys.argv[1])
    if not output_dir.exists():
        print(f"Error: Directory {output_dir} does not exist")
        sys.exit(1)
    
    zip_path = package_viewer(output_dir)
    print(f"\nCreated package at: {zip_path}") 