"""
run_thesis_synthesis.py
SAMBP TR-55/2026: Thesis Synthesis and Contribution Map

Maps every SAMBP technical report to a thesis chapter, enumerates the
original contributions, identifies the minimal citation set, and
produces a publication roadmap.

Studies:
  A — Report inventory: all 42+ reports by phase and chapter mapping
  B — Original contributions matrix: novelty × significance
  C — Cross-report dependency graph: what each report depends on
  D — Publication roadmap: target venues and paper structures
  E — Gap analysis: what remains for future work
"""

print("=" * 64)
print("SAMBP TR-55: Thesis Synthesis and Contribution Map")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Report inventory and chapter mapping
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Report Inventory and Chapter Mapping ──")

# Chapter structure (IIT Madras PhD thesis)
chapters = {
    1: "Introduction and Motivation",
    2: "Mathematical Foundations (LM, Confidence Gating)",
    3: "Transformer Differential (87T)",
    4: "Line Differential (87L) — Core and IBR Enhancements",
    5: "Distance Protection (21/21G) and Coordination",
    6: "IBR Microgrid Protection",
    7: "Digital Twin and State Estimation",
    8: "Physics-Informed Machine Learning",
    9: "Centralised Protection and Control",
    10: "Conclusion and Future Work",
}

report_chapter_map = [
    # (TR, title_short, chapter, contribution_type)
    ("TR-10", "CT Saturation Immunity",           4, "Component"),
    ("TR-16", "87B/87L Coordination",             4, "System"),
    ("TR-17", "Adaptive 87L Threshold",           4, "Novel"),
    ("TR-18", "Mho Distance Relay (21/21P)",       5, "Component"),
    ("TR-19", "Multi-Feeder Transfer (POTT/PUTT)", 5, "System"),
    ("TR-20", "Frequency-Adaptive 87L",            4, "Novel"),
    ("TR-21", "Harmonic Discrimination 87L",       4, "Novel"),
    ("TR-22", "Negative-Sequence 87LN",            4, "Novel"),
    ("TR-23", "Transient Differential (TDCS-87L)", 4, "Novel"),
    ("TR-30", "Cross-Polarised Mho",               5, "Component"),
    ("TR-31", "Zero-Seq Compensation (21G)",       5, "Component"),
    ("TR-32", "67Q/67N Directional Elements",      5, "Component"),
    ("TR-33", "POTT Scheme",                       5, "System"),
    ("TR-34", "Quadrilateral Distance",            5, "Novel"),
    ("TR-35", "Full IBR Distance Study",           5, "System"),
    ("TR-36", "Auto-Reclosing Strategy",           5, "System"),
    ("TR-37", "Monte Carlo Reliability",           5, "Validation"),
    ("TR-38", "GFL vs GFM Characterisation",       6, "Novel"),
    ("TR-39", "Islanding Detection/Mode Switch",   6, "Novel"),
    ("TR-40", "Adaptive OC Coordination",          6, "Novel"),
    ("TR-41", "87B Bus Differential MG",           6, "Novel"),
    ("TR-42", "Microgrid Integration Study",       6, "System"),
    ("TR-43", "Digital Twin Architecture",         7, "Novel"),
    ("TR-44", "EKF State Estimation",              7, "Novel"),
    ("TR-45", "DT Validation",                     7, "Validation"),
    ("TR-46", "PINN Classifier",                   8, "Novel"),
    ("TR-47", "Feature Engineering",               8, "Novel"),
    ("TR-48", "Online Learning",                   8, "Novel"),
    ("TR-49", "ML Integration",                    8, "System"),
    ("TR-50", "Wide-Area Coordinator (WAPC)",      9, "Novel"),
    ("TR-51", "Settings Optimisation",             9, "Novel"),
    ("TR-52", "Cybersecurity GOOSE",               9, "Novel"),
    ("TR-53", "HIL Validation Protocol",           9, "Validation"),
    ("TR-54", "Field Deployment Guide",            9, "System"),
]

print(f"\n  {'TR':>7s}  {'Ch':>3s}  {'Type':>12s}  Title")
print(f"  {'-'*7}  {'-'*3}  {'-'*12}  {'-'*36}")
for tr, title, ch, ctype in report_chapter_map:
    print(f"  {tr:>7s}  {ch:>3d}  {ctype:>12s}  {title}")

# Summary by chapter
from collections import Counter, defaultdict
ch_count = defaultdict(list)
for tr, title, ch, ctype in report_chapter_map:
    ch_count[ch].append(ctype)

print(f"\n  Chapter report counts:")
for ch in sorted(ch_count):
    types = Counter(ch_count[ch])
    novel = types.get('Novel', 0)
    print(f"    Ch {ch:2d}: {len(ch_count[ch]):2d} reports  "
          f"({novel} novel, {types.get('System',0)} system, "
          f"{types.get('Validation',0)} validation, "
          f"{types.get('Component',0)} component)")

# ════════════════════════════════════════════════════════════════════════
# Study B — Original contributions
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Original Contributions ──")

contributions = [
    # (id, chapter, title, novelty_score, significance_score)
    ("C1",  4, "Physics-constrained adaptive 87L threshold for IBR line differential",   5, 5),
    ("C2",  4, "Harmonic-discrimination filter for IBR multi-inverter differential",      4, 4),
    ("C3",  4, "Negative-sequence 87LN for asymmetric IBR fleet faults",                 4, 4),
    ("C4",  4, "Transient differential TDCS-87L for 3-phase IBR faults",                 4, 5),
    ("C5",  5, "Quadrilateral distance characteristic adapted to IBR current profiles",   4, 4),
    ("C6",  5, "Monte Carlo reliability framework for IBR protection schemes",            3, 5),
    ("C7",  6, "GFL/GFM dual-mode characterisation for protection coordination",         5, 5),
    ("C8",  6, "ROCOF-based islanding with IEC 61850 mode-switch in 120 ms",             4, 4),
    ("C9",  6, "Adaptive OC setting-group switching tied to IBR mode",                   4, 4),
    ("C10", 7, "Non-blocking digital twin architecture for real-time protection audit",   5, 5),
    ("C11", 7, "EKF joint estimation of (k_ibr, Z_line, alpha) from current ratio",      5, 4),
    ("C12", 8, "PINN fault classifier with embedded protection-physics constraints",      5, 5),
    ("C13", 8, "Permutation-importance analysis of physics-derived protection features",  3, 3),
    ("C14", 8, "CUSUM-triggered online learning for fleet composition drift",             4, 4),
    ("C15", 9, "Wide-area PMU fault localisation with N-1 security verification",        5, 5),
    ("C16", 9, "Automatic CTI-graded relay settings engine with fleet-change dispatch",   4, 5),
    ("C17", 9, "HMAC-SHA256 countermeasure for IEC 61850 GOOSE protection channels",     3, 4),
    ("C18", 9, "Closed-loop CUSUM→settings→GOOSE adaptive protection protocol",          5, 5),
]

print(f"\n  {'ID':>4s}  {'Ch':>3s}  {'N':>3s}  {'S':>3s}  Contribution")
print(f"  {'-'*4}  {'-'*3}  {'-'*3}  {'-'*3}  {'-'*52}")
for cid, ch, title, nov, sig in contributions:
    print(f"  {cid:>4s}  {ch:>3d}  {nov:>3d}  {sig:>3d}  {title}")

# High-novelty + high-significance
tier1 = [(c[0], c[2]) for c in contributions if c[3] >= 5 and c[4] >= 5]
print(f"\n  Tier-1 contributions (novelty≥5, significance≥5):")
for cid, title in tier1:
    print(f"    {cid}: {title}")

# ════════════════════════════════════════════════════════════════════════
# Study C — Cross-report dependency
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: Key Cross-Report Dependencies ──")

deps = [
    ("TR-46", ["TR-37", "TR-35"], "PINN trained on MC data from distance protection scheme"),
    ("TR-47", ["TR-46"],          "Feature importance for PINN classifier"),
    ("TR-48", ["TR-47", "TR-46"], "Online update of PINN with fleet drift"),
    ("TR-49", ["TR-46","TR-47","TR-48","TR-43","TR-44"], "Full ML stack integration"),
    ("TR-50", ["TR-43","TR-49"],  "WAPC uses DT + PINN advisory"),
    ("TR-51", ["TR-50","TR-40"],  "Settings engine feeds WAPC"),
    ("TR-52", ["TR-50","TR-51"],  "Secures GOOSE channels carrying trips and settings"),
    ("TR-53", ["TR-46","TR-49","TR-50","TR-51","TR-52"], "Validates all ML+CPC modules"),
    ("TR-54", ["TR-51","TR-52","TR-53","TR-48"], "Field guide uses all prior deliverables"),
]

print(f"\n  {'Report':>7s}  {'Depends on':>36s}  Reason")
print(f"  {'-'*7}  {'-'*36}  {'-'*36}")
for tr, dep, reason in deps:
    print(f"  {tr:>7s}  {', '.join(dep):>36s}  {reason}")

# ════════════════════════════════════════════════════════════════════════
# Study D — Publication roadmap
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: Publication Roadmap ──")

papers = [
    # (paper_id, title, target_journal, TRs, status)
    ("P1", "IBR Line Differential: Adaptive Threshold and Harmonic Discrimination",
     "IEEE Trans. Power Delivery", ["TR-17","TR-20","TR-21","TR-22"], "Draft ready"),
    ("P2", "GFL/GFM Microgrid Protection: Mode-Switch and Adaptive OC Coordination",
     "IEEE Trans. Smart Grid",    ["TR-38","TR-39","TR-40","TR-42"], "Draft ready"),
    ("P3", "Digital Twin for IBR Protection Audit with EKF State Estimation",
     "IEEE Trans. Industrial Informatics", ["TR-43","TR-44","TR-45"], "In preparation"),
    ("P4", "Physics-Informed Neural Network for IBR Fault Classification",
     "IEEE Trans. Power Systems", ["TR-46","TR-47","TR-48","TR-49"], "In preparation"),
    ("P5", "Wide-Area Coordinator with Automatic Settings and GOOSE Security",
     "IEEE Trans. Power Delivery", ["TR-50","TR-51","TR-52","TR-53","TR-54"], "Planned"),
]

print(f"\n  {'ID':>4s}  {'Target journal':>36s}  {'Status':>14s}  TRs")
print(f"  {'-'*4}  {'-'*36}  {'-'*14}  {'-'*30}")
for pid, title, journal, trs, status in papers:
    print(f"  {pid:>4s}  {journal:>36s}  {status:>14s}  {', '.join(trs)}")
    print(f"  {'':>4s}  {title}")

# ════════════════════════════════════════════════════════════════════════
# Study E — Gap analysis
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Gap Analysis and Future Work ──")

gaps = [
    ("G1", "Medium", "Physical HIL validation on real SEL-411L IEDs",
     "TR-53 defines protocol; hardware not yet available"),
    ("G2", "Medium", "Variable-lambda adaptive forgetting (TR-48)",
     "Fixed lambda=0.99 used; adaptive version deferred"),
    ("G3", "Low",    "Z_line observability in EKF (TR-44)",
     "Requires two-ended voltage phasor; identified but unresolved"),
    ("G4", "High",   "Multi-substation WAPC scaling (beyond 10 buses)",
     "TR-50 limited to single substation; wide-area extension needed"),
    ("G5", "Medium", "GOOSE flooding mitigation validation",
     "TR-52 notes switch-level control needed; not tested"),
    ("G6", "Low",    "GFM virtual synchronous machine model",
     "IBR model simplified; full VSM dynamics in future"),
    ("G7", "High",   "Real field fault data for PINN validation",
     "All training data synthetic; field validation required"),
]

print(f"\n  {'ID':>4s}  {'Priority':>8s}  Gap")
print(f"  {'-'*4}  {'-'*8}  {'-'*50}")
for gid, pri, gap, note in gaps:
    print(f"  {gid:>4s}  {pri:>8s}  {gap}")
    print(f"  {'':>4s}  {'':>8s}  → {note}")

high_pri = sum(1 for g in gaps if g[1] == "High")
print(f"\n  High-priority gaps: {high_pri}  (recommended for post-PhD continuation)")

print("\n" + "=" * 64)
print("TR-55 synthesis complete.")
print(f"  Total reports: {len(report_chapter_map)}")
print(f"  Original contributions: {len(contributions)} "
      f"({len(tier1)} Tier-1)")
print(f"  Publications planned: {len(papers)}")
print(f"  Open gaps: {len(gaps)} ({high_pri} high-priority)")
print("=" * 64)
