# SAMBP Project - Publication Ready Package

This folder contains all necessary files for compiling and publishing the SAMBP (Stability-Aware Model-Based Protection) framework research.

## Files Overview

### Main Documents

1. **ieee_paper.tex**
   - Publication-ready IEEE Transactions paper
   - Format: Two-column journal article
   - Content: Novel methodology, validation results, performance metrics
   - Suitable for: IEEE Transactions on Power Delivery, IEEE Transactions on Power Systems
   - Compile with: `pdflatex ieee_paper.tex`

2. **sambp_full_report.tex**
   - Comprehensive technical report on the entire SAMBP framework
   - Format: Single-column technical report (IIT Madras template)
   - Content: Complete mathematical derivations, all three protection functions (87T, 87L, 87B), system integration
   - Use for: PhD thesis chapters, detailed reference documentation
   - Compile with: `pdflatex sambp_full_report.tex && bibtex sambp_full_report && pdflatex sambp_full_report.tex && pdflatex sambp_full_report.tex`

### Supporting Files

3. **sambp_references.bib**
   - Bibliography file for both documents
   - IEEE-formatted references
   - Used by: Both ieee_paper.tex and sambp_full_report.tex

4. **sambp_diagrams/** folder
   - Contains LaTeX source files for technical diagrams:
     - `inverse_estimation_diagram.tex` - Process flowchart
     - `87l_fsm_diagram.tex` - Communication fallback state machine
     - `transformer_model_diagram.tex` - Differential current components
   - Can be compiled standalone or included in documents

5. **figures/** folder
   - Additional figure files from the technical reports
   - Includes PDF and TeX sources from TR-03 through TR-09
   - Use for reference or include in presentations

## Compilation Instructions

### For IEEE Paper (Recommended for quick review)
```bash
pdflatex ieee_paper.tex
```

### For Comprehensive Report (With full bibliography)
```bash
pdflatex sambp_full_report.tex
bibtex sambp_full_report
pdflatex sambp_full_report.tex
pdflatex sambp_full_report.tex
```

### For Overleaf
1. Upload this entire folder to a new Overleaf project
2. Set **ieee_paper.tex** as the main document for journal publication
3. Or set **sambp_full_report.tex** as main for comprehensive documentation

## Key Results Highlighted

- **Perfect Discrimination**: TPR = 1.000, FPR = 0.000
- **Extended Testing**: 4000 Monte Carlo trials with ±30% impedance, ±60° phase perturbations
- **Three Protection Functions**: 87T (transformer), 87L (line), 87B (bus) differential protection
- **System Integration**: IEC 61850 GOOSE with <0.5 ms latency and 99.999% reliability

## Publication Targets

- IEEE Transactions on Power Delivery
- IEEE Transactions on Power Systems
- IEEE Transactions on Industrial Electronics

## Additional Resources

For detailed technical content on specific functions, see the companion technical reports:
- TR-03: Transformer & Line Differential Protection (87T, 87L)
- TR-04: Bus Differential Protection (87B)
- TR-05: System Integration Study
- TR-06: IEC 61850 GOOSE Integration
- TR-07: Hardware-in-the-Loop Validation
- TR-08: Monte Carlo Robustness Study (Nominal Bounds)
- TR-09: Final Validation with Extended Bounds (±30%/±60°)

## Contact

For questions about the SAMBP framework implementation and validation, refer to the accompanying technical reports or contact the research team at IIT Madras, Department of Electrical Engineering.

---

Last Updated: April 3, 2026
Package Version: 1.0 (Complete Publication Ready)