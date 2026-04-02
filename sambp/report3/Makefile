## Makefile — sambp TR-03/2026  (87T + 87L Differential Protection)

MAIN   = main_report3
LATEX  = pdflatex -interaction=nonstopmode
BIBTEX = bibtex
FIGDIR = figures

# Standalone TikZ figures
FIGS = $(FIGDIR)/fig_87T_system.pdf \
       $(FIGDIR)/fig_87L_system.pdf \
       $(FIGDIR)/fig_87T_characteristic.pdf \
       $(FIGDIR)/fig_87L_mode_fsm.pdf \
       $(FIGDIR)/fig_sambp_architecture.pdf

.PHONY: all report figures clean

all: report

figures: $(FIGS)

$(FIGDIR)/%.pdf: $(FIGDIR)/%.tex
	cd $(FIGDIR) && $(LATEX) $(notdir $<)

report: figures
	$(LATEX)  $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX)  $(MAIN)
	$(LATEX)  $(MAIN)

clean:
	rm -f *.aux *.bbl *.blg *.lof *.log *.lot *.out *.toc *.pdf
	rm -f $(FIGDIR)/*.aux $(FIGDIR)/*.log $(FIGDIR)/*.pdf
