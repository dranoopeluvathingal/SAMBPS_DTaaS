MAIN = main
LATEX = pdflatex -interaction=nonstopmode
BIBTEX = bibtex

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib figures/*.tex
	$(LATEX) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(MAIN)
	$(LATEX) $(MAIN)

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log \
	       $(MAIN).out $(MAIN).toc

distclean: clean
	rm -f $(MAIN).pdf
