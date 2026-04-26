PAPER    = main_paper
FIG_DIR  = figures
FIG_SRCS = $(wildcard $(FIG_DIR)/*.tex)
FIG_PDFS = $(FIG_SRCS:.tex=.pdf)
PDFLATEX = pdflatex -interaction=nonstopmode -halt-on-error

.PHONY: all paper figures clean

all: paper

paper: $(PAPER).pdf

$(PAPER).pdf: $(PAPER).tex references.bib $(FIG_PDFS)
	$(PDFLATEX) $(PAPER)
	-bibtex $(PAPER)
	$(PDFLATEX) $(PAPER)
	$(PDFLATEX) $(PAPER)
	@echo ">>> $(PAPER).pdf ready  ($$(du -h $(PAPER).pdf | cut -f1))"

$(FIG_DIR)/%.pdf: $(FIG_DIR)/%.tex
	cd $(FIG_DIR) && $(PDFLATEX) $(<F)

clean:
	rm -f $(PAPER).{aux,bbl,blg,log,out,toc,lof,lot,synctex.gz,fls,fdb_latexmk}
	rm -f $(FIG_DIR)/*.{aux,log,fls}
