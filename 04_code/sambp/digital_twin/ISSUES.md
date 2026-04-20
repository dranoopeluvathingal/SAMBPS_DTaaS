# SAMBP Digital Twin Lab — Issue Tracker

Inline issue tracker for the `sambp/digital_twin` package.
Format: `TR-XX-vY.Z-a/b/c` — parent TR, target version, sequence letter.

All v0.2 issues are deferred until first journal submission.
Milestone **v0.2** closes when TR-43, TR-44, and TR-45 citation refreshes
are complete and the complex-measurement EKF is merged.

---

## Open

### TR-45-v0.2-a — Complex measurement model for EKFPhasorEstimator

**Title:** Extend EKFPhasorEstimator to complex observation `V1/I1 ∈ ℂ`  
**Priority:** High (blocks alpha estimation improvement)  
**Milestone:** v0.2  
**Filed:** 2026-04-15  
**Related:** TR-43-v0.2-a, TR-44-v0.2-a

**Body:**
The current measurement vector is `y = [|I1|, |I2|, |V1|/|I1|] ∈ ℝ³`.
Discarding the angle of `V1/I1` leaves an `alpha`–`Z_line` degeneracy in the
EKF Jacobian: both parameters enter only through the product `alpha·Z_line/k`,
so the EKF cannot separate them from a scalar Z_app alone.
Study G confirms: k_ibr RMSE improves 28.5× with phasor DFT, but alpha RMSE
improves only 1.18× (0.36 → 0.31).

**Planned fix:**
Extend to a complex observation model:
```
y_complex = [I1, I2, V1/I1]  ∈ ℂ³   (six real degrees of freedom)
```
The Jacobian `∂h/∂x` will be complex-valued (3×4 complex or 6×4 real after
splitting real/imaginary). This breaks the alpha–Z_line degeneracy via the
impedance angle.

**Acceptance criteria:**
- [ ] `EKFPhasorEstimator` updated to accept complex `y` (no API break for
      callers that only read `state_dict`)
- [ ] Study G re-run shows alpha RMSE < 0.15 (target: <50% of current 0.31)
- [ ] TR-45 §"Limitations" updated to record the result
- [ ] New tag `sambp-dt-lab-v0.2`

**References:** TR-45 §"Limitations and v0.2 Direction"; README.md "Known limitation"

---

### TR-43-v0.2-a — Rewrite TR-43 to cite the `sambp.digital_twin` package

**Title:** Rewrite TR-43 to cite the sambp.digital\_twin package  
**Priority:** Medium (deferred until first journal submission)  
**Milestone:** v0.2  
**Filed:** 2026-04-15  
**Related:** TR-44-v0.2-a, TR-45-v0.2-a

**Body:**
TR-43 currently cites the standalone script `run_digital_twin_study.py` as its
software artefact. The script has been superseded by the `sambp.digital_twin`
package (tag `sambp-dt-lab-v0.1`). v0.2 should refresh the TR-43 software
references to cite:

- `sambp.digital_twin.estimation.rls_estimator.RLSEstimator`
- `sambp.digital_twin.models.scenario_library.ScenarioLibrary`
- `sambp.digital_twin.run_dt_lab --study A, B`

This is a **citation refresh only** — all numerical results in TR-43 remain
identical. No re-analysis required.

**Acceptance criteria:**
- [ ] TR-43 `main_report43.tex` updated: standalone script reference → package module path
- [ ] TR-43 §Software/Reproducibility section points to `run_dt_lab --study A,B`
- [ ] Cross-reference to TR-44-v0.2-a and TR-45-v0.2-a added to TR-43 §"Relation to TR-44/45"
- [ ] PDF rebuilt; no numerical changes

**References:** README.md §Citation; TR-44-v0.2-a (parallel TR-44 refresh); TR-45-v0.2-a

---

### TR-44-v0.2-a — Rewrite TR-44 to cite EKFEstimator + EKFPhasorEstimator and add Study G cross-reference

**Title:** Rewrite TR-44 to cite EKFEstimator + EKFPhasorEstimator and add Study G cross-reference  
**Priority:** Medium (deferred until first journal submission)  
**Milestone:** v0.2  
**Filed:** 2026-04-15  
**Related:** TR-43-v0.2-a, TR-45-v0.2-a

**Body:**
TR-44 currently cites the standalone script `run_dt_estimation_study.py`. The
script has been superseded by the `sambp.digital_twin` package
(tag `sambp-dt-lab-v0.1`). v0.2 should refresh TR-44 to cite:

- `sambp.digital_twin.estimation.ekf_estimator.EKFEstimator`
- `sambp.digital_twin.estimation.ekf_phasor_estimator.EKFPhasorEstimator`
- `sambp.digital_twin.estimation.phasor_dft.PhasorDFT`
- `sambp.digital_twin.run_dt_lab --study C, D, G`

In addition, add a **Study G cross-reference section** to TR-44 showing:
- The 28.5× k_ibr RMSE improvement (EKFEstimator: 0.0517 pu → EKFPhasorEstimator: 0.0018 pu)
- The modest alpha improvement (1.18×: 0.36 → 0.31) and why (scalar Z_app degeneracy)
- A pointer to TR-45-v0.2-a for the complex-measurement fix

This is a **citation refresh + one new cross-reference section**. All existing
numerical results in TR-44 remain identical.

**Acceptance criteria:**
- [ ] TR-44 software references updated to package module paths
- [ ] TR-44 §Software points to `run_dt_lab --study C,D,G`
- [ ] New §"Study G cross-reference" added with phasor DFT comparison table
- [ ] Pointer to TR-45-v0.2-a for alpha/Z_line fix
- [ ] Cross-reference to TR-43-v0.2-a added
- [ ] PDF rebuilt; no changes to Studies C or D numbers

**References:** README.md §Citation; TR-43-v0.2-a (parallel TR-43 refresh); TR-45-v0.2-a (complex model)

---

### TR-87-v0.1-a — Alias miss for all-lowercase channel names in comtrade_adapter

**Title:** `extract_relay_waveforms()` returns zeros for CSV columns named `ia`, `va` etc.  
**Priority:** Medium (correctness defect; affects real PSCAD exports with lowercase headers)  
**Milestone:** v0.1-patch  
**Filed:** 2026-04-20 (discovered during SUBREPORT_TR87 validation)  
**Related:** TR-87

**Body:**  
`_IA_KEYS = ("Ia","IA","I_a","i_a","Ia_pu","Br_Ia")` — `"ia"` (no underscore,
all-lowercase) is absent. `read_pscad_csv()` preserves the column name verbatim,
so `pscad_fault_data.csv` (columns `ia,ib,ic`) loads into `ComtradeResult.channels`
correctly but `extract_relay_waveforms()` silently returns a zero array with a
`UserWarning`. The result is a FaultCase with all-zero current waveforms — incorrect.

**Reproduction:**
```python
from io_utils.comtrade_adapter import read_pscad_csv, extract_relay_waveforms
cr = read_pscad_csv("05_data/fault_waveforms/pscad_fault_data.csv")
wf = extract_relay_waveforms(cr)   # UserWarning; wf["ia"] == zeros
```

**Fix:**
```python
_VA_KEYS = ("Va","VA","V_a","v_a","va","Va_pu","Bus_Va")
_VB_KEYS = ("Vb","VB","V_b","v_b","vb","Vb_pu","Bus_Vb")
_VC_KEYS = ("Vc","VC","V_c","v_c","vc","Vc_pu","Bus_Vc")
_IA_KEYS = ("Ia","IA","I_a","i_a","ia","Ia_pu","Br_Ia")
_IB_KEYS = ("Ib","IB","I_b","i_b","ib","Ib_pu","Br_Ib")
_IC_KEYS = ("Ic","IC","I_c","i_c","ic","Ic_pu","Br_Ic")
```

**Acceptance criteria:**
- [ ] `pscad_fault_data.csv` pipeline returns non-zero `ia` waveform
- [ ] All existing synthetic tests still pass
- [ ] `UserWarning` no longer emitted for canonical lowercase headers

---

## Closed

*(none yet — v0.1 is the first tagged release)*

---

## Cross-reference matrix (v0.2 issues)

| Issue | TR-43-v0.2-a | TR-44-v0.2-a | TR-45-v0.2-a |
|---|:---:|:---:|:---:|
| TR-43-v0.2-a | — | ✓ Related | ✓ Related |
| TR-44-v0.2-a | ✓ Related | — | ✓ Related |
| TR-45-v0.2-a | ✓ Related | ✓ Related | — |

All three issues reference each other bidirectionally.
TR-45-v0.2-a is the highest-priority issue (code change required);
TR-43-v0.2-a and TR-44-v0.2-a are documentation refreshes that depend on
the v0.2 tag produced when TR-45-v0.2-a closes.
