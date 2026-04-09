# ============================================================
#  Makefile — ieee_6th_order
#  Validation Boundaries of Reduced-Order Inverse Protection
#  Models Under Sixth-Order Synchronous Machine Dynamics
# ============================================================

MAIN   = main
LATEX  = pdflatex
BIBTEX = bibtex
FLAGS  = -interaction=nonstopmode -halt-on-error

DIAGRAMS = \
  diagrams/fig1_concept.tex \
  diagrams/fig2_estimator_recap.tex \
  diagrams/fig3_sixthorder_model.tex \
  diagrams/fig4_dq_to_abc.tex \
  diagrams/fig5_validation_workflow.tex \
  diagrams/fig6_window_hierarchy.tex \
  diagrams/fig7_waveform_compare.tex \
  diagrams/fig8_dq_states.tex \
  diagrams/fig9_short_window_fit.tex \
  diagrams/fig10_long_window_fit.tex \
  diagrams/fig11_rms_residual.tex \
  diagrams/fig12_param_bias.tex \
  diagrams/fig13_condition_number.tex \
  diagrams/fig14_confidence_score.tex \
  diagrams/fig15_controller_contribution.tex \
  diagrams/fig16_relay_deviation.tex \
  diagrams/fig17_triptime_consequence.tex \
  diagrams/fig18_validity_map.tex

.PHONY: all clean distclean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex references.bib $(DIAGRAMS)
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
