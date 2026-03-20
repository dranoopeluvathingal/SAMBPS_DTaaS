import os

def prepend_header(filepath, folder_name):
    """Prepends the Senior Scientist header if missing."""
    header_template = f'''"""
Description: [One-line technical summary of the file's primary responsibility]
Project: PhD Thesis - Physics-Informed Protection for IBR-Dominated Microgrids
Author: Dr. Anoop Eluvathingal (Senior Scientist)
Logic Layer: {folder_name.replace('_', ' ').title()}
"""

'''
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if file already starts with a docstring
        if content.strip().startswith('"""') or content.strip().startswith("'''"):
            print(f"Skipping: {filepath} (Already documented)")
            return False

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(header_template + content)
        print(f"Updated: {filepath} with professional header.")
        return True
    except Exception as e:
        print(f"Error updating {filepath}: {e}")
        return False

def run_mass_update(root_dir='.'):
    """Scans PhD directories and updates missing documentation headers."""
    target_folders = ['core_engines', 'analytics_validation', 'data_processing', 'visualization', 'presentation_delivery']
    count = 0
    
    for folder in target_folders:
        folder_path = os.path.join(root_dir, folder)
        if not os.path.exists(folder_path): continue
        
        for file in os.listdir(folder_path):
            if file.endswith('.py'):
                if prepend_header(os.path.join(folder_path, file), folder):
                    count += 1
                    
    print(f"\nSUCCESS: {count} files updated. Your Empire is now standardized.")

if __name__ == "__main__":
    run_mass_update()