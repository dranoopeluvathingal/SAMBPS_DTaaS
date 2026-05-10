MAIN = main_paper_c

.PHONY: all clean

all:
	pdflatex -interaction=nonstopmode $(MAIN)
	bibtex $(MAIN)
	pdflatex -interaction=nonstopmode $(MAIN)
	pdflatex -interaction=nonstopmode $(MAIN)

clean:
	rm -f $(MAIN).aux $(MAIN).bbl $(MAIN).blg $(MAIN).log \
	       $(MAIN).out $(MAIN).toc $(MAIN).pdf
