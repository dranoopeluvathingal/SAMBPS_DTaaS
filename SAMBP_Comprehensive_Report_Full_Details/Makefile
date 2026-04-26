# ============================================================
#  SAMBP Comprehensive Report — Makefile
#  Auto-rebuilds main_report_full.pdf whenever any TR .tex
#  file or build_report.py changes.
#
#  Usage:
#    make          — build PDF if sources changed
#    make force    — always rebuild from scratch
#    make clean    — remove LaTeX auxiliary files
#    make cleanall — remove aux files + generated tex + PDF
# ============================================================

REPORT_DIR   := /root/phd_thesis/SAMBP_Comprehensive_Report_Full_Details
TR_BASE      := /root/phd_thesis/03_technical_reports
BUILDER      := $(REPORT_DIR)/build_report.py
OUT_TEX      := $(REPORT_DIR)/main_report_full.tex
OUT_PDF      := $(REPORT_DIR)/main_report_full.pdf
LOG          := $(REPORT_DIR)/build.log

# Find all TR source files (sorted for reproducibility)
TR_FILES := $(shell find $(TR_BASE) -name "main_report*.tex" | sort)

# ── Default target ────────────────────────────────────────────
.PHONY: all force clean cleanall

all: $(OUT_PDF)

# ── PDF depends on the .tex, which depends on TR sources ─────
$(OUT_PDF): $(OUT_TEX)
	@echo "[SAMBP] Compiling PDF (pass 1)..."
	@cd $(REPORT_DIR) && pdflatex -interaction=nonstopmode main_report_full.tex \
	    >> $(LOG) 2>&1 || true
	@echo "[SAMBP] Compiling PDF (pass 2 — cross-refs)..."
	@cd $(REPORT_DIR) && pdflatex -interaction=nonstopmode main_report_full.tex \
	    >> $(LOG) 2>&1 || true
	@echo "[SAMBP] Done: $$(pdfinfo $(OUT_PDF) | grep Pages) pages"
	@ls -lh $(OUT_PDF)

$(OUT_TEX): $(TR_FILES) $(BUILDER)
	@echo "[SAMBP] TR sources changed — regenerating $(OUT_TEX)..."
	@cd $(REPORT_DIR) && python3 $(BUILDER) 2>&1 | tee -a $(LOG)

# ── Force full rebuild regardless of timestamps ───────────────
force:
	@touch $(BUILDER)
	@$(MAKE) all

# ── Clean auxiliary files (keep PDF and tex) ──────────────────
clean:
	@cd $(REPORT_DIR) && rm -f \
	    main_report_full.aux main_report_full.log \
	    main_report_full.toc main_report_full.lof \
	    main_report_full.lot main_report_full.out \
	    main_report_full.bbl main_report_full.blg \
	    compile*.log build.log
	@echo "[SAMBP] Auxiliary files removed."

# ── Clean everything including generated tex and PDF ─────────
cleanall: clean
	@cd $(REPORT_DIR) && rm -f main_report_full.tex main_report_full.pdf
	@echo "[SAMBP] Generated files removed."
