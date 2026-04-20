# SUBREPORT_TR58 — Generalised EAC and Conservative CUEP Bound for Relay 78

**TR ID:** TR-58  
**Full title:** Generalised Equal Area Criterion for IBR-Augmented Grids with a Conservative Analytical CUEP Bound for Relay 78 Out-of-Step Protection  
**Folder:** `03_technical_reports/phase_7_IBR_extension/TR58_EAC_CUEP_relay78/`  
**Report file:** `main_report58.tex`  
**Generated:** 2026-04-20  
**Target journal:** IEEE Transactions on Power Systems  
**Thesis allocation:** Chapter 6, §6.3 — Generator Suite (40/64G/78/81/87G)  
**Cross-linked TRs:** TR-56 (DFIG model), TR-65 (generator suite), TR-67 (HIL validation of blinder in hardware)

---

## §1 Scope

**What TR-58 IS:**
- A **generalised energy function** `V_g(δ, ω)` for the hybrid SG + GFM + GFL system, extending the classical EAC Lyapunov function to account for GFM virtual synchronising power and GFL current-limited power deficit
- **Proposition 1 (Conservative CUEP Lower Bound):** a closed-form lower bound `δ_LB ≤ δ_u` requiring only offline commissioning-time data — specifically `P_max^eff = P_max^SG − ΔP_max^GFL`
- A **Relay 78 blinder setting procedure** (Algorithm 1) converting `δ_LB` to an impedance-plane blinder with a 5° security margin
- A **conservative stability index** `η = 1 − A_acc/A_dec^min` computable in real time from synchrophasor measurements
- Validated: 10-scenario deterministic sweep (10/10 PASS) + 2000-trial Monte Carlo (all 6 targets met, 0 conservatism violations)

**What TR-58 IS NOT:**
- Not an online CUEP algorithm — the bound is computed entirely offline at commissioning from static IBR connection data; no real-time PEBS/BCU computation required
- Not applicable to multi-machine EEAC without extension — Proposition 1 is for a single SG on a Thévenin equivalent (SMIB model); multi-machine extension via EEAC deferred
- Not a relay hardware implementation — HIL validation of the blinder coordinates against SEL-300G/GE D60 deferred to TR-67

**Unifying problem (Ch. 6, §6.3):** The standard blinder at `π − δ₀` is non-conservative in IBR-augmented grids. GFL current-limitation during LVRT reduces post-fault synchronising power, shifting `δ_u` inward. The relay may fire *after* the machine has already crossed the point of no return. Standard setting error: +6.7° (non-conservative) vs. −8.5° (proposed, conservative) in the worked numerical example.

---

## §2 State of the Art

Key references in `references58.bib`:

| Ref | Contribution | Limitation vs. TR-58 |
|---|---|---|
| Standard EAC / Kundur 1994 | Classical `δ_u = π − δ₀` for pure-SG SMIB | No IBR; energy function not valid with GFL non-conservative term |
| Wu2020GFM | Power synchronisation control (PSC) for GFM | Control design; no protection implication |
| Chiang1987 (EEAC) | Extended EAC for multi-machine | Online BCU computation — not feasible on relay hardware |
| IEEE C37.92 | Out-of-step relaying guide | Does not address IBR grids; no GFL deficit term |
| NERC TPL-001-4 | N-1 stability requirement | Requires compliance certificate — Prop. 1 provides one |

**Novelty:** First closed-form, offline-computable, provably conservative CUEP lower bound for hybrid SG+GFM+GFL systems, suitable for direct use as a Relay 78 blinder setting.

---

## §3 Method

### 3.1 Augmented power–angle equation

Post-fault total electrical power seen by the SG:
```
P_e(δ) = P_max^SG·sin(δ)          [SG network]
         + K_v·(δ − δ₀)            [GFM, linearised; K_v [pu/rad]]
         − ΔP_GFL(δ)               [GFL deficit; ΔP_GFL ≥ 0]
```
where `K_v = Σ_k (E_v,k·E_g,k/X_v,k)·cos(δ_v,k* − δ_g*)` is the effective virtual synchronising coefficient (commissioning data).

### 3.2 Generalised energy function

```
V_g(δ, ω) = (H_SG/ω₀)·ω²
            − P_m·(δ − δ₀)
            + P_max^SG·(cos δ₀ − cos δ)
            − (K_v/2)·(δ − δ₀)²
            + ∫_{δ₀}^{δ} ΔP_GFL(ξ) dξ
```
**Lemma 1:** On any post-fault trajectory with `ΔP_GFL` non-decreasing in `δ` (satisfied under constant current injection), `V̇_g ≤ 0` along equilibrium trajectories → valid Lyapunov function.

### 3.3 Proposition 1 — Conservative CUEP Lower Bound

**Assumptions:**
- A1 (Worst-case GFL deficit): `ΔP_GFL(δ) ≤ ΔP_max^GFL := max(0, P_GFL^pre − V_min·I_max·cos φ_LVRT)` where `V_min = 0.85 pu` (LVRT floor), `I_max` = GFL rated current
- A2 (GFM tracking): GFM benefit is ignored entirely for conservative direction

```
P_max^eff = P_max^SG − ΔP_max^GFL

δ_LB := π − arcsin(P_m / P_max^eff)   [Eq. 14]

⟹  δ_u ≥ δ_LB    (proven by bounding argument in §4)
```

**Blinder setting:** `δ_blinder = δ_LB − δ_sec`, `δ_sec ≥ 5°`

**Direction of conservatism (Remark 1):** `δ_LB ≤ δ_u` means the blinder is *inside* the true stability region — relay fires before, not after, the point of no return. Standard setting `π − δ₀` is outside whenever `ΔP_max^GFL > 0`.

**Corollary 1 (Pure-SG recovery):** When `ΔP_max^GFL = 0`, the bound recovers the classical result `δ_LB = π − δ₀` exactly.

### 3.4 Conservative stability index

```
η = 1 − A_acc / A_dec^min,   where A_dec^min = P_max^eff·(cos δ_cl − cos δ_LB) − P_m·(δ_LB − δ_cl)
```
`η > 0` is a sufficient condition for stability; `η ≤ 0` is an alarm for possible OOS. Computable in real time from synchrophasor measurements of `δ` and `ω`.

### 3.5 Worked numerical example

| Parameter | Value |
|---|---|
| `H_SG` | 6.5 s |
| `P_m` | 0.80 pu |
| `P_max^SG` | 1.80 pu |
| `δ₀` | 26.4° |
| GFL penetration | 30% |
| `V_min` (deep fault) | 0.20 pu |
| `ΔP_max^GFL` | 0.107 pu |
| `P_max^eff` | 1.693 pu |
| `δ_LB` | **151.8°** (standard: 153.6°, error +1.8°) |
| `δ_blinder` | **146.8°** |
| True `δ_u` (simulation) | ≈155.3° |
| Total conservatism margin | 8.5° inside true CUEP |

---

## §4 Implementation

### File map

| File | Description |
|---|---|
| `main_report58.tex` | This document (full derivation + tables + TikZ figures) |
| `04_code/sambp/relay78/run_tr58_eac_relay78.py` | Swing ODE (RK4) + 10-scenario deterministic + 2000-trial MC validation |

### Algorithm 1 — IBR-Corrected Relay 78 Blinder Setting

```
Input: pre-fault load flow, IBR data, network Thévenin equivalent
1. δ₀ = arcsin(P_m / P_max^SG)
2. ΔP_max^GFL = max(0, P_GFL^pre − V_min·I_max·cos φ_LVRT)
3. Feasibility check: P_m ≤ P_max^SG − ΔP_max^GFL
4. P_max^eff = P_max^SG − ΔP_max^GFL
5. δ_LB = π − arcsin(P_m / P_max^eff)
6. δ_blinder = δ_LB − 5°
7. Convert to R–X impedance blinder via Z_meas(δ_blinder)
```

All steps use static commissioning data — zero online computation required.

---

## §5 Validation

### 5.1 Conservatism gap table (5 representative cases)

| IBR mix | `k_ibr` | `ΔP_max^GFL` (pu) | `δ_LB` (°) | `δ_u` (°) | `ε = δ_u − δ_LB` (°) |
|---|---|---|---|---|---|
| All SG | 0% | 0.00 | 153.6 | 153.6 | 0.0 |
| 30% GFM | 30% | 0.00 | 153.6 | 157.1 | 3.5 |
| 30% GFL (LVRT) | 30% | 0.15 | 146.3 | 149.8 | 3.5 |
| 50% GFL (LVRT) | 50% | 0.25 | 140.7 | 145.2 | 4.5 |
| 30% GFM + 20% GFL | 50% | 0.10 | 148.1 | 155.3 | 7.2 |

Gap `ε ≤ 7.2°` in all deterministic cases. Combined with `δ_sec = 5°`: total blinder margin 10–12° inside true CUEP in the worst case (acceptable for protection grading).

### 5.2 Deterministic 10-scenario sweep (from `run_tr58_eac_relay78.py`)

All 10/10 PASS. Key result for S05–S06 (30% GFL, deep fault, `V_min = 0.10 pu`):
- True CUEP has shifted to `δ_u = 151.1°`
- Standard blinder `π − δ₀ = 153.6°`: fires **after** the CUEP (+2.5° non-conservative)
- Proposed blinder `δ_LB − 5° = 146.1°`: fires **5° inside** the CUEP (conservative ✓)

GFM scenarios (S03, S04, S08): GFM virtual torque prevents finite instability angle; `ε = 26–27°` due to GFM benefit being ignored by Assumption A2 (conservative by design).

### 5.3 Monte Carlo (2000 trials, RK4 Δt = 2 ms)

`k_gfl ∈ [0.10, 0.50]`, `k_gfm ∈ [0.00, 0.30]`, `V_min ∈ [0.15, 0.40] pu`. Stable/unstable trials at `t_cl ∈ [0.40–0.70]×CCT` and `[1.30–1.70]×CCT`.

| Metric | Value | Target |
|---|---|---|
| `P(δ_LB ≤ δ_u)` — Proposition 1 | **1.0000** | = 1.000 |
| Conservatism violations | **0** | = 0 |
| `ε_max = max(δ_u − δ_LB)` | 30.25° | < 35° |
| `P_D` (proposed, unstable trials) | **1.0000** | ≥ 0.980 |
| `P_FA` (proposed, stable trials) | **0.0000** | ≤ 0.010 |
| Median trip time `t₅₀` (proposed) | 470 ms | < 500 ms |

All 6 targets met. Proposition 1 verified with zero violations across all 2000 trials. `ε_max = 30.25°` in GFM-heavy cases (`k_gfm ≈ 0.30`) where true CUEP → 180° but `δ_LB` conservatively ignores GFM benefit.

---

## §6 Results

**Key quantitative claims verified by TR-58:**

| Metric | Value | Source |
|---|---|---|
| Conservatism violations | 0/2000 | MC results |
| `P_D` (proposed relay) | 1.0000 | MC results |
| `P_FA` (proposed relay) | 0.0000 | MC results |
| Deterministic sweep | 10/10 PASS | `run_tr58_eac_relay78.py` |
| S05–S06: standard blinder error | +2.5° non-conservative | Table: compare |
| S05–S06: proposed blinder margin | −5° (inside CUEP) | Proposition 1 |
| `ε_max` (MC) | 30.25° | MC results |
| `ε` standard cases | ≤ 7.2° | Table: gap |
| Blinder crossover (non-conservative) | `ΔP_max^GFL ≈ 0.05 pu` (~5% synchronising power reduction) | Fig: sensitivity |

---

## §7 Limitations

**L-1 — SMIB model only:** Proposition 1 is derived for a single SG on a Thévenin equivalent (SMIB). Extension to multi-machine systems via EEAC (Chiang 1987) requires using `δ_LB` as the CUEP surrogate in the coherent machine decomposition. Deferred.

**L-2 — GFM benefit fully ignored:** Assumption A2 discards the GFM virtual synchronising term entirely, producing `ε_max = 30.25°` in GFM-heavy cases. A tighter bound retaining the GFM lower bound `0.866·K_v·(δ − δ₀)` would reduce `ε_max` significantly but requires commissioning knowledge of `K_v`. Conservative choice is appropriate for protection.

**L-3 — Static commissioning data assumed:** `ΔP_max^GFL` uses the GFL pre-fault injection `P_GFL^pre` and the LVRT data `{I_max, φ_LVRT, V_min}` from the IBR connection agreement. If the GFL operating point changes significantly (e.g., partial output at night), the bound may be overly conservative or require recalculation. Recommends annual setting review.

**L-4 — Impedance-plane blinder not hardware-validated in this TR:** The R–X blinder coordinates (§4.2 of TR-58) are derived analytically. Hardware validation against SEL-300G/GE D60 relay test sets is deferred to TR-67. The RTDS HIL campaign (TR-67) confirms the blinder coordinates in hardware for 5/6 Relay 78 scenarios.

**L-5 — Non-conservative `V_t` assumption:** `V_min = 0.85 pu` (LVRT floor) is used as the worst-case terminal voltage. If the fault clears with `V_t > V_min`, the actual `ΔP_GFL` is smaller than `ΔP_max^GFL`, making the bound more conservative. For close-in 3PH faults (`V_min → 0`), the bound approaches the feasibility limit `P_m = P_max^eff`.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy, scipy.

```bash
# Run 10-scenario deterministic sweep + 2000-trial Monte Carlo
cd /root/phd_thesis/04_code/sambp/relay78
python run_tr58_eac_relay78.py \
    --scenarios all \
    --mc_trials 2000 \
    --rk4_dt 0.002 \
    --output_dir outputs/tr58/

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_7_IBR_extension/TR58_EAC_CUEP_relay78
make
# or: pdflatex main_report58 && bibtex main_report58 && pdflatex main_report58 && pdflatex main_report58
```

**Key figures in the compiled PDF (TikZ-generated inline):**
- R–X diagram: standard vs. proposed blinder, swing locus, CUEP impedance point
- Blinder angle vs. GFL power deficit (sensitivity curve): proposed tracks below true CUEP; standard remains flat (non-conservative for `ΔP > 0.05 pu`)

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report58.tex` read (996 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report58.tex` is authoritative — this file is a read-only analytical summary.*
