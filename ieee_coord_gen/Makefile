# ============================================================
#  Makefile — ieee_coord_gen
#  Coordinated Adaptive OC Protection for Parallel SGs
# ============================================================

MAIN   = main
LATEX  = pdflatex
BIBTEX = bibtex
FLAGS  = -interaction=nonstopmode -halt-on-error

.PHONY: all clean distclean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib \
             diagrams/fig1_system.tex \
             diagrams/fig2_flowchart.tex \
             diagrams/fig3_pickup_bars.tex \
             diagrams/fig4_triptime_bars.tex \
             diagrams/fig5_margins.tex
	$(LATEX) $(FLAGS) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg \
	      $(MAIN).log $(MAIN).out $(MAIN).toc \
	      $(MAIN).fls $(MAIN).fdb_latexmk

distclean: clean
	rm -f $(MAIN).pdf
