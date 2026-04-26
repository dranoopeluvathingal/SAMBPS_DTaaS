## Makefile — SAMBP TR-04/2026  (87B Bus Differential Protection)

MAIN   = main_report4
LATEX  = pdflatex -interaction=nonstopmode
BIBTEX = bibtex
FIGDIR = figures

FIGS = $(FIGDIR)/fig_87B_system.pdf \
       $(FIGDIR)/fig_87B_characteristic.pdf

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
