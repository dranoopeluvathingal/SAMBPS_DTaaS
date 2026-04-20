# SUBREPORT_paper_b — Hilbert–Fortescue Sequence Estimation and Greedy Cascade Coordination

**Paper ID:** paper_b  
**Folder:** `02_papers/paper_b_cascade_oc/`  
**Manuscript:** `main_paper_b.tex` (IEEE journal format, IEEEtran)  
**Target journal:** IEEE Transactions on Industrial Electronics  
**Generated:** 2026-04-20  
**Authors:** Anoop V. Eluvathingal, K. Shanti Swarup (IIT Madras / SGCRL)  
**Extends:** Paper A (M1/M2) with Milestone 3 (M3 — sequence estimator) and Milestone 4 (M4 — cascade coordinator)  
**Cross-linked TRs:** TR-01, TR-02 (sync_oc foundation); companion papers: EluvathingalSeqEstim, EluvathingalCoordGen

---

## §1 Scope

**What paper_b IS:**
- **M3 — Hilbert–Fortescue sequence estimator:** Real-time instantaneous decomposition of three-phase fault currents into positive-, negative-, and zero-sequence signals via analytic signal (Hilbert transform) + Fortescue transformation; independent LM fitting per active sequence
- **M4 — Greedy cascade coordination:** O(N) single-pass algorithm that enforces pickup selectivity (ΔI_m ≥ 0.20 pu) and IEC 60255 time-grading (Δt_grade ≥ 0.15 s) across N parallel generator relays, with a formal inductive convergence proof (Theorem 1)
- **Fault-type routing:** Rules directing 3PH → Paper A (M1) path vs. LL/SLG/LLG → M3 path, with confidence gate extension
- **Graceful degradation:** When estimation confidence is rejected for all generators, the cascade still enforces selectivity from fixed commissioning settings

**What paper_b IS NOT:**
- Not a standalone paper — explicitly builds on Paper A (cites `EluvathingalPaperA`) and shares the 6-parameter physics-constrained model and two-pass LM estimator unchanged
- Not a multi-machine network study — restricted to N generators on a single common busbar (star topology, Eq. 2); ring/mesh topologies deferred
- Not a LL-fault solver — the Hilbert–Fortescue decomposition correctly identifies SLG (γ = 0.914) but fails the confidence gate for LL faults (γ = 0.587) due to shared-frequency residual contamination between I₁ and I₂; fix deferred to companion paper EluvathingalSeqEstim

**Direct extensions from Paper A:**
- Same 6-parameter model `θ = [t₀, I_ss, I_sub, τ_ac, τ_dc, φ_a]` with `I_dc = −I_sub·sin(φ_a)`
- Same two-pass LM estimator applied independently to each active sequence
- Same 4-component confidence gate `γ = w_r·s_r + w_c·s_c + w_b·s_b + w_p·s_p, γ_th = 0.70`

---

## §2 State of the Art

Eight key references in `references_b.bib` bound the novelty:

| Ref | Authors | Approach | Limitation vs. paper_b |
|---|---|---|---|
| Blackburn2006 | Protective Relaying | Fixed OC relay design | No asymmetric fault handling; no multi-relay coordination |
| Anderson1999 | Power system protection | Generator protection standard | Offline only |
| EluvathingalPaperA | Paper A | 3PH LM estimator + confidence gate | No asymmetric fault; no multi-relay coordination |
| Brahma2004 | Topology-adaptive OC | Local measurement-based pickup update | Offline re-optimisation; not real-time |
| Saleh2017 | Microgrid N-1 coordination | Optimisation-based coordination | Solve time in seconds; not sub-cycle |
| Najy2013 | Islanded microgrid OC | Optimal OC for islanded MG | Fixed topology; no estimation in the loop |
| Chen2016 | (implicit, via §Disc) | LP/NLP coordination | O(N²) constraints; not closed-form |
| IEC60255-151 | OC relay standard | Inverse-time characteristic | Standardises constraints enforced by M4 |

**Novelty claims:**
1. First real-time instantaneous Hilbert–Fortescue decomposition for LM parameter estimation under asymmetric faults
2. First O(N) closed-form coordination algorithm with inductive convergence proof for parallel generator busbars
3. First formal demonstration of graceful degradation: coordination guaranteed even when estimation is rejected for all generators

---

## §3 Method

### 3.1 Hilbert–Fortescue sequence estimator (M3)

**Step 1 — Analytic signal:**
```
I̊_a(t) = i_a(t) + j·H{i_a}(t)   (similarly for phases B, C)
```
Computed via FFT over the event window. Hilbert edge effect mitigated by: (i) starting window 2 ms after `t₀`; (ii) Savitzky–Golay pre-smoothing (order 3, window 21 samples); (iii) Pass-2 tail window.

**Step 2 — Fortescue decomposition:**
```
I̊_0(t) = (1/3)[I̊_a + I̊_b + I̊_c]
I̊_1(t) = (1/3)[I̊_a + a·I̊_b + a²·I̊_c],   a = exp(j2π/3)
I̊_2(t) = (1/3)[I̊_a + a²·I̊_b + a·I̊_c]
```

**Step 3 — Fault-type routing and independent LM fitting:**

| Fault | Active sequences | LM fitting |
|---|---|---|
| 3PH | I₁ only | Paper A (M1) unchanged |
| LL | I₁, I₂ | Independent; positive-sequence governs adaptation |
| SLG | I₁ (I₀=I₁=I₂) | I₁ only |
| LLG | I₁, I₂ | Independent |

Positive-sequence `θ̂^(1)` governs relay adaptation. Confidence gate evaluated on positive-sequence Jacobian.

**SLG advantage:** Network identity I₀ = I₁ = I₂ concentrates the full fault current in the positive-sequence signal — clean single-envelope waveform, well-matched to the 6-parameter model → γ = 0.914.

**LL limitation:** I₁ and I₂ share the same carrier frequency ω₀ (series-connected sequence networks). Their real parts are not fully separated by Fortescue acting on real relay measurements → systematic model mismatch, ‖r‖ = 8.12 → γ = 0.587. Fix requires complex-domain measurements (PMU) or independent τ_ac,1/τ_ac,2 estimation.

### 3.2 Greedy cascade coordination (M4)

**Topology:** N generators G₁…G_N on a common busbar, each protected by relay R_k, with downstream bus relay R_B.

**Constraints:**
- Pickup selectivity (IEC 60255-151): `I_p,k ≥ I_p,k+1 + ΔI_m`, `ΔI_m = 0.20 pu`
- Time-grading (IEEE C37.112): `t_op,k(I_f,min) ≥ t_op,k+1(I_f,min) + Δt_g`, `Δt_g = 0.15 s`

**Algorithm (Alg. 1):**
```
Sort generators innermost (k=N) to outermost (k=1)
I_p,N* ← max(I_p,N, I_p,B + ΔI_m)
for k = N-1 downto 1:
    I_p,k* ← max(I_p,k, I_p,k+1* + ΔI_m)
Clip: I_p,k* ← clip(I_p,k*, I_p,min, I_p,max)  for all k
```

**Theorem 1 (One-pass convergence):** Algorithm terminates in exactly N steps and satisfies pickup selectivity for all adjacent pairs (k, k+1). Proved by induction (base case k=N from line 2; inductive step: each update does not modify previously set values).

**O(N) complexity:** Exactly N max-comparisons. Total M3+M4 compute < 20 ms for N=4, W=800 samples.

---

## §4 Implementation

### Module tree

```
04_code/sambp/sync_oc/
├── inverse_estimation/
│   ├── parameter_estimator.py         # Two-pass LM (from Paper A, unchanged)
│   └── sequence_estimator.py          # Hilbert–Fortescue M3 decomposition
├── adaptation/
│   ├── bounded_update.py              # clip_relay_settings(), apply_bounded_update()
│   ├── coordination_logic.py          # Greedy cascade M4; Theorem 1 implementation
│   └── adaptive_mapping.py            # θ̂ → {I_p, TMS} mapping
├── signal_processing/
│   ├── sequence_components.py         # Analytic signal + Fortescue transform
│   └── smoothing.py                   # Savitzky–Golay (Hilbert edge mitigation)
├── run_multi_gen.py                   # Multi-generator busbar runner (N=2,3,4)
└── run_milestone2.py                  # Milestone-2 (M3+M4) entry point

02_papers/paper_b_cascade_oc/figures/
├── fig_pipeline.pdf                   # End-to-end M1→M3→M4 signal flow
├── fig_sequence_networks.pdf          # Sequence network interconnections (LL/SLG/LLG)
├── fig_multi_gen_bus.pdf              # Multi-generator busbar topology
├── fig_coord_N4_3PH.pdf              # N=4 coordination result bar chart
├── fig_pickup_stacking.pdf            # Outermost pickup vs. N (linear growth)
├── fig_coordination_flowchart.pdf     # M4 algorithm flowchart
├── ll_fault_mid_R_waveform.png        # LL fault phase currents (γ=0.587, no adapt)
├── slg_fault_high_R_waveform.png      # SLG fault phase currents (γ=0.914, adapt)
└── fig_pipeline.tex                   # TikZ source for pipeline figure
```

---

## §5 Validation

### 5.1 Sequence estimator — asymmetric faults (M3)

| Case | Fault | `γ` | `κ_n` | `‖r‖` | Adapted | `I_p*` (pu) | Change |
|---|---|---|---|---|---|---|---|
| ll_mid_R | LL | 0.587 | 17.2 | 8.12 | No | 1.200 | 0% |
| slg_high_R | SLG | 0.914 | 17.2 | 0.76 | Yes | 1.100 | −8.3% |

Equal `κ_n = 17.2` for both cases confirms Fortescue decomposition itself is well-conditioned. Γ difference (0.914 vs. 0.587) arises entirely from residual score `s_r`.

### 5.2 Multi-generator coordination — 3PH faults (M4, N=2,3,4)

All generators γ ≥ 0.891; M3 adaptation accepted; cascade enforces selectivity in single pass.

| N | G_1 `I_p*` | G_2 `I_p*` | G_3 `I_p*` | G_4 `I_p*` | Bus | Min margin |
|---|---|---|---|---|---|---|
| 2 | 1.550 | 1.350 | — | — | 1.000 | 0.200 pu ✓ |
| 3 | 1.635 | 1.435 | 1.235 | — | 1.000 | 0.200 pu ✓ |
| 4 | **2.038** | 1.838 | 1.638 | 1.438 | 1.000 | 0.200 pu ✓ |

At N=4: outermost relay G₁ raised from 1.300 pu (fixed) → 2.038 pu (coordinated).

### 5.3 Graceful degradation — N=3, LL fault

All γ ∈ [0.558, 0.696] < 0.70. M3 rejected. Cascade operates on fixed settings:
```
I_p,B = 1.000 → I_p,3 = 1.200 → I_p,2 = 1.400 → I_p,1 = 1.600 pu
```
All 0.200 pu margins satisfied. Coordination delivered without adaptation.

### 5.4 Computational cost

| Component | Operations | Wall time |
|---|---|---|
| Hilbert–FFT (M3) | 1 FFT per sequence | < 1 ms |
| LM per sequence (M1) | ≤ 200 NFev | ≤ 15 ms |
| Greedy cascade N=4 (M4) | 4 comparisons | < 1 ms |
| **Total (SLG case)** | | **< 18 ms** |

---

## §6 Results

**Key quantitative claims:**

| Metric | Value |
|---|---|
| SLG confidence | γ = 0.914 (accepted, `γ_th = 0.70`) |
| SLG pickup reduction | 1.20 → 1.10 pu (−8.3%) |
| LL confidence | γ = 0.587 (rejected, fixed settings retained) |
| N=4 coordination steps | 4 (exactly N — O(N) proof verified) |
| N=4 outermost pickup | 2.038 pu (within standard relay range) |
| All N∈{2,3,4} selectivity margins | ≥ 0.200 pu ✓ |
| Graceful degradation (N=3 LL) | Coordination satisfied from fixed settings ✓ |
| Total compute | < 18 ms (N=4, SLG) |

---

## §7 Limitations

**L-1 — LL fault estimation failure:** The Hilbert–Fortescue decomposition produces γ = 0.587 < 0.70 for LL faults because I₁ and I₂ share the same carrier frequency ω₀ (series sequence networks). The real-part separation is incomplete; ‖r‖ = 8.12 vs. 0.76 for SLG. Fix requires either: (a) complex-domain measurements (PMU phasors), or (b) independent decay-constant estimation for τ_ac,1 and τ_ac,2. Deferred to companion paper `EluvathingalSeqEstim`.

**L-2 — Single-busbar star topology only:** Theorem 1 proves convergence for the star chain G₁→…→G_N→Bus. Multi-bus ring topologies require a more general coordination formulation with O(N²) constraint checks.

**L-3 — Pickup stacking at large N:** Linear growth ΔI_m = 0.20 pu/generator. At N=4, G₁ reaches 2.038 pu. For N ≥ 5, outermost pickup approaches practical relay ceilings. Non-uniform grading margins are needed. Deferred to companion paper `EluvathingalCoordGen`.

**L-4 — TMS grading not explicitly solved in M4:** Theorem 1 covers pickup selectivity (Eq. 3). Time-grading (Eq. 4) is verified post-hoc but M4 does not include a TMS update step. The companion paper `EluvathingalCoordGen` provides the closed-form TMS grading correction.

**L-5 — Hilbert edge effects:** 5–10 ms of Gibbs ringing at window boundaries is mitigated by a 2 ms lead offset + Savitzky–Golay + Pass-2 tail window, bounding Hilbert amplitude error < 0.5% for windows ≥ 100 ms. For shorter fault durations (< 100 ms), edge effects may increase the error.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy.

```bash
# Run M3+M4 multi-generator study (N=2,3,4; 3PH + SLG + LL)
cd /root/phd_thesis/04_code/sambp/sync_oc
python run_milestone2.py \
    --n_generators 2 3 4 \
    --fault_types 3PH SLG LL \
    --output_dir outputs/milestone2/

# Or single-case runner
python run_multi_gen.py --N 4 --fault_type 3PH --verbose

# Compile paper
cd /root/phd_thesis/02_papers/paper_b_cascade_oc
pdflatex main_paper_b && bibtex main_paper_b && \
    pdflatex main_paper_b && pdflatex main_paper_b
```

**Key output figures shipped with manuscript:**

| File | Description |
|---|---|
| `fig_pipeline.pdf` | M1→M3→M4 signal flow (fault routing + confidence gate) |
| `fig_sequence_networks.pdf` | Sequence network interconnections for LL/SLG/LLG |
| `fig_multi_gen_bus.pdf` | Multi-generator busbar topology |
| `fig_coord_N4_3PH.pdf` | N=4 coordination bar chart (fixed → adaptive → coordinated) |
| `fig_pickup_stacking.pdf` | Outermost pickup vs. N (linear growth, practical ceiling) |
| `ll_fault_mid_R_waveform.png` | LL fault waveforms (γ=0.587, gate rejects) |
| `slg_fault_high_R_waveform.png` | SLG fault waveforms (γ=0.914, gate accepts) |

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_paper_b.tex` read (700+ lines) + `references_b.bib` + figures inventory. Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_paper_b.tex` is authoritative — this file is a read-only analytical summary. Do not edit `main_paper_b.tex` via this file.*
