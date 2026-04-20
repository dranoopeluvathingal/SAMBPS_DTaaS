# SUBREPORT_TR18 — Mho Distance Relay (21/21P)

**TR ID:** TR-18  
**Full title:** Mho Distance Relay (21/21P): Zone Reach Verification, Selectivity, and Coordination with 87B/87L Protection  
**Ref:** IITM/EE/PhD/AVE/TR-18/2026  
**Folder:** `03_technical_reports/phase_2_87L_deep/TR18_mho_distance_21/`  
**Report file:** `main_report18.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 2 — 87L Deep-Dive  
**Thesis allocation:** Ch. 5 (Distance Protection) — third SAMBP function integration  
**Cross-linked TRs:** TR-15/TR-17 (87L primary), TR-16 (87B/87L coordination), TR-19 (multi-feeder transfer)

---

## §1 Scope

**What TR-18 IS:**
- Three-zone Mho distance relay (21/21P): adds the third protection function to the SAMBP suite
- Zone 1 (instantaneous, 80% reach), Zone 2 (0.30s, 120%), Zone 3 (0.60s, 180%)
- **12/12 selectivity scenarios correct (100%)**: bolted, HIF, load, and out-of-zone cases
- **Non-conflicting coordination** confirmed for all seven fault classes with 87B and 87L
- **Complementary HIF coverage**: 21 cannot reach HIF (Z_m=j2.275 pu vs Zone 3 reach j0.090 pu); 87L is sole HIF detector
- Load blinder: R_blinder=0.40 pu; no load encroachment confirmed

**What TR-18 IS NOT:**
- Not an adaptive distance relay (IBR infeed compensation deferred to future work)
- Not replacing 87L — back-up function only for line faults
- Not hardware validated

**Core contribution:** Formally establishes the three-function 87B/87L/21 coordination hierarchy: 87B primary for bus faults; 87L primary for line faults (including HIF); 21 provides back-up for bolted/low-resistance faults and remote bus faults via Zone 2.

---

## §2 State of the Art

| Ref | Contribution | Limitation vs. TR-18 |
|---|---|---|
| TR-16 | 87B/87L non-conflict proved | No distance function |
| Anderson1999/Ziegler2006 | Mho relay theory | No SAMBP integration |

**Novelty:** First distance function in the SAMBP suite; establishes three-function coordination hierarchy; identifies HIF as exclusively in 87L domain (21 structurally unable to reach arc-impedance faults).

---

## §3 Method

### 3.1 Mho Operating Criterion

```
Z_m = V_relay / I_relay    (positive sequence, 21P)
Z_ag = V_a / (I_a + k0 × 3I0)   (ground, 21G; k0=0.667)

Mho criterion (self-polarised):
  Re[(Z_m - Z_reach) × Z_m*] ≤ 0
  
Circle: centre = Z_reach/2, radius = |Z_reach|/2
  → passes through origin; resets at load impedance
```

### 3.2 Relay Configuration

| Parameter | Value |
|---|---|
| Z_line | j0.05 pu |
| MTA | 80° |
| k0 (zero-seq compensation) | 0.667 |
| Zone 1 reach (k1=0.80) | j0.040 pu |
| Zone 2 reach (k2=1.20) | j0.060 pu, 0.30s |
| Zone 3 reach (k3=1.80) | j0.090 pu, 0.60s |
| Load blinder | R_blinder=0.40 pu |

---

## §4 Validation

### 4.1 Zone boundary sweep (0.005 pu resolution, 3ph bolted)

All three zone boundaries match design values exactly: Zone 1 at d=0.800, Zone 2 at d=1.200, Zone 3 at d=1.800.

### 4.2 12-scenario selectivity matrix

| ID | Description | Z_m (pu) | Z1 | Z2 | Z3 | Trip | Notes |
|---|---|---|---|---|---|---|---|
| INT_25 | d=25%, 3ph | j0.013 | ✓ | ✓ | ✓ | Z1 | 87L concurrent |
| INT_50 | d=50%, 3ph | j0.025 | ✓ | ✓ | ✓ | Z1 | 87L concurrent |
| INT_79 | d=79%, 3ph | j0.040 | ✓ | ✓ | ✓ | Z1 | 87L concurrent |
| INT_82 | d=82%, 3ph | j0.041 | — | ✓ | ✓ | Z2 (0.3s) | 87L faster |
| RBUS | Remote bus d=1.05 | j0.053 | — | ✓ | ✓ | Z2 (0.3s) | 87B remote; 21 back-up |
| BKUP | Beyond remote d=1.45 | j0.072 | — | — | ✓ | Z3 (0.6s) | Back-up only |
| LBUS | Local bus d=0.02 | j0.001 | ✓ | ✓ | ✓ | Z1 | 87B primary; 21 overlap |
| AG_50 | ag d=50% bolted | j0.025 | ✓ | ✓ | ✓ | Z1 | 87L concurrent |
| **AG_HIF** | **ag HIF Z_arc=j1.5** | **j2.275** | **—** | **—** | **—** | **no** | **87L sole detector** |
| LOAD_N | Normal load R=0.5 | 0.5+j0.1 | — | — | — | no | blinder active |
| LOAD_H | Light load R=0.3 | 0.3+j0.08 | — | — | — | no | outside circle |
| OOZ | Out of zone d=2.0 | j0.100 | — | — | — | no | correct no-trip |

**12/12 correct (100%).**

### 4.3 Three-function coordination

| Fault type | 87B | 87L | 21 | Key interaction |
|---|---|---|---|---|
| 3ph line 0–80% | no | yes (primary) | Z1/inst | concurrent |
| 3ph line 80–100% | no | yes (primary) | Z2/0.3s | 87L faster |
| Remote bus | yes (remote) | no | Z2/0.3s | 87B primary; 21 back-up |
| Local bus | yes (primary) | no | Z1 overlap | 87B primary |
| ag bolted | no | yes | Z1/inst | concurrent |
| **ag HIF** | **no** | **yes (sole)** | **none** | **21 cannot reach** |
| Load | no | no | none | all restrain |

### 4.4 HIF gap analysis

Z_m = j0.025 + j1.5 × 1.5 = j2.275 pu — far outside Zone 3 (j0.090 pu). 87L sole detector via differential current (no impedance limitation).

---

## §5 Results

| Metric | Value |
|---|---|
| Selectivity | 12/12 (100%) |
| Zone boundaries | Exact to 0.005 pu resolution |
| HIF detection | 21 fails; 87L is sole detector (complementary roles) |
| Local bus Zone 1 overlap | Documented; can be blocked by 87B signal |
| Load encroachment | None (load well outside Mho circles) |
| Critical B_C for IBR infeed compensation | Future work |

---

## §6 Limitations

**L-1 — Local bus Zone 1 overlap:** Both 87B and 21 Zone 1 detect bus faults simultaneously. Acceptable in practice (87B faster, 21 Zone 1 is operationally correct); blocking signal from 87B can eliminate redundancy.

**L-2 — No IBR infeed compensation:** Under high IBR penetration, fault current infeed modifies apparent impedance; Zone 1 reach may need adaptation.

**L-3 — No coordination with OC relay:** The SAMBP OC function (sync_oc) not explicitly coordinated with 21 Zone 2/3 timing; future study needed.

**L-4 — No hardware validation:** Simulation only.

---

## §7 Reproduction Recipe

```bash
cd /root/phd_thesis/04_code/sambp/sambp_system
python run_mho_study.py --seed 2026 --scenarios all

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_2_87L_deep/TR18_mho_distance_21
pdflatex main_report18 && bibtex main_report18 && pdflatex main_report18 && pdflatex main_report18
```

---

## §8 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report18.tex` read (389 lines). Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report18.tex` is authoritative — this file is a read-only analytical summary.*
