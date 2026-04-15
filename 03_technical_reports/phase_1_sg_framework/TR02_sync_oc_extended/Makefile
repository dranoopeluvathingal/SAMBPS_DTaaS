## Makefile — sambp_sync_oc Technical Report TR-02/2026

MAIN   = main_report2
LATEX  = pdflatex -interaction=nonstopmode
BIBTEX = bibtex
FIGDIR = figures

# Standalone TikZ figures
FIGS = $(FIGDIR)/fig_park_dq_model.pdf \
       $(FIGDIR)/fig_hif_study.pdf \
       $(FIGDIR)/fig_sequence_networks.pdf \
       $(FIGDIR)/fig_multi_gen_bus.pdf \
       $(FIGDIR)/fig_coordination_flowchart.pdf

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
