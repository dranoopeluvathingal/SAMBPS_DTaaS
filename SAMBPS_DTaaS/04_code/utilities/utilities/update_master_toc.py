import os
import ast
import pandas as pd

def get_stats(filepath):
    """Extracts first-line docstring and counts source lines of code."""
    doc = "No description provided."
    sloc = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            # Extract Docstring
            tree = ast.parse(content)
            doc = ast.get_docstring(tree) or doc
            # Count logical lines (ignore empty and comments)
            lines = content.splitlines()
            sloc = len([l for l in lines if l.strip() and not l.strip().startswith('#')])
    except Exception:
        doc = "Extraction error."
    return doc.split('\n')[0], sloc

def generate_modular_toc(root_dir='.'):
    """Generates a structured Markdown TOC based on organized folders."""
    # Functional priorities as defined in your organize_thesis.sh [cite: 2026-03-01]
    categories = {
        'core_engines': '🧠 Primary Algorithmic Logic',
        'analytics_validation': '⚖️ Performance Audits & Metrics',
        'data_processing': '📊 Synthetic Data & Signal Gen',
        'visualization': '🎨 High-Res Thesis Assets',
        'presentation_delivery': '📁 Defense & Synopsis Tools'
    }
    
    markdown_out = f"# 📚 Master Table of Contents: PhD Empire\n"
    markdown_out += f"**Candidate:** Dr. Anoop Eluvathingal | **Date:** 2026-03-17\n\n---\n"
    
    total_sloc = 0
    
    for folder, description in categories.items():
        folder_path = os.path.join(root_dir, folder)
        if not os.path.exists(folder_path): continue
        
        markdown_out += f"## {description} (`/{folder}`)\n"
        markdown_out += "| File | SLOC | Technical Responsibility |\n"
        markdown_out += "| :--- | :--- | :--- |\n"
        
        cat_sloc = 0
        # Sort files to maintain "Empire Builder" order
        files = sorted([f for f in os.listdir(folder_path) if f.endswith('.py')])
        
        for file in files:
            doc, sloc = get_stats(os.path.join(folder_path, file))
            markdown_out += f"| `{file}` | {sloc} | {doc} |\n"
            cat_sloc += sloc
            
        markdown_out += f"| **SUBTOTAL** | **{cat_sloc}** | |\n\n"
        total_sloc += cat_sloc

    markdown_out += f"---\n**Total Verified Empire Scale:** {total_sloc} Source Lines of Code.\n"
    
    with open("MASTER_TOC.md", "w") as f:
        f.write(markdown_out)
    print(f"SUCCESS: MASTER_TOC.md updated. Total: {total_sloc} SLOC.")

if __name__ == "__main__":
    generate_modular_toc()