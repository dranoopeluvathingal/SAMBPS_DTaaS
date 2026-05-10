MAIN    = main
LATEX   = pdflatex
BIBTEX  = bibtex
FLAGS   = -interaction=nonstopmode -halt-on-error

.PHONY: all clean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib
	$(LATEX) $(FLAGS) $(MAIN)
	$(BIBTEX) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)
	$(LATEX) $(FLAGS) $(MAIN)

clean:
	rm -f $(MAIN).{aux,bbl,blg,log,out,toc,lof,lot,fls,fdb_latexmk,synctex.gz}
