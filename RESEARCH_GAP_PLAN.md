# SAMBP Research Gap-Filling Plan
## Novel Research Agenda: TR-56 to TR-67

**Date:** April 2026  
**Context:** Extends the SAMBP Inverse-Estimation framework (TR-03 to TR-55) to five unresolved gaps:  
(G1) DFIG/wind-specific fault modelling · (G2) Solar PV protection · (G3) 87T IBR extensions ·  
(G4) 87G generator differential · (G5) Generator protection suite (40, 78, 64G, 81)

**Prioritisation principle:** Mathematical novelty and disruption to existing protection theory first.  
Applied engineering and system integration second.

---

## PRIORITY RANKING — RESEARCH TRACKS

| Priority | Track | Core Mathematical Challenge | Novelty Level |
|:--------:|-------|----------------------------|:-------------:|
| 1 | TR-56 | Piecewise-ODE DFIG fault model with unknown crowbar breakpoint | ★★★★★ |
| 2 | TR-57 | Bayesian SPRT for IBR inrush vs. fault discrimination | ★★★★★ |
| 3 | TR-58 | Generalised equal-area for hybrid SG–IBR out-of-step | ★★★★★ |
| 4 | TR-59 | Virtual rotor differential (87G-DFIG) via slip-frequency observer | ★★★★☆ |
| 5 | TR-60 | Loss-of-excitation (Relay 40) with nonlinear IBR admittance correction | ★★★★☆ |
| 6 | TR-61 | Stator earth fault (64G) via optimal sub-harmonic injection | ★★★★☆ |
| 7 | TR-62 | Sparse LM model for PV inverter faults (zero-DC problem) | ★★★☆☆ |
| 8 | TR-63 | Under/over-frequency (81) in zero-inertia IBR networks | ★★★☆☆ |
| 9 | TR-64 | 87T complete IBR system integration | ★★★☆☆ |
| 10 | TR-65 | Comprehensive SG + IBR generator protection relay | ★★☆☆☆ |
| 11 | TR-66 | Monte Carlo robustness for TR-56 to TR-65 | ★★☆☆☆ |
| 12 | TR-67 | HIL validation protocol for new elements | ★★☆☆☆ |

---
---

# PHASE 1 — FOUNDATIONAL MATHEMATICS
## (Highest novelty — deepest disruption to existing protection theory)

---

## TR-56: Piecewise-ODE Fault Model and Inverse Estimation for DFIG (Type 3 Wind)

### Research Gap
All existing SAMBP inverse-estimation models (TR-03, sync_oc) assume a **continuously
differentiable** fault current governed by a single ODE system. The DFIG (Doubly-Fed
Induction Generator) violates this assumption fundamentally: when rotor current exceeds
the crowbar threshold I_cb, the crowbar fires and **discontinuously inserts** resistance R_cb
into the rotor circuit. The fault current transitions from a slow-decay pre-crowbar regime to
a fast-decay post-crowbar regime at an *a priori unknown* switching time t_cb. No existing
protection inverse-estimation framework handles unknown breakpoints in piecewise-ODE systems.

### Mathematical Formulation

**Pre-crowbar fault current model (t₀ ≤ t < t_cb):**

  i_a(t) = I_ss·sin(ωs·t + φ₀)
           + I_nat·sin((1-s)ωs·t + ψ)·exp(-(t-t₀)/τ_r')
           + I_dc·exp(-(t-t₀)/τ_s')·sin(φ₀)

where:
  τ_r' = L_r' / R_r        (rotor transient time constant, ~0.5–2 s)
  τ_s' = L_s' / R_s        (stator transient time constant, ~20–200 ms)
  I_nat = E_r / (R_r + jX_r') is the natural (slip-frequency) current component

**Post-crowbar model (t ≥ t_cb):**

  i_a(t) = I_ss·sin(ωs·t + φ_cb)
           + I_nat''·sin((1-s)ωs·t + ψ_cb)·exp(-(t-t_cb)/τ_r'')
           + I_dc''·exp(-(t-t_cb)/τ_s'')·sin(φ_cb)

where:
  τ_r'' = L_r' / (R_r + R_cb)    (crowbar greatly shortens τ_r'' → 5–30 ms)
  R_cb ≈ 5–20 R_r               (crowbar resistance, design dependent)

**Full DFIG parameter vector (10 parameters):**

  θ_DFIG = [t₀, t_cb, I_ss, I_nat, τ_r', τ_s', I_nat'', τ_r'', τ_s'', φ₀]ᵀ ∈ ℝ¹⁰

**Novel problem: t_cb is an unknown breakpoint.**
This makes the cost function non-smooth in t_cb.

**Proposed solution — Smoothed Heaviside continuation method:**

  Replace the sharp switch at t_cb with:
    h_ε(t, t_cb) = sigmoid((t - t_cb)/ε)    ε → 0 gives hard switch

  Composite model:
    î(t; θ_DFIG, ε) = [1 - h_ε]·i_pre(t; θ_pre) + h_ε·i_post(t; θ_post)

  Jacobian ∂î/∂t_cb = -(1/ε)·h_ε·(1-h_ε)·[i_post - i_pre] is now continuous → LM converges.

  Continuation schedule: ε ∈ {1ms, 0.5ms, 0.2ms, 0.1ms} — anneal toward hard switch.

**Crowbar detection sub-problem (initialise t_cb):**

  Prior to LM iteration, detect crowbar using changepoint detection on
  |di/dt| (crowbar causes rapid derivative change).
  Use CUSUM on |di_k/dt|:
    C_k = max(0, C_{k-1} + |di_k/dt| - μ₀ - κ)
  Alarm at C_k > h → initial estimate t̂_cb = k·T_s

**Confidence gate extension for DFIG:**

  κ_n(J_DFIG) bounded above by ≈ 120 (vs 50 for 87L) due to 10 parameters.
  New threshold: κ_max = 100 (relax from 30 due to higher dimensionality).
  Additional physics check: τ_r'' < τ_r' / 3 (crowbar must shorten time constant).

**Internal fault indicator for DFIG:**

  f_int,DFIG = 1 − w_1·|I_nat''−I_nat_expected(k_ibr)|/I_nat_expected
                 − w_2·max(0, τ_r'' − τ_r,cb_max)/τ_r,cb_max

  where I_nat_expected(k_ibr) is computed from the Digital Twin pre-fault estimate.

### Key Publications
- **Journal:** IEEE Transactions on Energy Conversion
  Title: "Inverse-Estimation-Based Protection for DFIG Wind Generators:
          Piecewise-ODE Model with Unknown Crowbar Breakpoint"
  Novelty: First application of unknown-breakpoint LM estimation to power system protection.

- **Conference:** IEEE PES General Meeting 2027
  Title: "Crowbar-Aware Fault Current Model for DFIG Protection in Active Distribution Networks"

### IP Potential
- **Patent Claim 1:** Method of estimating fault current parameters in a DFIG by fitting a
  piecewise-continuous fault current model with a trainable crowbar switching time using
  continuation-smoothed Levenberg–Marquardt optimisation.
- **Patent Claim 2:** A protection relay for wind generators comprising a crowbar-switching
  detector (CUSUM on |di/dt|) and a post-crowbar inverse estimator to discriminate internal
  faults from crowbar-limited rotor current transients.

---

## TR-57: Bayesian Sequential Probability Ratio Test for IBR Inrush vs. Fault in 87T

### Research Gap
The existing 87T model (TR-04) uses 2nd harmonic restraint (k₂ > δ₂ = 0.15) to distinguish
inrush from internal faults. This fails catastrophically with IBR sources:
  (a) IBR FRT controllers inject 2nd harmonic up to 20% during asymmetric faults →
      genuine faults are restrained (safety failure).
  (b) IBR-limited inrush (k_ibr pu max current) produces I_diff < 0.10 pu at moderate k_ibr →
      standard % differential may never pick up during genuine internal fault.

No existing protection standard (IEC 60255-111, IEEE C37.91) provides a solution for
IBR-connected transformers. This is a fundamental theoretical gap.

### Mathematical Formulation

**Physical insight:** Inrush and fault differ in waveform ASYMMETRY, not harmonic content.
  - Inrush: current flows in one direction only (core saturation is unidirectional)
    → large positive peaks, near-zero negative peaks
    → Asymmetry index A = (I_p+ − |I_p−|)/(I_p+ + |I_p−|) → +1
  - Internal fault (IBR-limited): current is symmetric (IBR current controller forces
    I_d² + I_q² = k_ibr²) → A ≈ 0
  - CT saturation (external fault): asymmetric but with opposite sign → A → −1

**Asymmetry Random Variable:**

  Observed per half-cycle: A_k = (I_pk,pos − I_pk,neg) / (I_pk,pos + I_pk,neg)  ∈ (−1, +1)

  Under H₀ (inrush): A_k ~ Truncated-Normal(μ₀ = +0.70, σ₀ = 0.15)
  Under H₁ (fault):  A_k ~ Truncated-Normal(μ₁ = 0.00, σ₁ = 0.08)

  These distributions are derived analytically from the transformer core saturation model
  (Jiles-Atherton B-H curve) and IBR current control bandwidth.

**Sequential Probability Ratio Test (SPRT):**

  Likelihood ratio per observation:
    Λ_k = f(A_k | H₁) / f(A_k | H₀)    (ratio of truncated-normal PDFs)

  Log-likelihood accumulator:
    S_n = Σ_{k=1}^{n} log(Λ_k)

  Decision boundaries (Wald's optimal boundaries):
    S_n ≥ log(B)  → TRIP (internal fault confirmed)   B = (1−β)/α
    S_n ≤ log(A)  → RESTRAIN (inrush confirmed)        A = β/(1−α)
    log(A) < S_n < log(B) → CONTINUE (collect next half-cycle)

  Target: α = 0.001 (false trip rate), β = 0.001 (missed trip rate)
  → A = log(0.001/0.999) = −6.91, B = log(0.999/0.001) = +6.91

**Expected decision time:**
  Under H₁ (fault): E[n | H₁] = (1−β)·log(B/A) / KL(H₁||H₀)
  KL divergence: KL(N(0,0.08) || N(0.70,0.15)) ≈ 4.8 nats
  → E[n | fault] ≈ 2.9 half-cycles ≈ 29 ms at 50 Hz  (meets 50 ms protection standard)

**CT saturation immunity:**
  Extend to 3-class SPRT: H₀ (inrush), H₁ (fault), H₂ (CT saturation)
  H₂: A_k ~ Truncated-Normal(μ₂ = −0.50, σ₂ = 0.20)
  Three-hypothesis SPRT: Sobel-Wald generalisation with 3×3 error probability matrix.

**Integration with existing SAMBP 87T (TR-04):**
  Modified gate: TRIP if (SPRT → H₁) AND (κ_n < 30) AND (∥r∥_n < 0.15)
  Replace: 2nd harmonic restraint (k₂ > δ₂) is completely removed.
  Retain: CT-distortion model f_int for external-fault security.

### Key Publications
- **Journal (Primary):** IEEE Transactions on Power Delivery
  Title: "Sequential Probability Ratio Test for Inrush Discrimination in IBR-Connected
          Transformer Differential Protection"
  Novelty: First rigorous Bayesian formulation of inrush vs. fault as sequential hypothesis
           test; proof of optimality under Wald's theorem; removal of 2nd harmonic restraint.

- **Journal (Secondary):** IET Generation, Transmission & Distribution
  Title: "Waveform Asymmetry as an IBR-Immune Inrush Restraint Criterion for 87T"

### IP Potential
- **Patent Claim 1:** Method of discriminating transformer inrush from internal fault using
  a sequential probability ratio test on per-half-cycle waveform asymmetry index, without
  harmonic restraint, applicable to IBR-connected power transformers.
- **Patent Claim 2:** A transformer protection relay comprising a three-hypothesis SPRT
  processor and an asymmetry index calculator operative on differential current samples.
- **Patent Claim 3:** Relay setting method for 87T using analytically derived SPRT boundaries
  from transformer core Jiles-Atherton parameters.
  (Significant commercialisation: every substation transformer connected to IBR needs this.)

---

## TR-58: Generalised Equal-Area Criterion and Out-of-Step Protection for Hybrid SG–IBR Networks

### Research Gap
Relay 78 (out-of-step) is based on the classical equal-area criterion (EAC) valid only for
purely synchronous networks. With GFM (grid-forming) IBR in the network:
  - GFM inverters have a "virtual rotor angle" δ_virt governed by droop: dδ_virt/dt = ω_droop
  - GFM provides power P_IBR = E·V/X·sin(δ_sg − δ_virt) that depends on SG angle δ_sg
  - This creates a COUPLED second-order (SG) + first-order (GFM) ODE system
  - The classical EAC decelerating area integral is no longer correct
  - No existing equal-area formulation accounts for GFM virtual inertia and droop coupling

This is an unsolved problem in power systems stability theory with direct protection implications.

### Mathematical Formulation

**Hybrid swing equations:**

  SG:  M·δ̈_sg = P_m − P_e,sg(δ_sg, δ_virt) − D·δ̇_sg
  GFM: τ_droop·δ̇_virt = P_ref,IBR − P_e,IBR(δ_sg, δ_virt)

  Power exchange:
    P_e,sg  = V_sg·V_bus/X_sg · sin(δ_sg − δ_bus)
    P_e,IBR = V_IBR·V_bus/X_IBR · sin(δ_virt − δ_bus)

  Eliminating δ_bus (lossless network Kirchhoff equations):
    P_total = P_e,sg + P_e,IBR (conservation)
    → P_e,sg = f(δ_sg, δ_virt, network topology)

**Resulting coupled ODE:**

  [δ̈_sg    ]   [g₁(δ_sg, δ̇_sg, δ_virt)    ]
  [δ̇_virt  ] = [g₂(δ_sg, δ_virt) / τ_droop  ]

**Lyapunov stability analysis:**

  Candidate function V(δ_sg, δ̇_sg, δ_virt):
    V = ½·M·δ̇_sg² + U_sg(δ_sg) + U_IBR(δ_virt)

  where U_sg = −∫P_e,sg dδ_sg (potential energy), U_IBR = −∫P_e,IBR dδ_virt

  Critical energy V_cr = V at the controlling unstable equilibrium point (CUEP)
  → Stability: V < V_cr (equal area generalisation: kinetic energy < potential well depth)

**Generalised EAC (GEAC):**

  Accelerating area:  A_acc = ∫_{δ₀}^{δ_fault}  (P_m − P_e,sg − P_IBR_support) dδ_sg
  Decelerating area:  A_dec = ∫_{δ_fault}^{δ_cr} (P_e,sg + P_IBR_support − P_m) dδ_sg

  Key result: IBR power support INCREASES A_dec by:
    ΔA_dec = ∫_{δ_fault}^{δ_cr} P_e,IBR(δ_sg, δ_virt(t)) dδ_sg

  δ_virt(t) is itself a function of time via the GFM droop equation → integral is
  path-dependent (not purely potential energy). Must solve coupled ODE numerically
  or use a two-timescale approximation (if τ_droop << T_swing):

  Quasi-static approximation: δ_virt ≈ δ_virt,eq(δ_sg) (GFM tracks instantaneously)
  → GEAC becomes: A_dec,eff = ∫ (P_e,sg + P_IBR,eq(δ_sg) − P_m) dδ_sg
  → Explicit closed-form exists for simplified network.

**IBR-corrected Relay 78 blinder settings:**

  Classical blinder: |dZ/dt| > threshold, Z crosses inner Mho
  IBR correction: Apparent impedance includes IBR reactive support:
    Z_app = V_sg/(I_sg + I_IBR_contribution)
  → IBR reactive current shifts the impedance locus inward (reduces apparent impedance)
  → Classical blinder triggers nuisance operation during GFM reactive support transients

  Proposed: Corrected inner blinder:
    R_inner,corrected = R_inner,classical × (1 + k_Q·Q_IBR/Q_rated)
  where k_Q is derived from the Lyapunov stability margin.

### Key Publications
- **Journal (Primary):** IEEE Transactions on Power Systems
  Title: "Generalised Equal-Area Criterion for Hybrid Synchronous–Inverter Networks
          and Out-of-Step Relay Setting Correction"
  Novelty: First GEAC formulation with GFM virtual inertia coupling; Lyapunov
           energy function for mixed-order ODE system; closed-form blinder correction.
  (This paper has scope for ~40 citations in first year — it solves a known open problem.)

- **Journal (Secondary):** IEEE Transactions on Energy Conversion
  Title: "Out-of-Step Protection Relay Design for GFM-Rich Active Distribution Networks"

### IP Potential
- **Patent Claim 1:** Method of calculating out-of-step relay blinder settings by solving
  a coupled swing-equation system for a hybrid SG–GFM network and applying a Lyapunov
  energy correction to the classical equal-area criterion.
- **Patent Claim 2:** Out-of-step relay comprising a real-time GFM power support estimator
  and a dynamic blinder adjustment algorithm.
  (Directly relevant to all GFM grid-code compliance projects globally.)

---

# PHASE 2 — GENERATOR PROTECTION EXTENSIONS

---

## TR-59: Virtual Rotor Differential (87G-DFIG) Using Slip-Frequency State Observer

### Research Gap
Generator differential (87G) requires current measurements on BOTH sides of the
protected winding. For DFIG: stator is accessible (standard CTs), but rotor CTs are
impractical (rotating slip rings, variable frequency). No existing 87G standard
(IEC 60255-111) covers DFIG. The rotor current must be *estimated* from stator
measurements using the DFIG machine model — a mathematically non-trivial
inverse problem because DFIG has complex slip-dependent dynamics.

### Mathematical Formulation

**DFIG machine equations (dq frame, generator convention):**

  v_ds = R_s·i_ds − ω_s·L_s·i_qs + L_s·(di_ds/dt) + L_m·(di_dr/dt)
  v_qs = R_s·i_qs + ω_s·L_s·i_ds + L_s·(di_qs/dt) + L_m·(di_qr/dt)
  v_dr = R_r·i_dr − s·ω_s·L_r·i_qr + L_r·(di_dr/dt) + L_m·(di_ds/dt)
  v_dq = R_r·i_qr + s·ω_s·L_r·i_dr + L_r·(di_qr/dt) + L_m·(di_qs/dt)

**State: x = [i_ds, i_qs, i_dr, i_qr]ᵀ, Inputs: v_s (measured), v_r (known from converter)**

**Reduced observer (rotor current estimator without rotor voltage measurement):**

  Since v_r is commanded by the RSC (Rotor Side Converter) — and RSC output voltage
  can be read from the converter controller over IEC 61850 MMS — the full state
  observer can be realised:

  Extended Kalman Filter (EKF):
    x̂_{k+1} = A(s_k)·x̂_k + B·u_k + K_EKF·(y_k − C·x̂_k)
    y_k = [i_ds, i_qs]ᵀ  (stator currents, measured)
    u_k = [v_ds, v_qs, v_dr, v_qr]ᵀ  (stator voltages + RSC output)

  A(s_k) depends on slip s_k (time-varying) → EKF uses Jacobian ∂A/∂s.

**Virtual rotor differential:**

  Estimated rotor current (referred to stator): î_r,abc = T_park⁻¹(θ_r)·[î_dr, î_qr]ᵀ
  Stator current: i_s,abc (measured)
  Virtual differential current: i_diff,DFIG = |i_s,abc − a_eff·î_r,abc|
  where a_eff = N_stator/N_rotor (turns ratio, nameplate data).

  TRIP condition: i_diff,DFIG > I_diff,trip AND confidence γ_EKF > γ_min

**Fault vs. normal operation check:**
  Internal stator fault: i_diff,DFIG increases rapidly (fault current bypasses winding)
  Internal rotor fault: î_r,abc error increases (observer model mismatch) AND i_s unbalance
  External fault: observer tracks correctly, i_diff,DFIG ≈ 0 (observer compensates)

**Confidence γ_EKF:**
  Based on EKF innovation covariance S_k = C·P_k·Cᵀ + R:
    γ_EKF = exp(−∥ν_k∥²_{S_k⁻¹} / N_window)
    where ν_k = y_k − C·x̂_k is the innovation vector.
  High innovation = poor model fit = low confidence (no spurious trip).

### Key Publications
- **Journal:** IEEE Transactions on Energy Conversion
  Title: "Generator Differential Protection for DFIG Wind Turbines Using
          Slip-Frequency EKF Rotor Current Observer"
  Novelty: First virtual 87G for DFIG; observer-based protection; confidence gate
           using EKF innovation covariance.

### IP Potential
- **Patent Claim 1:** Method of detecting internal faults in a doubly-fed induction generator
  by estimating rotor-side winding current using an extended Kalman filter driven by
  stator terminal measurements and RSC voltage commands, and computing a virtual
  differential current without physical rotor current transformers.

---

## TR-60: Loss-of-Excitation Protection (Relay 40) with Nonlinear IBR Admittance Correction

### Research Gap
Classical Relay 40 uses fixed Mho circles in the admittance plane (Y-plane):
  Inner zone (Zone 1): centred at jB₁, radius R₁ (partial LOE)
  Outer zone (Zone 2): centred at jB₂, radius R₂ (full LOE, stability limit)
Settings: B₁ = 1/(2X_d'), R₁ = 1/(2X_d'); B₂ = 1/(X_d + X_d')/2, etc.

With GFM IBR providing reactive support Q_IBR(V) = k_q·(V_ref − V):
  - IBR reactive current shifts the terminal admittance: Y_app ≠ Y_SG
  - The relay "sees" an admittance that includes IBR contribution
  - Classical Mho circles trigger nuisance trips during normal GFM voltage support
  - Classical Mho circles miss LOE events when GFM masks the voltage drop

**This is an unresolved gap in IEEE C37.102 (SG protection guide) — not addressed
for IBR-rich environments.**

### Mathematical Formulation

**Apparent admittance at generator terminals:**

  Y_app = I_sg / V_sg = (I_sg_physical + I_IBR_injection) / V_sg

  IBR reactive injection (GFM droop):
    I_IBR = jQ_IBR / V_sg* = j·k_q·(V_ref − |V_sg|) / V_sg*
    → ΔY_IBR = j·k_q·(V_ref − |V_sg|) / |V_sg|²  (linearised for |V_sg| near 1 pu)

  Modified apparent admittance:
    Y_app,mod = Y_sg + ΔY_IBR(V_sg)

**LOE impedance locus derivation with IBR:**

  Without LOE: Y_sg = Y_sg,normal (outside both Mho circles)
  With LOE: Y_sg evolves along the classical LOE locus (ellipse in Y-plane)
  With IBR: Y_app,mod = Y_sg + ΔY_IBR → the measured locus is SHIFTED and DISTORTED

  Closed-form correction for linearised IBR droop:
    Y_app,mod ≈ Y_sg + j·k_q·(V_ref − |V_sg|) / |V_sg,0|²

  IBR-corrected relay settings:
    B₁,corrected = B₁,classical − k_q / |V_sg,0|²
    R₁,corrected = R₁,classical × √(1 + (k_q·ΔV)² / |V_sg,0|⁴)

  where ΔV = V_ref − |V_sg,0| is the normal GFM voltage error (≈ ±0.01 pu).

**Discrimination between GFM reactive support and LOE onset:**

  LOE signature: Y_sg crosses into Zone 1 monotonically (excitation decays)
  GFM support: ΔY_IBR oscillates with AC voltage regulation time constant τ_avr

  Temporal filter: Apply rate-of-change threshold on ΔY:
    Trip confirmed only if ΔY_corrected is monotonically increasing for T_delay = 200 ms
    (classical delay; now applied to the IBR-corrected admittance)

### Key Publications
- **Journal:** IEEE Transactions on Power Delivery
  Title: "IBR-Corrected Loss-of-Excitation Protection for Synchronous Generators
          in GFM-Rich Active Distribution Networks"

---

## TR-61: Stator Earth Fault Protection (64G) via Optimal Sub-Harmonic Injection for IBR Generators

### Research Gap
Two approaches exist for 100% stator earth fault protection:
  (a) Fundamental frequency neutral voltage (64G): covers 95% winding only
  (b) 3rd harmonic method: requires SG to produce 3rd harmonic naturally — PV/wind inverters
      do NOT produce measurable 3rd harmonic at neutral (IBR current control suppresses it)

The sub-harmonic injection method (20 Hz or 25 Hz) exists for SGs (IEEE C37.101) but:
  - Optimal injection frequency has never been derived for IBR generators with LC filters
  - IBR LCL filter attenuates injection signal differently at each frequency
  - IBR current controllers may interact with injected sub-harmonic
  - Injection amplitude must be below IBR current control bandwidth to avoid interference

**No existing work derives the optimal injection frequency for IBR earth fault protection.**

### Mathematical Formulation

**Inverter LCL filter transfer function (injection signal path):**

  G_LCL(jω_inj) = 1 / (L_f·C_f·ω_inj² − 1 + jω_inj·(R_f·C_f))
  where L_f, C_f, R_f are filter inductance, capacitance, damping resistance.

**Current controller interaction (IBR rejects sub-harmonic if in control bandwidth):**

  IBR current control bandwidth: f_BW ≈ f_sw/10 ≈ 150 Hz (for 1.5 kHz switching)
  Controller rejection ratio at f_inj: H_ctrl(jω_inj) = L(jω_inj)/(1 + L(jω_inj))
    where L = G_ctrl·G_plant (open-loop, available from IBR specification sheet)
  For f_inj << f_BW: H_ctrl ≈ 1 (controller rejects injection → no measurement possible)
  For f_inj >> f_BW: H_ctrl ≈ 0 (controller transparent → injection passes through)

**Earth fault detection using injection:**

  Neutral-to-earth impedance: Z_ne(jω_inj) = V_n / I_inj
  Healthy: Z_ne = Z_neutral_earthing (known, high impedance) → I_inj ≈ 0
  Faulted: Z_ne drops to R_fault || Z_neutral_earthing → I_inj increases measurably

**Optimal injection frequency derivation:**

  Optimisation problem:
    f_inj* = argmax  SNR(f_inj)
    subject to: f_inj > 2·f_BW  (above controller bandwidth — no rejection)
                f_inj ≠ 3f₀, 5f₀, 7f₀  (avoid IBR harmonic frequencies)
                f_inj < f_resonance,LCL  (below LCL resonance to avoid amplification)
                |G_LCL(jω_inj)| > G_min  (LCL must transmit the signal)

  SNR function:
    SNR(f_inj) = |ΔI_inj,fault|² / P_noise(f_inj)

  where P_noise(f_inj) is the measured noise PSD at frequency f_inj (IBR switching harmonics).

  **Closed-form solution** (for simplified LC filter, no damping):
    f_inj,optimal ≈ max(2·f_BW, f₀ + Δf_margin) where Δf_margin = 5–15 Hz
    For typical IBR: f_BW = 150 Hz, f₀ = 50 Hz → f_inj* ≈ 25–35 Hz
    (This recovers the industry-empirical 20 Hz value from first principles.)

### Key Publications
- **Journal:** IEEE Transactions on Industrial Electronics
  Title: "Optimal Sub-Harmonic Injection Frequency for 100% Stator Earth Fault Protection
          of Grid-Connected Inverter-Based Generators"
  Novelty: First analytic derivation of injection frequency from IBR filter/control parameters.

### IP Potential
- **Patent Claim:** Method of selecting the injection signal frequency for stator earth fault
  protection of an inverter-based generator by solving an SNR optimisation subject to
  current-controller rejection constraints and LCL filter transmission constraints.

---

# PHASE 3 — PV PROTECTION AND SYSTEM COMPLETION

---

## TR-62: Sparse Inverse Estimation Model for Solar PV Fault Discrimination (Zero-DC Problem)

### Research Gap
All SAMBP 87L and OC models include a DC offset term (I_DC·exp(−t/τ_DC)) because SG and
DFIG fault currents have electromagnetic flux-driven DC components. PV inverters have
**zero DC offset** in fault current because there is no magnetic flux to maintain:
  - The existing 4-parameter 87L model (TR-03) applied to PV-fed lines has an ill-conditioned
    Jacobian: the τ_DC column becomes numerically degenerate (τ_DC → ∞, I_DC → 0)
  - Condition number κ_n diverges → Stage-2 gate always vetoes → 87L cannot protect PV lines

This requires a new, **sparser model** for IBR-only lines.

### Mathematical Formulation

**PV fault current model (2 parameters only):**

  î(t; θ_PV) = I_inv · sin(ωt + φ_inv)   for t ≥ t₀
  θ_PV = [I_inv, φ_inv]ᵀ ∈ ℝ²

  This is the minimal model for IBR fault current with fast current control (no DC, no natural frequency).
  Jacobian: J_PV ∈ ℝ^{N×2} — condition number κ_n(J_PV) ≤ 3 analytically (near-orthogonal columns)

**Model selection criterion (SAMBP network with mixed SG + PV):**

  Use Digital Twin (TR-43) to determine k_ibr (IBR fraction at the fault end).
  Model selection:
    k_ibr < 0.05:  Use 4-parameter model (SG-dominated) — existing 87L
    0.05 ≤ k_ibr ≤ 0.50: Use 6-parameter hybrid model (add IBR term)
    k_ibr > 0.50:  Use 2-parameter model (IBR-dominated) — new TR-62 model

**Hybrid model for mixed SG–PV networks:**

  î(t; θ_hyb) = I_sg·sin(ωt + φ_sg) + I_sg,dc·exp(−t/τ_sg) +
                I_pv·sin(ωt + φ_pv)

  θ_hyb = [I_sg, φ_sg, I_sg,dc, τ_sg, I_pv, φ_pv]ᵀ ∈ ℝ⁶

  Key insight: I_pv and I_sg have DIFFERENT phase angles (φ_pv ≠ φ_sg) due to different
  source impedance angles → 6-parameter model remains identifiable.

**PV generator protection (87G-PV equivalent):**

  No stator winding → no conventional differential.
  Equivalent: DC-domain symmetry monitoring + AC-domain overcurrent.

  DC bus midpoint voltage asymmetry:
    V_asym = (V_dc+ − V_dc−) / (V_dc+ + V_dc−)
    Healthy: |V_asym| < 0.02 (symmetric ground leakage)
    Earth fault on string: |V_asym| > 0.10 within 5 ms

  Combined 87G-PV trip logic:
    TRIP = (|V_asym| > V_thr) AND (|I_ac,diff| > I_thr) AND (ROCOF < ROCOF_island_thr)
    (ROCOF check: prevent tripping during anti-islanding condition)

### Key Publications
- **Journal:** IEEE Transactions on Industrial Electronics
  Title: "Sparse Inverse Estimation for Differential Protection of PV-Connected Lines:
          Model Selection Under Varying IBR Penetration"

---

## TR-63: Under/Over-Frequency Protection (81) in Zero-Inertia IBR Networks

### Research Gap
Conventional Relay 81 (ROCOF + frequency threshold) was designed for networks with
rotational inertia (H ≥ 2 s). For pure-IBR microgrids: H_system → 0 as IBR penetration
increases. The rate-of-change-of-frequency (ROCOF) becomes:

  df/dt = −ΔP / (2H) → ∞ as H → 0

This causes:
  (a) Nuisance 81 trips for tiny load steps in low-inertia networks
  (b) Anti-islanding 81 thresholds (ROCOF > 0.5 Hz/s) may not be met in pure-IBR islands
      where GFM inverters regulate frequency actively
  (c) 81 settings derived from classical swing equation are meaningless for GFM networks

### Mathematical Formulation

**Virtual inertia model for GFM fleet:**

  GFM droop inertia emulation:
    J_virt = P_GFM / (ω₀ · k_droop · dω/dt)
  Effective system inertia: H_eff = H_SG + Σ(H_virt,i · P_GFM,i/P_total)

  For pure-GFM island: H_eff = H_virt (tunable) — can be set to any value.

**81 setting as function of H_eff:**

  Minimum ROCOF for reliable 81 operation:
    (df/dt)_min = ΔP_min / (2·H_eff·f₀) where ΔP_min is the minimum detectable imbalance

  For H_eff → 0: (df/dt)_min → ∞ → conventional 81 is useless.

**Proposed: Inertia-normalised frequency deviation index (IFDI):**

  IFDI_k = Δf_k / H_eff,k  (normalised frequency excursion per unit inertia)

  This remains bounded even as H_eff → 0 because Δf also becomes smaller
  (GFM inverters regulate frequency → Δf is limited by droop gain).

  Trip condition: IFDI > IFDI_trip  (settings derived from maximum allowable ΔP)
  Anti-islanding: IFDI > IFDI_island (larger threshold for islanding detection)

### Key Publications
- **Journal:** IEEE Transactions on Smart Grid
  Title: "Inertia-Normalised Frequency Deviation Index for 81 Protection in
          GFM-Rich Zero-Inertia Microgrids"

---

# PHASE 4 — SYSTEM INTEGRATION AND VALIDATION

---

## TR-64: Complete IBR-Aware 87T System Integration

Extend TR-04 with:
  - Replace 2nd harmonic restraint with SPRT asymmetry criterion (from TR-57)
  - Add IBR fault model (2-parameter, from TR-62) for IBR-connected transformer 87T
  - Validate across all IBR transformer topologies:
      Δ/Y (delta primary), Y/Y (wye-wye), Dyn11 (most common distribution transformer)
  - Parametric Monte Carlo: k_ibr ∈ [0.06, 1.0], inrush current ∈ [5, 12 pu], fault ∈ [0.10, 1.0 pu]
  - Target: TPR = 1.000, FPR = 0.000 across 5,000 trials

### Key Publications
- **Journal:** IEEE Transactions on Power Delivery
  Title: "IBR-Aware Transformer Differential Protection: Asymmetry SPRT and
          Zero-DC Sparse Model Integration Study"

---

## TR-65: Comprehensive Generator Protection Relay — All Elements Integrated

Integrates TR-56 to TR-63 into a single generator protection relay specification covering:

| Element | SG | DFIG | PV |
|---------|:--:|:----:|:--:|
| 87G differential | Existing (sync_oc) | TR-59 (virtual) | TR-62 (DC asymm) |
| 40 LOE | TR-60 (IBR-corrected) | N/A | N/A |
| 78 out-of-step | TR-58 (GEAC) | N/A | N/A |
| 64G stator earth | TR-61 (sub-harmonic) | TR-61 (adapted) | TR-62 (DC symm) |
| 81 over/under-freq | Classical | TR-63 (IFDI) | TR-63 (IFDI) |
| 50/51 overcurrent | Existing | Existing | TR-62 |
| 67 directional | Existing | TR-38/TR-32 | TR-32 |

### Key Publications
- **Journal:** IEEE Transactions on Power Delivery
  Title: "Complete Adaptive Generator Protection Relay for SG, DFIG, and PV
          in Active IBR-Rich Distribution Networks"
  (This is a synthesis/integration paper — high citation value as a reference paper)

---

## TR-66: Monte Carlo Robustness Study for TR-56 to TR-65

Parametric robustness across all new protection elements:
  Parameters: machine rating, transformer vector group, IBR control mode (GFL/GFM),
              grid strength (SCR ∈ [1.5, 10]), CT error (ε_CT ∈ [0, 0.01]),
              noise (σ_I = 0.005 pu), sub-harmonic injection SNR ∈ [10, 40 dB]
  10,000 Monte Carlo trials per element
  Target: TPR ≥ 0.999, FPR ≤ 0.001 for all elements

---

## TR-67: HIL Validation Protocol Extension

Hardware validation of TR-56 to TR-65 on existing HIL platform (TR-53):
  - Add DFIG machine model to real-time simulator
  - Add PV inverter emulator (rapid shutdown simulation)
  - Add crowbar switching event trigger (FPGA-controlled)
  - Validate SPRT 87T: confirm decision time < 50 ms across all inrush magnitudes
  - Validate GEAC relay 78: confirm no nuisance trip under GFM reactive support
  - 23-item commissioning checklist (extension of TR-54)

---
---

# RESEARCH ROADMAP

## Timeline and Dependencies

```
2026 Q2-Q3   TR-56  DFIG fault model (math foundation)
             TR-57  Bayesian SPRT 87T (math foundation)

2026 Q3-Q4   TR-58  Generalised EAC 78 (math foundation)
             TR-59  Virtual 87G-DFIG (depends on TR-56)

2027 Q1-Q2   TR-60  LOE with IBR (depends on TR-58)
             TR-61  Sub-harmonic 64G (independent)
             TR-62  Sparse PV model (depends on TR-57 insight)

2027 Q2-Q3   TR-63  IFDI 81 (depends on TR-58)
             TR-64  87T integration (depends on TR-57, TR-62)

2027 Q3-Q4   TR-65  Generator relay integration (depends on TR-56 to TR-63)
             TR-66  Monte Carlo robustness
             TR-67  HIL validation
```

---

# IP AND PUBLICATION SUMMARY

## Patent Portfolio (6 core patent families)

| # | Title | Claims | Novelty Basis |
|---|-------|--------|---------------|
| P1 | Piecewise-ODE DFIG protection with crowbar breakpoint | LM with continuation smoothing + CUSUM | First piecewise-ODE inverse estimation in protection |
| P2 | SPRT inrush discrimination for IBR transformers | 3-hypothesis SPRT on waveform asymmetry | Removes 2nd harmonic restraint — paradigm change |
| P3 | Hybrid SG–IBR out-of-step relay with GEAC correction | GEAC Lyapunov + blinder correction | First OOS relay for GFM-coupled networks |
| P4 | Virtual 87G for DFIG using EKF rotor observer | Software rotor differential without rotor CTs | Eliminates rotor CT installation cost |
| P5 | Optimal injection frequency for IBR 64G protection | SNR optimisation closed-form | First analytic injection frequency for IBR filters |
| P6 | Model-selection 87L for mixed SG–PV networks | k_ibr-driven sparse/full model switching | Adaptive protection architecture |

---

## Journal Publication Plan (9 papers)

| Paper | Journal | TR | Status | Core Novelty |
|-------|---------|-----|--------|-------------|
| J1 | IEEE Trans. Energy Conversion | TR-56 | Planned 2026 Q4 | DFIG piecewise-ODE LM |
| J2 | IEEE Trans. Power Delivery | TR-57 | Planned 2027 Q1 | SPRT inrush discrimination |
| J3 | IEEE Trans. Power Systems | TR-58 | Planned 2027 Q1 | Generalised EAC for hybrid networks |
| J4 | IEEE Trans. Energy Conversion | TR-59 | Planned 2027 Q2 | Virtual 87G-DFIG EKF |
| J5 | IEEE Trans. Power Delivery | TR-60 | Planned 2027 Q2 | LOE with IBR admittance correction |
| J6 | IEEE Trans. Industrial Electronics | TR-61 | Planned 2027 Q3 | Optimal 64G injection |
| J7 | IEEE Trans. Industrial Electronics | TR-62 | Planned 2027 Q3 | Sparse PV inverse model |
| J8 | IEEE Trans. Smart Grid | TR-63 | Planned 2027 Q4 | IFDI for zero-inertia 81 |
| J9 | IEEE Trans. Power Delivery | TR-65 | Planned 2028 Q1 | Complete generator relay integration |

---

## Conference Papers (5 papers)

| Paper | Conference | TR | Year |
|-------|------------|----|------|
| C1 | IEEE PES General Meeting | TR-56 | 2027 |
| C2 | IEEE ISGT Europe | TR-57 | 2027 |
| C3 | CIGRE Paris | TR-58 | 2027 |
| C4 | IEEE ICDCM | TR-61+62 | 2028 |
| C5 | IEEE PES General Meeting | TR-65 | 2028 |

---

# CRITICAL ASSESSMENT

## Which Gaps Are Truly Novel vs. Incremental?

**Highest disruption (rewrite existing standards):**
1. **TR-57** — Removing 2nd harmonic restraint from 87T (IEC 60255-111 and IEEE C37.91
   both mandate it; this paper provides a mathematical proof that it is unsafe for IBR-connected
   transformers and proposes a provably better alternative). High citation ceiling.

2. **TR-58** — GEAC for hybrid networks. The classical EAC is in every power systems
   textbook. A generalisation that includes GFM inverters is a 50-year-old problem
   being solved for the first time. Very high-impact journal paper.

**High novelty (new solutions to known problems):**
3. **TR-56** — DFIG piecewise-ODE. Technically the hardest paper in this plan.
   Unknown breakpoint estimation is a genuinely hard inverse problem.

4. **TR-59** — Virtual 87G-DFIG. Eliminates expensive rotor CTs in practice.
   High commercial value.

**Solid but more incremental:**
5-9: TR-60 to TR-65 — Apply well-understood mathematical tools (EKF, SPRT, SNR optimisation)
to new protection contexts. Still publishable in top journals but less likely to be
landmark papers.

## Recommended Starting Point
Begin with **TR-57** in parallel with **TR-58**:
- TR-57 can be completed in ~3 months (SPRT is well-understood; the IBR asymmetry
  model derivation is the key new work)
- TR-58 requires ~4 months (Lyapunov construction for coupled ODE is the hard part)
- These two papers establish the mathematical credentials for the full generator protection
  work that follows.
