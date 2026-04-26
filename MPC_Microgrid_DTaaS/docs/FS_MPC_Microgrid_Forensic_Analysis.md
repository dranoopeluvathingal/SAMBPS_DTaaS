# Forensic Analysis — FS-Model Predictive Control of Microgrid Interface Converters for Reactive Power and Harmonic Compensation

**Source:** Perez, M. A., & Flores-Bahamonde, F. (2016). *FS-Model Predictive Control of Microgrid Interface Converters for Reactive Power and Harmonic Compensation.* Proc. IEEE PEDG, pp. 1206–1211. Universidad Técnica Federico Santa María, Valparaíso, Chile.

**Analyst:** Anoop Eluvathingal · **Date:** 2026-04-26 · **Purpose:** Reproduce as standalone project for MAS-DT-SH thesis Ch4 / Ch5 baseline + APPEEC paper #2 supporting reference.

---

## 1. Core Idea — Forensic Read

### 1.1 What is being claimed

The Microgrid Interface Converter (MIC) — the bidirectional VSI that already sits between a DC microgrid and the AC grid for *power exchange* — is **simultaneously** used as a power-quality compensator (active filter + STATCOM) for **the main grid** at the PCC. One converter does two jobs: bulk bidirectional power flow **and** ancillary services (reactive support + harmonic cancellation), without disrupting normal microgrid operation.

### 1.2 Why this is non-trivial

| Conventional approach | What this paper changes |
|---|---|
| MIC handles only fundamental real/reactive power; PQ is handled by *separate* STATCOM / APF / DSTATCOM | One converter, two functions — capex saved |
| Internal MG-side compensation (refs [10]–[17]) only cleans the AC bus *inside* the microgrid | This compensates the *main grid* current `i_s` at the PCC |
| Linear small-signal v_dc PI control breaks down for distorted/large transients | Uses **energy-domain** outer loop → linear plant in I_s, no linearisation |
| Linear PI inner-loop current control struggles with high-order harmonics | **Finite-Set MPC** — directly tracks distorted refs at switching-frequency bandwidth |

### 1.3 The hidden insight

When the microgrid sits in **zero-consumption mode** (`i_dc = 0`), the topology *is mathematically identical to* a STATCOM/active filter. The paper observes this and asks: can the same controller seamlessly extend this STATCOM behaviour to loading and regenerating modes? The answer is yes — the inner FS-MPC tracks whatever distorted reference the outer loop hands it, and the outer energy-loop produces the right amplitude regardless of which direction `i_dc` flows.

### 1.4 Novelty contribution (rank-ordered)

1. **Energy-based DC-bus model** that is exactly linear in `I_s` (not just locally linearised around `v_dc*`).
2. **FS-MPC reference shaping** as `i_m_ref = i_s_ref − i_l` so the converter explicitly absorbs the load's harmonics and reactive content.
3. Demonstrates **mode-agnostic** operation — same controller works for loading, regenerating, and zero-consumption.

---

## 2. Control Architecture — Block-by-Block

### 2.1 Plant (what is being controlled)

```
                   ┌──────────┐                   ┌────────────┐
   PV ──┐          │          │      i_m          │            │   i_s
        ├─DC/DC───►│  C, v_dc │◄────VSI ─── L,r ──┤    PCC     ├────►  Grid v_s
   Bat ─┘          │          │   (3-phase 2-lvl) │            │
                   │          │      ▲            └─────┬──────┘
                   └────┬─────┘      │                  │ i_l
                        │ i_dc       s ∈ {0,1}^3        ▼
                                                     Loads
                                            (linear RL + 6-pulse rectifier)
```

### 2.2 Governing equations (continuous-time)

| Variable | Meaning |
|---|---|
| `v_dc` | DC-link voltage |
| `i_dc` | Net DC current from microgrid into the DC link (sign convention: regenerating > 0) |
| `i_m` | 3-phase converter current (AC side of L filter) |
| `v_s` | 3-phase grid voltage at PCC |
| `i_s` | 3-phase grid current (`i_s = i_m + i_l`) |
| `i_l` | 3-phase load current (linear + non-linear) |
| `s = [sa, sb, sc]` | Switching vector, each in {0,1} |

**DC-side (Eq 1):**
```
C · dv_dc/dt + v_dc/R = sᵀ i_m − i_dc        (1)
```

**AC-side (Eq 2):**
```
L · di_m/dt + r · i_m = v_s − M s v_dc        (2)

         ┌  2  -1  -1 ┐
M = 1/3 ·│ -1   2  -1 │   (zero-sequence-removal matrix)
         └ -1  -1   2 ┘
```

**KCL at PCC (Eq 3):** `i_s = i_m + i_l`

### 2.3 Two-loop cascade

```
                                           ┌─────────────────────────────┐
   v_dc ──►  v_dc²  ──► Energy E_c=½Cv_dc² │                             │
                                           │     OUTER PI on E_c         │──► I_s* (amplitude)
   v_dc_ref ►  E_c_ref ───────────────────►│   plant: 1/(s + 2/RC)·(3Vs/2)│
                                           └─────────────────────────────┘
                                                                          │
                                                                          ▼
   v_s ──► PLL (positive-sequence) ──► sin(θ_a), sin(θ_b), sin(θ_c) ──► × ──► i_s_ref(t)
                                                                          │
                                                                          ▼
   i_l (measured) ──► subtract ──► i_m_ref = i_s_ref − i_l
                                                                          │
                                                                          ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  INNER FS-MPC                                                        │
   │   for each s ∈ {000, 100, 110, 010, 011, 001, 101, 111}              │
   │     compute  i_m_pred(k+1) = (1 − rT_s/L)·i_m(k) + (T_s/L)·(v_s − Ms·v_dc) │
   │     compute  g(s) = Σ_phase (i_m_pred − i_m_ref)²                    │
   │   apply argmin_s g(s) at t=k+1                                       │
   └──────────────────────────────────────────────────────────────────────┘
                                                                          │
                                                                          ▼
                                                                    Gate signals
```

---

## 3. Inner Loop — Finite-Set MPC Current Control (Detailed)

### 3.1 Why FS-MPC and not a linear PI/PR?

The reference `i_m_ref = i_s_ref − i_l` contains the **load harmonic spectrum** (5th, 7th, 11th, 13th… for a 6-pulse rectifier). A PI in `dq` only tracks the fundamental; a PR bank requires one resonant per harmonic and stability tuning. **FS-MPC tracks any reference up to ~f_sw/10 bandwidth without redesign**, which is exactly what's needed.

### 3.2 Discretization (Forward Euler, Eq 4)

With `T_s = 20 µs`:
```
i_m_pred(k+1) = (1 − r·T_s/L)·i_m(k) + (T_s/L)·(v_s(k) − M·s·v_dc(k))      (4)
```
For the listed parameters (L=1 mH, r assumed ~50 mΩ): `1 − rT_s/L ≈ 0.999` → effectively the predictor is dominated by the input term `(T_s/L)·(v_s − M s v_dc)` ≈ 20 V/A scaling.

### 3.3 Switching candidates

For a 2-level 3-phase VSI, `s ∈ {0,1}^3` → 8 combinations. Two of them (000, 111) yield identical zero AC voltage. So the cost function effectively evaluates **7 unique voltage vectors**.

### 3.4 Cost function (Eq 5/6)

```
g(s) = Σ_{i ∈ {a,b,c}} ( i_m_pred,i(k+1) − i_m_ref,i(k+1) )²
     = Σ_{i ∈ {a,b,c}} ( i_m_pred,i(k+1) − i_s_ref,i(k+1) + i_l,i(k+1) )²
```

The argmin over the 8 candidates is applied at the next sample.

### 3.5 Delay compensation (mentioned, not derived)

Computational delay (computing g(s) takes ~1 sample) means the *applied* state at t=k+1 is based on stale state at t=k. Standard fix: predict twice — first roll the state to k+1 using the previously-applied switching, then evaluate g(s) for the k+2 prediction. The paper cites Kouro et al. (2015) for the delay compensation methodology but doesn't derive it.

### 3.6 Tuning levers

| Lever | Effect |
|---|---|
| `T_s` | Smaller → better tracking, more compute. 20 µs ↔ 50 kHz evaluation rate |
| Cost weight per phase | Could add a switching-effort penalty `λ·||s(k+1) − s(k)||²` to reduce f_sw — paper does NOT do this |
| Number of horizons | Single-step in the paper. Multi-step would improve performance but cost explodes 8^N |
| Reference filter | Could band-limit `i_l` to control which harmonics are compensated |

---

## 4. Outer Loop — DC-Link Energy Control (Forensic Derivation)

### 4.1 Why the energy formulation matters

A classical approach controls `v_dc` directly with a PI. But the actual relationship between input power and `v_dc` is **nonlinear** because power = energy rate, and energy ∝ `v_dc²`. Linearising around `v_dc*` is fine for small signals but fails during large disturbances (e.g. 100 A `i_dc` step). The energy formulation makes the plant **globally linear in I_s**.

### 4.2 Derivation (paper's path, expanded)

Multiply Eq (2) by `i_mᵀ` and add to (1) × `v_dc`:
```
v_dc · C · dv_dc/dt + v_dc²/R = v_dc · sᵀ i_m − i_dc · v_dc
```
But `v_dc · sᵀ i_m = i_mᵀ · (M s v_dc)` plus AC losses; combining with (2):
```
(C/2) · d(v_dc²)/dt + v_dc²/R = i_mᵀ v_s − i_dc v_dc       (7)
```
Define `E_c = ½ C v_dc²`. Substitute `i_m = i_s − i_l`:
```
dE_c/dt + (2/RC) E_c = v_sᵀ i_s − v_sᵀ i_l − i_dc v_dc      (9)
```

### 4.3 Plant transfer function

Treat `p_dc = i_dc · v_dc` and `p_l = v_sᵀ i_l` as **measurable disturbances** (feedforward candidates). Then:
```
G_E(s) = E_c(s) / P_s(s) = 1 / (s + 2/RC)        (10)
```
For balanced 3-phase with PLL-locked sinusoidal current `i_s = I_s · [sin(θ), sin(θ−2π/3), sin(θ+2π/3)]`:
```
P_s = v_sᵀ i_s = (3/2) V_s I_s
```
So:
```
G(s) = E_c(s) / I_s(s) = (3 V_s / 2) / (s + 2/RC)        (11)
```

### 4.4 Controller — PI on energy error

```
   E_c_ref = ½ C v_dc_ref²
   e_E = E_c_ref − E_c
   I_s* = K_p · e_E + K_i · ∫ e_E dt
```

Tuning by pole placement against `(3V_s/2) / (s + 2/RC)`:
- For settling time of 20 ms (paper's claim) and 2nd-order closed-loop response with damping ζ=0.7 → ω_n ≈ 200 rad/s.
- Standard PI synthesis: `K_p = (2ζω_n − 2/RC) / (3V_s/2)`, `K_i = ω_n² / (3V_s/2)`.

### 4.5 Disturbance feedforward (improvement over paper)

The paper treats `p_dc` and `p_l` as disturbances. **Feeding them forward** as `I_s_ff = (p_dc + p_l) / (3V_s/2)` and adding to the PI output would eliminate the steady-state amplitude swing during mode transitions. This is an obvious enhancement when reproducing.

---

## 5. Operating Modes Covered

| Mode | `i_dc` sign | Power flow | Converter behaviour |
|---|---|---|---|
| **Loading** | `i_dc < 0` | Grid → MG | Converter draws fundamental from grid + injects compensating harmonic+Q |
| **Regenerating** | `i_dc > 0` | MG → Grid | Converter injects fundamental into grid + injects compensating harmonic+Q |
| **Zero-consumption** | `i_dc = 0` | None bulk | Pure STATCOM / active filter |

All three are handled by the **same** controller with no mode switching — the energy loop adjusts `I_s*` automatically.

---

## 6. Simulation Validation — Detailed Analysis

### 6.1 Test bench parameters (Table I in paper)

| Parameter | Value | Comment |
|---|---|---|
| AC grid voltage (RMS, line-line) | 380 V | Standard EU LV |
| DC-link voltage `v_dc*` | 900 V | > √2·380 √3, leaves headroom |
| Microgrid nominal power | 80 kW | At full regeneration |
| Nonlinear load | 25 kW (6-pulse rectifier, inductive DC) | Dominant 5th, 7th |
| Linear load | 10 kW / 10 kVAr | RL combination |
| `C` (DC link) | 1000 µF | Sized for `ΔV_dc` < 5% on transient |
| `L` (AC filter) | 1 mH | First-order filter, no LCL |
| `T_s` | 20 µs | 50 kHz cost-function rate |

### 6.2 Test cases and what they prove

| Fig | Mode | Scenario | What it validates |
|---|---|---|---|
| 4 | Loading | Nonlinear load only | `i_s` sinusoidal + in-phase even with distorted `i_l`; harmonic absorption working |
| 5 | Regenerating | Nonlinear load only | Same harmonic compensation while injecting bulk power; `i_s` 180° from `v_s` |
| 6 | STATCOM (`i_dc=0`) | Nonlinear load | Limit-case proof — converter purely PQ |
| 7 | Loading | + 9 kVAr linear Q | Reactive compensation alongside harmonic — 'i_s' still in-phase |
| 8 | Loading | + 23 kVAr linear Q | Higher Q; lagging `i_l` and leading `i_m` clearly visible; same 'i_s' amplitude as Fig 7 → P unchanged ✓ |
| 9 | Voltage step | 0→100 A regen at t=200ms; switch to 100 A loading at t=400ms | DC-link 2nd-order settling ~20 ms; `I_s_ref` adjusts; closed-loop bandwidth verified |
| 10 | Power waveforms | Load step + Q step | `p_s` tracks `p_l + p_dc`; `q_s` ≈ 0 throughout despite 35 kVAr load Q |

### 6.3 What the paper does **not** show (gaps for you to fill if extending)

- No THD numbers reported for `i_s`. (Reproduce → measure THD → quantify improvement.)
- No grid voltage harmonics or unbalance — assumes ideal `v_s`.
- No grid-fault ride-through (LVRT/HVRT).
- No multi-converter coordination (relevant for MAS-DT-SH).
- No hardware-in-loop or experimental validation.
- Switching frequency not reported (it's variable in FS-MPC).
- No comparison against PI-PR baseline.

---

## 7. Why It Matters For Your Work

### 7.1 Direct relevance map

| Your project | How this paper plugs in |
|---|---|
| **MAS-DT-SH thesis Ch4** (Math + Algorithm) | This is a clean, citeable example of FS-MPC for an Interface Converter Agent. The energy-domain DC-bus trick is worth a paragraph. |
| **MAS-DT-SH thesis Ch5** (Digital Twin) | The plant equations (1)(2) are exactly the DT model you'd embed in the cyber side of an ICA digital twin. |
| **APPEEC paper #2** (GFM/GFL estimator) | Citation for FS-MPC's ability to track distorted refs — supports your estimator's claim of harmonic-aware operation. |
| **APPEEC paper #3** (DT trajectory prediction) | The 1-step predictor here is the simplest case of the trajectory predictor; you can cite as baseline. |
| **MAS taxonomy (Sprint 5)** | Concretises "Interface Converter Agent" — one converter, one outer loop, one inner FS-MPC. Clean role spec. |
| **Algorithm-1 end-to-end (Sprint 6)** | Reuse this code as the bottom-layer device controller while your Zone Agent dispatches `v_dc_ref` and `i_dc` setpoints from above. |

### 7.2 What to extract for citation

```
@inproceedings{perez2016fsmpc,
  author    = {Perez, Marcelo A. and Flores-Bahamonde, Freddy},
  title     = {{FS-Model Predictive Control of Microgrid Interface
               Converters for Reactive Power and Harmonic Compensation}},
  booktitle = {Proc. IEEE PEDG},
  year      = {2016},
  pages     = {1206--1211},
  doi       = {10.1109/PEDG.2016.7527028}
}
```

---

## 8. Reproduction Plan — Build It As A New Project

### 8.1 Stack choice

| Option | Pros | Cons | Recommendation |
|---|---|---|---|
| **Python (numpy/scipy/matplotlib)** | Free, scriptable, integrates with MAS-DT-SH lab repo, easy CI | Slower than compiled; no native solver for stiff power-electronics dynamics | **Pick this** for thesis-grade reproducibility |
| MATLAB/Simulink + Simscape Electrical | Industry-standard, GUI, fast | License cost; harder version control | Use only if you need vendor-validated PE blocks |
| PSCAD/EMTDC | Best EMT fidelity | Closed, expensive | Skip |
| OpenModelica | Free, EMT-capable | Steeper learning curve | Future option |

**Recommendation:** Python first (own the math). Mirror to Simulink later if APPEEC reviewers push back.

### 8.2 Project layout

```
fs_mpc_microgrid/
├── README.md
├── pyproject.toml
├── requirements.txt
├── src/fs_mpc_mg/
│   ├── __init__.py
│   ├── plant.py          # 3φ VSI + L filter + DC-link ODE
│   ├── load_model.py     # 6-pulse rectifier + linear RL
│   ├── pll.py            # SOGI / DDSRF positive-seq PLL
│   ├── inner_fsmpc.py    # FS-MPC current controller (8 candidates)
│   ├── outer_energy_pi.py # Energy-domain DC-link PI
│   ├── simulator.py      # Top-level fixed-step EMT loop
│   └── scenarios.py      # Loading / Regen / Zero / Q-sweep
├── notebooks/
│   ├── 01_reproduce_fig4_loading.ipynb
│   ├── 02_reproduce_fig5_regen.ipynb
│   ├── 03_reproduce_fig6_statcom.ipynb
│   ├── 04_reproduce_fig9_voltage_step.ipynb
│   └── 05_thd_quantification.ipynb
├── tests/
│   ├── test_plant.py
│   ├── test_predictor.py
│   ├── test_pll_lock.py
│   └── test_energy_pi.py
└── figures/        # Auto-generated PNGs matching paper figures
```

### 8.3 Step-by-step build sequence

| Step | Module | What you implement | Test gate before next step |
|---|---|---|---|
| 1 | env | `pyproject.toml`, `requirements.txt` (numpy, scipy, matplotlib, pytest), Python 3.11+ venv | `pytest --version` works |
| 2 | `plant.py` | Continuous-time ODE: `i_m_dot = (v_s − Msv_dc − r·i_m)/L`, `v_dc_dot = (sᵀi_m − i_dc − v_dc/R)/C` | Unit test: open-circuit `s=000` → `i_m → 0` exponentially |
| 3 | `load_model.py` | Six-pulse diode rectifier (use idealised commutation model or full diode network); linear RL | THD of `i_l` ≈ 25–30% with no filter ✓ matches textbook |
| 4 | `pll.py` | Positive-sequence DDSRF or SOGI-PLL on `v_s` | Locks within 30 ms on 50 Hz step from 0 → 380 V |
| 5 | `inner_fsmpc.py` | (a) build 8-vector LUT in αβ; (b) Eq (4) predictor; (c) cost g(s) per Eq (6); (d) argmin | Test: with `i_l = 0` and step `i_m_ref`, current settles within 1–2 sample times |
| 6 | `outer_energy_pi.py` | Eq (8): `E_c = ½ C v_dc²`; PI on `E_c_ref − E_c` → `I_s*` | Test: `v_dc` settles to 900 V from 800 V in ~20 ms with `i_dc=0` |
| 7 | `simulator.py` | Fixed-step EMT loop: ODE integrator (RK4) at sub-T_s step, controller call every `T_s`, ZOH on switching | Test: 1 s simulation in <30 s wall-clock for T_s=20 µs |
| 8 | `scenarios.py` | Mode-switching scripts to drive `i_dc(t)` and load profile | — |
| 9 | Reproduce Fig 4 | Run loading scenario; plot `v_s`, `i_s`, `i_m`, `i_l` | Visual match within 5% amplitude of paper |
| 10 | Reproduce Fig 5/6/7/8/9/10 | One notebook each | All visually match; `i_s` THD < 5% in all modes |
| 11 | THD quantification | FFT of `i_s` and report THD per case | Numbers logged in CSV; gives you content the paper omits |
| 12 | Wrap as ICA agent | Adapter exposing `set_v_dc_ref`, `set_i_dc`, `step(dt)` for MAS integration | Plugs into MAS-DT-SH orchestrator skeleton (Sprint 3 deliverable) |

### 8.4 Key implementation gotchas (forensic warnings)

1. **Forward Euler at 20 µs is borderline stable** for L=1 mH (time constant 20 µs if r≈50 mΩ). Verify stability or use trapezoidal predictor.
2. **Six-pulse rectifier ideally needs an iterative LCP solver** for diode commutation. Two acceptable shortcuts: (a) precomputed waveform from a reference simulation; (b) idealised 120° conduction model (gives 5th, 7th, 11th, 13th cleanly).
3. **`M` matrix sign convention** — confirm by checking that `M·[1,0,0]ᵀ·v_dc` produces `[2v_dc/3, −v_dc/3, −v_dc/3]` for `s=[1,0,0]`. Some textbooks use a different normalisation.
4. **PLL phase-frame** — your `i_s_ref` must be in the same frame as `i_m` measurement (abc, not αβ). Don't mix.
5. **Delay compensation** — without it you'll see ~1.5× the ripple the paper shows. Implement (k+2) predictor from sample 1.
6. **`R` in Eq (1)** — the paper models DC-link losses as a parallel resistor. Set R≈10 kΩ so `2/RC ≈ 0.2 rad/s` (slow); doesn't affect inner loop.
7. **Variable switching frequency** — FS-MPC produces a non-constant f_sw. Log it; useful figure of merit.

### 8.5 Validation checklist (your "definition of done")

| Check | Pass criterion |
|---|---|
| `i_s` THD in loading mode | < 5% (vs ~25% load THD) |
| `i_s` THD in regen mode | < 5% |
| `i_s` THD in STATCOM mode | < 5% |
| `v_dc` settling time on 100 A step | 20 ± 5 ms |
| Reactive power at PCC across all cases | < 1 kVAr |
| Active power balance `p_s ≈ p_l + p_dc` | within 2% steady-state |
| All paper figures (4, 5, 6, 7, 8, 9, 10) reproduced | Visual + quantitative match |

---

## 9. Result — Tabulated Master Summary

### 9.1 Paper-at-a-glance

| Field | Value |
|---|---|
| Title | FS-MPC of Microgrid Interface Converters for Reactive Power and Harmonic Compensation |
| Authors | M. A. Perez, F. Flores-Bahamonde |
| Affiliation | UTFSM, Chile |
| Venue / Year | IEEE PEDG 2016, pp. 1206–1211 |
| Topology | DC microgrid + 2-level VSI interface + L filter + AC grid + linear/nonlinear loads at PCC |
| Inner loop | Finite-Set MPC, 1-step horizon, 8 switching candidates, T_s=20 µs |
| Outer loop | PI on capacitor energy `E_c = ½Cv_dc²` (linear in I_s) |
| Validation | Simulation only (80 kW system), 7 test cases |
| Key result | Sinusoidal in-phase grid current across all 3 microgrid modes, 20 ms DC-link settling |

### 9.2 Reproduction roadmap (1-line summary)

| # | Phase | Deliverable | Time estimate |
|---|---|---|---|
| 1 | Setup | Repo + venv + CI | 0.5 day |
| 2 | Plant model | `plant.py` + tests | 1 day |
| 3 | Load model | `load_model.py` + diode rectifier | 1.5 days |
| 4 | PLL | `pll.py` (SOGI) | 1 day |
| 5 | Inner FS-MPC | `inner_fsmpc.py` + delay comp | 2 days |
| 6 | Outer energy PI | `outer_energy_pi.py` + tuning | 1 day |
| 7 | Simulator + ZOH | `simulator.py` integration | 1 day |
| 8 | Reproduce Fig 4 | First success milestone | 0.5 day |
| 9 | Reproduce Figs 5–10 | Remaining notebooks | 2 days |
| 10 | THD + extra metrics | Quantitative tables, paper omits these | 1 day |
| 11 | MAS adapter | Wrap as ICA for MAS-DT-SH integration | 1 day |
| **Total** | | **~12 working days** | **≈ 2.5 calendar weeks part-time** |

### 9.3 Where this slots into your active calendar

| Project | Connection | When to schedule |
|---|---|---|
| MAS-DT-SH Sprint 3 (Zone Agent + orchestrator skeleton) | Use the ICA wrapper as bottom-layer device controller | After Sprint 2 closes (17 May 2026) |
| MAS-DT-SH Sprint 4 (Switch + Substation Agents) | Cite this as the converter-side baseline | 24 May 2026 |
| APPEEC paper #2 (GFM/GFL estimator) | Cite Eq. (4) and (11) as supporting methodology | Before Wed 29 Apr send-Yan-Xu deadline if you want to add it |
| Thesis Ch4 (Math/Algorithm) | Section: "Single-converter FS-MPC baseline" | Stage 2 Sprint 2 (17 May) |

---

*End of forensic analysis. Linked code skeleton modules to be generated separately on request — say "scaffold the project" and I'll create the directory tree with stub files in `~/Desktop/fs_mpc_microgrid/`.*
