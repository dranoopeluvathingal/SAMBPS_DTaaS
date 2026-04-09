## Makefile — SAMBP TR-05/2026  (System Integration Study)

MAIN   = main_report5
LATEX  = pdflatex -interaction=nonstopmode
BIBTEX = bibtex
FIGDIR = figures

FIGS = figures/fig_system_topology.pdf \
       figures/fig_selectivity_matrix.pdf \
       figures/fig_sambp_pipeline.pdf

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
