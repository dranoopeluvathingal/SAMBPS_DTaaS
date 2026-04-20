# SUBREPORT_TR91 — Graph Neural Network Topology-Aware Protection

**TR ID:** TR-91  
**Full title:** Graph Neural Network Topology-Aware Protection: 3-Layer GraphSAGE for Relay Node Classification  
**Folder:** `03_technical_reports/phase_8_advanced_extensions/TR91_GNN_topology/`  
**Report file:** `main_report91.tex`  
**Generated:** 2026-04-20  
**Phase:** Phase 8 — Advanced Extensions  
**Thesis allocation:** Chapter 8 (ML-based protection)  
**Cross-linked TRs:** TR-62, TR-73 (Digital Twin node feature export), TR-90 (EMT validation)

---

## §1 Scope

**What TR-91 IS:**
- A 3-layer GraphSAGE relay node classifier with mean aggregation, trained jointly on IEEE 14-bus and IEEE 39-bus networks
- Zero-shot generalisation to IEEE 118-bus (never seen during training) — the primary novelty claim
- Pure NumPy implementation (no PyTorch / PyG) for portability and IED deployment
- Three-class output: `RESTRAIN` (0), `ALARM` (1), `TRIP` (2) — based on hop-distance from the fault bus
- Stage-1 classifier in the SAMBP framework, feeding a Stage-2 veto gate

**What TR-91 IS NOT:**
- Not an EMT-level waveform estimator — node features are derived from steady-state measurements (`|V|, θ, |I|, ΔI/Δt, Δf, P, Q, Z_app, I₂`)
- Not a replacement for current-differential (87L/87G) — TR-91 provides a topology-aware classification layer upstream of the protection function
- Not trained or validated with real-time transient waveforms — synthetic scenario generation only (EMT-level features: TR-67/TR-90)

**Namespace significance:** TR-91 is the final TR in the contiguous PhD namespace (TR-01..TR-91), bookending Phase 8 and the locked-namespace milestone.

---

## §2 State of the Art

Four references cited:

| Key | Reference | Limitation vs. TR-91 |
|---|---|---|
| hamilton2017 | Hamilton et al., NeurIPS 2017 — GraphSAGE | Original inductive GNN; not applied to protection |
| ieee14 | Christie 1993, IEEE 14-bus | Benchmark network only |
| ieee39 | Stagg & El-Abiad 1968, New England 39-bus | Benchmark network only |
| ieee118 | IEEE 118-bus system 1962 | Zero-shot test target |

**Novelty:** First application of mean-aggregation GraphSAGE to power system relay classification, with demonstrated zero-shot transfer from N=14/39 to N=118. Pure NumPy backprop through the mean aggregation layer is a secondary implementation contribution.

---

## §3 Method

### 3.1 GraphSAGE architecture (3-layer mean aggregation)

Each layer `ℓ` applies:
```
h_N(i)^(ℓ) = Mean{h_j^(ℓ-1) : j ∈ N(i)} = Â·H^(ℓ-1)_i,   Â_ij = 1/deg(i)
z_i^(ℓ)    = [h_i^(ℓ-1) ‖ h_N(i)^(ℓ)] · W^(ℓ) + b^(ℓ)
h_i^(ℓ)    = ReLU(z_i^(ℓ))           (ℓ < L=3; final layer: raw logits → softmax)
ŷ_i        = argmax_c softmax(z_i^(L))
```

**Why mean aggregation:** Permutation-invariant and size-invariant — the aggregated embedding depends only on the distribution of neighbour features, not their ordering or count. This is the property enabling zero-shot transfer across network sizes.

**3-hop receptive field:** Covers primary (1 hop), backup (2 hops), and remote (3 hops) relay zones. 99.8% of fault-to-relay paths in the IEEE 118-bus system are within 3 hops.

### 3.2 Node feature vector (d = 10)

| Index | Feature | Symbol | Unit |
|---|---|---|---|
| 0 | Voltage magnitude | `|V|` | pu |
| 1 | Voltage angle | `θ` | rad |
| 2 | Max branch current | `|I_max|` | pu |
| 3 | Rate of change of current | `ΔI/Δt` | pu/s |
| 4 | Frequency deviation | `Δf` | Hz |
| 5 | Active power injection | `P` | pu |
| 6 | Reactive power injection | `Q` | pu |
| 7 | Apparent impedance | `Z_app` | pu |
| 8 | Negative-sequence current | `I₂` | pu |
| 9 | Bias | **1** | — |

### 3.3 Label generation

For each synthetic fault scenario, fault bus `k` is selected uniformly:
```
y_i = TRIP     if d(i,k) ≤ 1
y_i = ALARM    if d(i,k) = 2
y_i = RESTRAIN if d(i,k) > 2
```
Reflects protection coordination: primary trips (1 hop), backup alarms (2 hops), remote restrains.

### 3.4 Training configuration

| Parameter | Value |
|---|---|
| Layers `L` | 3 |
| Hidden dim `d_h` | 32 |
| Input dim | 10 |
| Output classes | 3 |
| Learning rate `η` | 3×10⁻³ |
| Weight decay `λ` | 10⁻⁴ |
| Adam β₁, β₂ | 0.9, 0.999 |
| Batch size (scenarios) | 30 |
| Epochs | 100 |
| Training networks | IEEE 14 + IEEE 39 (mixed batch) |

**Loss:** Cross-entropy + L2 regularisation:
```
L = −(1/SN)·Σ_{s,i} log p_{s,i,y_{s,i}} + (λ/2)·Σ_ℓ ‖W^(ℓ)‖_F²
```

**Implementation:** Pure NumPy. Batched forward: `H^(S,N,d) → Â@H` via broadcast matmul. Manual backprop: `∂L/∂H = d_self + Â^T·d_neigh`. Mixed heterogeneous-size training by interleaved batches.

**Model weight footprint:** < 50 kB (three matrices: 20×32, 64×32, 64×3). IED-deployable.

---

## §4 Implementation

### Module

```
04_code/sambp/
├── gnn_protection.py            # GraphSAGE model, forward, backward, predict
└── tr91_gnn_runner.py           # Scenario generation, train/eval pipeline, zero-shot test

03_technical_reports/phase_8_advanced_extensions/TR91_GNN_topology/
├── main_report91.tex            # This document
├── tr91_results.json            # Full accuracy / F1 / confusion matrix results
├── loss_curve.csv               # Epoch vs. cross-entropy loss (100 epochs)
├── tab_accuracy.tex             # Auto-generated accuracy table (included in PDF)
└── tab_cm_ieee118.tex           # Auto-generated 118-bus confusion matrix
```

---

## §5 Validation

### 5.1 Classification accuracy and F1 (from `tr91_results.json`)

| Network | Accuracy | F1-REST. | F1-ALARM | F1-TRIP | Macro-F1 |
|---|---|---|---|---|---|
| IEEE 14-bus (in-dist.) | 94.3% | 0.963 | 0.942 | 0.885 | 0.930 |
| IEEE 39-bus (in-dist.) | 99.0% | 0.996 | 0.963 | 0.959 | 0.973 |
| **IEEE 118-bus (zero-shot†)** | **99.4%** | **0.998** | **0.947** | **0.918** | **0.954** |

† Never seen during training. Zero-shot accuracy exceeds in-distribution IEEE 14-bus — confirms inductive mean-aggregation property.

### 5.2 Zero-shot confusion matrix — IEEE 118-bus (50 scenarios, 5900 node-decisions)

| True ╲ Pred | RESTRAIN | ALARM | TRIP |
|---|---|---|---|
| RESTRAIN | 5462 | 16 | 1 |
| ALARM | 7 | 323 | 7 |
| TRIP | 0 | 6 | 78 |

**Dominant error mode:** ALARM → RESTRAIN (7 nodes) and ALARM → TRIP (7 nodes) — both conservative failure modes. **Zero TRIP nodes misclassified as RESTRAIN** — no dangerous missed operations.

### 5.3 Training convergence

Loss converged from ≈1.1 → 0.056 over 100 epochs. Smooth, no oscillation (Adam + mild L2). Training time: 201.4 s on CPU.

### 5.4 Inference latency

**33.4 μs/node** (CPU, no GPU). For IEEE 118-bus: total classification ≈ 3.9 ms — well within the 20 ms protection decision window.

---

## §6 Results

| Metric | Value | Source |
|---|---|---|
| Zero-shot accuracy (IEEE 118) | 99.4% | `tr91_results.json` |
| Zero-shot macro-F1 | 0.954 | `tr91_results.json` |
| False-safe errors (TRIP→RESTRAIN) | 0 | confusion matrix |
| Inference latency | 33.4 μs/node | `tr91_results.json` |
| Training time | 201.4 s | `tr91_results.json` |
| Final training loss | 0.056 | `loss_curve.csv` |
| Model size | < 50 kB | weight matrix dims |

**Comparison with threshold-based schemes:**

| Scheme | Topology-Adaptive | Zero-Shot | Inference |
|---|---|---|---|
| Fixed OC threshold | No | No | < 1 ms |
| Distance relay (mho) | No | No | < 1 ms |
| Adaptive OC (lookup table) | Partial | No | 1–5 ms |
| **GraphSAGE TR-91** | **Yes** | **Yes** | **33 μs/node** |

---

## §7 Limitations

**L-1 — Synthetic scenarios only:** Fault scenarios generated analytically; EMT-level time-domain features (from TR-62 Digital Twin / TR-90 EMT replay) would improve fidelity for IBR-connected buses where `ΔI/Δt` and `I₂` dynamics differ from synchronous-source assumptions.

**L-2 — Class imbalance:** RESTRAIN nodes dominate in large networks (>90% in IEEE 118). F1-TRIP (0.918) is lower than F1-RESTRAIN (0.998) as a result. Focal loss or TRIP/ALARM oversampling should be investigated.

**L-3 — Static adjacency matrix:** Implementation assumes a static graph. Online topology detection (breaker state estimation from GOOSE/SV) is needed for adaptive reconfiguration events — currently not handled.

**L-4 — Hardware latency not measured:** 33.4 μs/node measured in Python/NumPy on a desktop CPU. Real-time platform (RTDS, dSPACE) measurement with IEC 61850 GOOSE latency included is deferred.

**L-5 — Single-hop label heuristic:** Labels are assigned purely by hop distance from fault bus. In practice, protection zone boundaries depend on relay settings, CT ratios, and network impedances — a more physics-grounded label function would improve precision.

---

## §8 Reproduction Recipe

**Prerequisites:** Python ≥ 3.10, numpy only.

```bash
# Train and evaluate GraphSAGE (IEEE 14 + 39 train, IEEE 118 zero-shot)
cd /root/phd_thesis/04_code/sambp
python tr91_gnn_runner.py \
    --epochs 100 \
    --batch_size 30 \
    --hidden_dim 32 \
    --lr 3e-3 \
    --output_dir ../../03_technical_reports/phase_8_advanced_extensions/TR91_GNN_topology/

# Compile TR
cd /root/phd_thesis/03_technical_reports/phase_8_advanced_extensions/TR91_GNN_topology
pdflatex main_report91 && pdflatex main_report91
```

**Outputs:**
- `tr91_results.json` — per-network accuracy, F1, confusion matrix, latency, training time
- `loss_curve.csv` — epoch vs. loss
- `tab_accuracy.tex`, `tab_cm_ieee118.tex` — auto-generated LaTeX tables

---

## §9 Change-log

| Date | Change |
|---|---|
| 2026-04-20 | Sub-report created from full `main_report91.tex` read + `tr91_results.json` + auto-generated tables. Manuscript not modified. |

---

*Sub-report generated by SAMBP archivist pipeline. `main_report91.tex` and `tr91_results.json` are authoritative — this file is a read-only analytical summary.*
