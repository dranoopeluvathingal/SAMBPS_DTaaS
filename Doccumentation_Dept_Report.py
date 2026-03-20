import os

def check_placeholders(root_dir='.'):
    """Identifies files still using the documentation placeholder."""
    target_folders = ['core_engines', 'analytics_validation', 'data_processing', 'visualization', 'presentation_delivery']
    placeholder = "[One-line technical summary"
    
    print(f"--- DOCUMENTATION AUDIT: PhD EMPIRE ---")
    print(f"| Folder | Pending File |")
    print(f"| :--- | :--- |")
    
    count = 0
    for folder in target_folders:
        folder_path = os.path.join(root_dir, folder)
        if not os.path.exists(folder_path): continue
        
        for file in os.listdir(folder_path):
            if file.endswith('.py'):
                with open(os.path.join(folder_path, file), 'r', encoding='utf-8') as f:
                    if placeholder in f.read():
                        print(f"| {folder} | `{file}` |")
                        count += 1
                        
    if count == 0:
        print(f"\n✅ ALL PROVINCES SECURED: No placeholders remaining.")
    else:
        print(f"\nTotal Pending: {count} files require technical summaries.")

if __name__ == "__main__":
    check_placeholders()