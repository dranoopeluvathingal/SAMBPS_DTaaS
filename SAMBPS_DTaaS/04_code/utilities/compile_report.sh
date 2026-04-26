#!/bin/bash

# =============================================================================
# SAMBP Comprehensive Report Compilation Script
# 
# This script automates compilation of the SAMBP technical report with
# bibliography and proper LaTeX passes for reference resolution.
#
# Usage: ./compile_report.sh [options]
# Options:
#   --clean     Clean auxiliary files before compilation
#   --quick     Quick single-pass compilation (preview only)
#   --full      Full compilation with bibliography (default)
#   --draft     Compile in draft mode (faster, no PDFs embedded)
# =============================================================================

set -e  # Exit on error

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPORT_NAME="sambp_comprehensive_report"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/${REPORT_NAME}_compilation.log"

# Default options
CLEAN_FIRST=false
QUICK_MODE=false
DRAFT_MODE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_FIRST=true
            shift
            ;;
        --quick)
            QUICK_MODE=true
            shift
            ;;
        --draft)
            DRAFT_MODE=true
            shift
            ;;
        --full)
            QUICK_MODE=false
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# Functions
# =============================================================================

function print_header {
    echo -e "${BLUE}\\n===========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}===========================================${NC}\\n"
}

function print_success {
    echo -e "${GREEN}✓ $1${NC}"
}

function print_error {
    echo -e "${RED}✗ $1${NC}"
}

function print_warning {
    echo -e "${YELLOW}⚠ $1${NC}"
}

function print_info {
    echo -e "${BLUE}ℹ $1${NC}"
}

# =============================================================================
# Main Script
# =============================================================================

print_header "SAMBP Comprehensive Report Compilation Script"

# Check if LaTeX is installed
if ! command -v pdflatex &> /dev/null; then
    print_error "pdflatex not found. Please install LaTeX distribution."
    exit 1
fi
print_success "LaTeX found: $(pdflatex --version | head -1)"

# Check if bibtex is installed
if ! command -v bibtex &> /dev/null; then
    print_error "bibtex not found. Please install bibtex."
    exit 1
fi
print_success "BibTeX found: $(bibtex --version | head -1)"

# Change to script directory
cd "$SCRIPT_DIR"
print_info "Working directory: $SCRIPT_DIR"

# Clean auxiliary files if requested
if [ "$CLEAN_FIRST" = true ]; then
    print_header "Cleaning Auxiliary Files"
    rm -f ${REPORT_NAME}.aux ${REPORT_NAME}.log ${REPORT_NAME}.out ${REPORT_NAME}.toc \
          ${REPORT_NAME}.lof ${REPORT_NAME}.lot ${REPORT_NAME}.bbl ${REPORT_NAME}.blg \
          ${REPORT_NAME}.fls ${REPORT_NAME}.fdb_latexmk
    print_success "Auxiliary files cleaned"
fi

# Quick compilation mode
if [ "$QUICK_MODE" = true ]; then
    print_header "Quick Compilation (Single Pass)"
    print_warning "Note: Bibliography and references may not be complete in quick mode"
    
    pdflatex -interaction=nonstopmode -file-line-error ${REPORT_NAME}.tex > ${LOG_FILE} 2>&1
    
    if [ $? -eq 0 ]; then
        print_success "Quick compilation completed successfully"
        echo -e "\\n${GREEN}PDF generated: ${REPORT_NAME}.pdf${NC}"
    else
        print_error "Compilation failed. Check ${LOG_FILE} for details."
        tail -30 ${LOG_FILE}
        exit 1
    fi
    exit 0
fi

# Full compilation with bibliography
print_header "Full Compilation (with Bibliography)"

# Pass 1: Initial LaTeX run
print_info "Pass 1: Initial LaTeX run..."
pdflatex -interaction=nonstopmode -file-line-error ${REPORT_NAME}.tex > ${LOG_FILE} 2>&1
if [ $? -ne 0 ]; then
    print_error "LaTeX Pass 1 failed"
    tail -30 ${LOG_FILE}
    exit 1
fi
print_success "Pass 1 completed"

# BibTeX pass
print_info "Pass 2: Running BibTeX..."
bibtex ${REPORT_NAME} >> ${LOG_FILE} 2>&1
if [ $? -ne 0 ]; then
    print_warning "BibTeX finished with warnings (may be normal if no citations yet)"
fi
print_success "BibTeX completed"

# Pass 2: LaTeX with bibliography
print_info "Pass 3: LaTeX with bibliography..."
pdflatex -interaction=nonstopmode -file-line-error ${REPORT_NAME}.tex > ${LOG_FILE} 2>&1
if [ $? -ne 0 ]; then
    print_error "LaTeX Pass 3 failed"
    tail -30 ${LOG_FILE}
    exit 1
fi
print_success "Pass 3 completed"

# Pass 3: Final LaTeX for references
print_info "Pass 4: Final LaTeX pass (references)..."
pdflatex -interaction=nonstopmode -file-line-error ${REPORT_NAME}.tex > ${LOG_FILE} 2>&1
if [ $? -ne 0 ]; then
    print_error "LaTeX Pass 4 failed"
    tail -30 ${LOG_FILE}
    exit 1
fi
print_success "Pass 4 completed"

# Check if PDF was generated
if [ -f "${REPORT_NAME}.pdf" ]; then
    FILESIZE=$(du -h "${REPORT_NAME}.pdf" | cut -f1)
    print_success "PDF generated successfully"
    echo -e "\\n${GREEN}╔════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  Compilation Successful!              ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  Output File: ${REPORT_NAME}.pdf${NC}"
    echo -e "${GREEN}║  File Size:   ${FILESIZE}${NC}"
    echo -e "${GREEN}║  Location:    $(pwd)${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
    echo -e "\\n${YELLOW}Next Steps:${NC}"
    echo "  1. Review the PDF: ${REPORT_NAME}.pdf"
    echo "  2. Fill in placeholder results [RESULT PLACEHOLDER]"
    echo "  3. Add TikZ diagrams from diagrams_tikz/ folder"
    echo "  4. Recompile with: ./compile_report.sh"
else
    print_error "PDF not generated. Check ${LOG_FILE} for details."
    tail -50 ${LOG_FILE}
    exit 1
fi

# Compilation statistics
print_header "Compilation Statistics"
PAGES=$(pdfinfo "${REPORT_NAME}.pdf" 2>/dev/null | grep Pages | awk '{print $2}')
if [ ! -z "$PAGES" ]; then
    echo "Total pages: $PAGES"
else
    echo "(PDF info tool not available)"
fi
echo "Compilation date: $(date)"
echo "Log file: ${LOG_FILE}"

print_success "All done!"
