"""
Benchmark runner for generator_aware_inverse_model_selector_v4
on the full Z_Synthetic_Family_Library_v2 dataset.

Expected:
    - generator_aware_inverse_model_selector_v4.py exists in the same folder
    - it exposes:
          generator_aware_inverse_model_selector_v4(input_csv, output_json=None, f0=50.0)

Outputs:
    Z_Synthetic_Family_Library_v2/benchmark_results_v4/
        benchmark_case_results.csv
        benchmark_summary.csv
        confusion_matrix_heuristic.csv
        confusion_matrix_combined.csv
        confusion_matrix_final.csv
        benchmark_by_family.csv
        benchmark_by_fault_type.csv
        benchmark_by_scr.csv
        benchmark_by_noise.csv
        benchmark_by_family_scr.csv
        benchmark_by_family_noise.csv
        benchmark_by_family_fault.csv
        benchmark_summary.json
"""

import os
import json
import time
import pandas as pd
import numpy as np

from generator_aware_inverse_model_selector_v4 import generator_aware_inverse_model_selector_v4


# ============================================================
# Helpers
# ============================================================

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def compute_confusion_matrix(df, true_col, pred_col, labels):
    cm = pd.crosstab(
        pd.Categorical(df[true_col], categories=labels),
        pd.Categorical(df[pred_col], categories=labels),
        dropna=False
    )
    cm.index.name = 'true'
    cm.columns.name = 'pred'
    return cm


def summarize_by_group(df, group_cols):
    agg = df.groupby(group_cols).agg(
        n_cases=('case_id', 'count'),
        final_accuracy=('final_correct', 'mean'),
        combined_accuracy=('combined_correct', 'mean'),
        heuristic_accuracy=('heuristic_correct', 'mean'),
        unknown_rate=('is_unknown', 'mean'),
        mean_final_confidence=('final_confidence', 'mean'),
        mean_combined_margin=('combined_margin', 'mean'),
    ).reset_index()
    return agg


# ============================================================
# Main benchmark runner
# ============================================================

def run_benchmark_v4(
    metadata_csv='Z_Synthetic_Family_Library_v2/metadata/library_metadata.csv',
    output_dir='Z_Synthetic_Family_Library_v2/benchmark_results_v4',
    limit_cases=None,
    save_every=100
):
    ensure_dir(output_dir)

    meta = pd.read_csv(metadata_csv)

    if limit_cases is not None:
        meta = meta.head(limit_cases).copy()

    results = []
    t0 = time.time()

    total_cases = len(meta)
    print(f"Starting benchmark v4 on {total_cases} cases...")

    for idx, row in meta.iterrows():
        try:
            pred = generator_aware_inverse_model_selector_v4(
                input_csv=row['filepath'],
                output_json=None,
                f0=50.0
            )

            out_row = {**row.to_dict(), **pred}
            out_row['run_error'] = ''
            results.append(out_row)

        except Exception as e:
            out_row = row.to_dict()
            out_row.update({
                'run_error': str(e),
                'heuristic_winner': 'run_error',
                'combined_winner': 'run_error',
                'final_family': 'run_error',
                'heuristic_winner_prob': np.nan,
                'combined_winner_prob': np.nan,
                'combined_margin': np.nan,
                'final_confidence': np.nan,
            })
            results.append(out_row)

        if (idx + 1) % save_every == 0 or (idx + 1) == total_cases:
            elapsed = time.time() - t0
            print(f"Processed {idx + 1}/{total_cases} cases | elapsed = {elapsed:.2f} s")

            # checkpoint save
            checkpoint_df = pd.DataFrame(results)
            checkpoint_path = os.path.join(output_dir, 'benchmark_case_results_checkpoint.csv')
            checkpoint_df.to_csv(checkpoint_path, index=False)

    elapsed = time.time() - t0
    results_df = pd.DataFrame(results)

    # --------------------------------------------------------
    # Accuracy columns
    # --------------------------------------------------------
    results_df['is_unknown'] = results_df['final_family'].eq('unknown_or_mixed')
    results_df['heuristic_correct'] = results_df['heuristic_winner'].eq(results_df['family'])
    results_df['combined_correct'] = results_df['combined_winner'].eq(results_df['family'])
    results_df['final_correct'] = results_df['final_family'].eq(results_df['family'])

    known_mask = (
        ~results_df['is_unknown']
        & results_df['final_family'].ne('run_error')
    )

    overall_heuristic_acc = results_df['heuristic_correct'].mean()
    overall_combined_acc = results_df['combined_correct'].mean()
    overall_final_acc = results_df['final_correct'].mean()
    known_only_final_acc = results_df.loc[known_mask, 'final_correct'].mean() if known_mask.any() else np.nan
    unknown_rate = results_df['is_unknown'].mean()

    # --------------------------------------------------------
    # Confusion matrices
    # --------------------------------------------------------
    family_labels = [
        'induction_machine_like',
        'dfig_like',
        'full_converter_pmsg_like',
        'grid_following_inverter_like'
    ]
    final_labels = family_labels + ['unknown_or_mixed', 'run_error']

    cm_heuristic = compute_confusion_matrix(results_df, 'family', 'heuristic_winner', family_labels)
    cm_combined = compute_confusion_matrix(results_df, 'family', 'combined_winner', family_labels)
    cm_final = compute_confusion_matrix(results_df, 'family', 'final_family', final_labels)

    # --------------------------------------------------------
    # Group summaries
    # --------------------------------------------------------
    by_family = summarize_by_group(results_df, ['family'])
    by_fault = summarize_by_group(results_df, ['fault_type'])
    by_scr = summarize_by_group(results_df, ['scr'])
    by_noise = summarize_by_group(results_df, ['noise_std'])
    by_family_scr = summarize_by_group(results_df, ['family', 'scr'])
    by_family_noise = summarize_by_group(results_df, ['family', 'noise_std'])
    by_family_fault = summarize_by_group(results_df, ['family', 'fault_type'])

    # --------------------------------------------------------
    # Residual separation summary
    # --------------------------------------------------------
    rmse_cols = [c for c in results_df.columns if c.startswith('family_rmse_')]

    residual_spreads = []
    for _, r in results_df.iterrows():
        vals = [r[c] for c in rmse_cols if pd.notna(r[c])]
        vals = sorted(vals)
        spread = vals[-1] - vals[0] if len(vals) >= 2 else np.nan
        residual_spreads.append(spread)

    results_df['family_residual_spread'] = residual_spreads

    residual_summary = pd.DataFrame([{
        'mean_family_residual_spread': results_df['family_residual_spread'].mean(),
        'median_family_residual_spread': results_df['family_residual_spread'].median(),
        'min_family_residual_spread': results_df['family_residual_spread'].min(),
        'max_family_residual_spread': results_df['family_residual_spread'].max(),
    }])

    # --------------------------------------------------------
    # Benchmark summary
    # --------------------------------------------------------
    benchmark_summary = pd.DataFrame([{
        'n_cases': len(results_df),
        'elapsed_seconds': elapsed,
        'overall_heuristic_accuracy': overall_heuristic_acc,
        'overall_combined_accuracy': overall_combined_acc,
        'overall_final_accuracy': overall_final_acc,
        'known_only_final_accuracy': known_only_final_acc,
        'unknown_rate': unknown_rate,
        'mean_final_confidence': results_df['final_confidence'].mean(),
        'mean_combined_margin': results_df['combined_margin'].mean(),
        'mean_family_residual_spread': results_df['family_residual_spread'].mean(),
    }])

    # --------------------------------------------------------
    # Save outputs
    # --------------------------------------------------------
    results_csv = os.path.join(output_dir, 'benchmark_case_results.csv')
    summary_csv = os.path.join(output_dir, 'benchmark_summary.csv')
    summary_json = os.path.join(output_dir, 'benchmark_summary.json')

    by_family_csv = os.path.join(output_dir, 'benchmark_by_family.csv')
    by_fault_csv = os.path.join(output_dir, 'benchmark_by_fault_type.csv')
    by_scr_csv = os.path.join(output_dir, 'benchmark_by_scr.csv')
    by_noise_csv = os.path.join(output_dir, 'benchmark_by_noise.csv')
    by_family_scr_csv = os.path.join(output_dir, 'benchmark_by_family_scr.csv')
    by_family_noise_csv = os.path.join(output_dir, 'benchmark_by_family_noise.csv')
    by_family_fault_csv = os.path.join(output_dir, 'benchmark_by_family_fault.csv')
    residual_summary_csv = os.path.join(output_dir, 'benchmark_residual_separation_summary.csv')

    cm_heuristic_csv = os.path.join(output_dir, 'confusion_matrix_heuristic.csv')
    cm_combined_csv = os.path.join(output_dir, 'confusion_matrix_combined.csv')
    cm_final_csv = os.path.join(output_dir, 'confusion_matrix_final.csv')

    results_df.to_csv(results_csv, index=False)
    benchmark_summary.to_csv(summary_csv, index=False)
    by_family.to_csv(by_family_csv, index=False)
    by_fault.to_csv(by_fault_csv, index=False)
    by_scr.to_csv(by_scr_csv, index=False)
    by_noise.to_csv(by_noise_csv, index=False)
    by_family_scr.to_csv(by_family_scr_csv, index=False)
    by_family_noise.to_csv(by_family_noise_csv, index=False)
    by_family_fault.to_csv(by_family_fault_csv, index=False)
    residual_summary.to_csv(residual_summary_csv, index=False)

    cm_heuristic.to_csv(cm_heuristic_csv)
    cm_combined.to_csv(cm_combined_csv)
    cm_final.to_csv(cm_final_csv)

    with open(summary_json, 'w', encoding='utf-8') as f:
        json.dump(benchmark_summary.iloc[0].to_dict(), f, indent=2)

    # --------------------------------------------------------
    # Console summary
    # --------------------------------------------------------
    print("\nSUCCESS: Benchmark v4 completed.")
    print(f"Metadata CSV                 : {os.path.abspath(metadata_csv)}")
    print(f"Results CSV                  : {os.path.abspath(results_csv)}")
    print(f"Summary CSV                  : {os.path.abspath(summary_csv)}")
    print(f"Confusion matrix (combined)  : {os.path.abspath(cm_combined_csv)}")
    print(f"Confusion matrix (final)     : {os.path.abspath(cm_final_csv)}")
    print(f"Elapsed time (s)             : {elapsed:.2f}")
    print(f"Total cases                  : {len(results_df)}")
    print(f"Overall heuristic accuracy   : {overall_heuristic_acc:.4f}")
    print(f"Overall combined accuracy    : {overall_combined_acc:.4f}")
    print(f"Overall final accuracy       : {overall_final_acc:.4f}")
    print(
        f"Known-only final accuracy    : {known_only_final_acc:.4f}"
        if pd.notna(known_only_final_acc) else
        "Known-only final accuracy    : NaN"
    )
    print(f"Unknown/mixed rate           : {unknown_rate:.4f}")
    print(f"Mean final confidence        : {results_df['final_confidence'].mean():.4f}")
    print(f"Mean combined margin         : {results_df['combined_margin'].mean():.4f}")
    print(f"Mean family residual spread  : {results_df['family_residual_spread'].mean():.6f}")

    return {
        'results_df': results_df,
        'benchmark_summary': benchmark_summary,
        'cm_heuristic': cm_heuristic,
        'cm_combined': cm_combined,
        'cm_final': cm_final,
        'by_family': by_family,
        'by_fault': by_fault,
        'by_scr': by_scr,
        'by_noise': by_noise,
    }


if __name__ == "__main__":
    run_benchmark_v4(
        metadata_csv='Z_Synthetic_Family_Library_v2/metadata/library_metadata.csv',
        output_dir='Z_Synthetic_Family_Library_v2/benchmark_results_v4',
        limit_cases=None,
        save_every=100
    )