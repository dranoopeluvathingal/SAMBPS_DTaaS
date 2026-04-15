# =============================================================================
#  Makefile — sambp_sync_oc Technical Report
#  Usage:
#    make report      — compile main_report.pdf (full, with bibtex)
#    make figures     — compile all standalone TikZ figures to PDF
#    make clean       — remove auxiliary files
#    make distclean   — remove all generated files (PDFs included)
# =============================================================================

REPORT    = main_report
BIBFILE   = references
FIG_DIR   = figures
FIG_SRCS  = $(wildcard $(FIG_DIR)/*.tex)
FIG_PDFS  = $(FIG_SRCS:.tex=.pdf)

PDFLATEX  = pdflatex -interaction=nontopstop -halt-on-error -shell-escape
BIBTEX    = bibtex

# ---- Default target ---------------------------------------------------------
.PHONY: all
all: report figures

# ---- Main report (3-pass latex + bibtex) ------------------------------------
.PHONY: report
report: $(REPORT).pdf

$(REPORT).pdf: $(REPORT).tex $(BIBFILE).bib $(FIG_SRCS)
	$(PDFLATEX) $(REPORT)
	-$(BIBTEX) $(REPORT)
	$(PDFLATEX) $(REPORT)
	$(PDFLATEX) $(REPORT)
	@echo ""
	@echo ">>> Report compiled: $(REPORT).pdf"

# ---- Standalone TikZ figures ------------------------------------------------
.PHONY: figures
figures: $(FIG_PDFS)

$(FIG_DIR)/%.pdf: $(FIG_DIR)/%.tex
	cd $(FIG_DIR) && $(PDFLATEX) $(<F)
	@echo ">>> Figure compiled: $@"

# ---- Convert figure PDFs to PNG (300 dpi, for paper submission) --------------
.PHONY: fig_png
fig_png: figures
	@for f in $(FIG_DIR)/*.pdf; do \
	  base=$$(basename $$f .pdf); \
	  pdftoppm -r 300 -png -singlefile $$f $(FIG_DIR)/$$base; \
	  echo ">>> PNG: $(FIG_DIR)/$$base.png"; \
	done

# ---- Clean auxiliary files --------------------------------------------------
.PHONY: clean
clean:
	rm -f $(REPORT).aux $(REPORT).bbl $(REPORT).blg \
	      $(REPORT).log $(REPORT).out $(REPORT).toc \
	      $(REPORT).lof $(REPORT).lot $(REPORT).idx \
	      $(REPORT).acn $(REPORT).ist $(REPORT).fls \
	      $(REPORT).fdb_latexmk $(REPORT).synctex.gz
	rm -f $(FIG_DIR)/*.aux $(FIG_DIR)/*.log $(FIG_DIR)/*.fls \
	      $(FIG_DIR)/*.fdb_latexmk

# ---- Full clean (remove PDFs too) -------------------------------------------
.PHONY: distclean
distclean: clean
	rm -f $(REPORT).pdf $(FIG_DIR)/*.pdf $(FIG_DIR)/*.png
