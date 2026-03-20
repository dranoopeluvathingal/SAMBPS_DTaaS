#!/bin/bash

# 1. Create Directories [cite: 2026-03-01]
mkdir -p core_engines data_processing analytics_validation visualization presentation_delivery backups

# Function to move only if file exists [cite: 2026-03-10]
safe_move() {
    if ls $1 >/dev/null 2>&1; then
        mv $1 $2
        echo "Moved: $1 -> $2"
    fi
}

# 2. Move Core Engines (Models and Logic)
mv method_a_magnitude.py model_a_magnitude.pkl core_engines/
mv method_b_entropy.py model_b_entropy.pkl core_engines/
mv hybrid_relay.py core_engines/
mv ansi_21lb_sim.py core_engines/
mv goose_engine.py core_engines/
mv fault_classifier.py core_engines/
mv ibr_fault_classifier.pkl core_engines/
mv feature_scaler.pkl core_engines/
mv adaptive_relay.py core_engines/
mv Fault_classifier.py core_engines/
mv scaler_a.pkl core_engines/
mv scaler_b.pkl core_engines/

# 3. Move Data Generation & Raw Data
mv hif_data_generator.py hif_fault_data.csv data_processing/
mv pscad_data_generator.py pscad_fault_data.csv data_processing/
mv sg_data_generator.py sg_fault_data.csv data_processing/
mv fault_data.csv data_processing/
mv generate_fault_data.py data_processing/
mv master_gen.py data_processing/

# 4. Move Analytics and Batch Audits
mv security_audit.py analytics_validation/
mv latency_audit.py analytics_validation/
mv batch_processor.py analytics_validation/
mv Master_100_Sim_Results.csv analytics_validation/
mv batch_validation_results.csv analytics_validation/
mv Comparative_Summary.csv analytics_validation/
mv Master_Trainer.py analytics_validation/
mv sequence_engine.py analytics_validation/
mv compare_methods_audit.py analytics_validation/
mv compare_results.py analytics_validation/
mv decision_boundaries.py analytics_validation/

# 5. Move Visualization Suite (Scripts and Images)
mv plot_integrated_entropy.py visualization/
mv integrated_entropy_plot.png visualization/
mv plot_operating_curves.py visualization/
mv plot_residual_chaos.py visualization/
mv thd_delay_plot.py visualization/
mv entropy_analysis.png visualization/
mv final_results_summary.png visualization/
mv method_comparison_physics.png visualization/
mv recreated_waveform.png visualization/
mv plot_comparison.py visualization/
mv plot_fault_results.py visualization/
mv plot_fault_waveform.py visualization/
mv plot_sg_analysis.py visualization/
mv batch_plots.py visualization/
mv plot_ripple_comparison.py visualization/
mv plot_sg_vs_ibr.py visualization/
mv comparative_analysis_results.png visualization/
mv thd_delay_scatter.png visualization/

# 6. Move Presentation and Delivery
mv Anoop_Detailed_PhD_Synopsis.pptx presentation_delivery/
mv Anoop_PhD_Synopsis.pptx presentation_delivery/
mv generate_synopsis.py presentation_delivery/
mv generate_detailed_synopsis.py presentation_delivery/
mv comparison_chart.py presentation_delivery/
mv generate_relay_flowchart.py presentation_delivery/

# 7. Move Backups and Miscellaneous
mv thesis_plots_backup.zip backups/
mv Relay_Data_Case_*.xlsx backups/

# 5. Cleanup 
# Keeping README.md and organize_thesis.sh in root for visibility  

echo "SUCCESS: PhD Thesis workspace organized for Dr. Anoop Eluvathingal."