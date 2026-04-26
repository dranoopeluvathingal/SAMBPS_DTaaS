# SAMBPS Flagship · Glossary

Specialised terms as used in this programme. Keep consistent across all chapters, papers, and TRs.

| Term | Definition |
|---|---|
| **Adaptive line differential (87L)** | Line differential protection element (ANSI 87L) whose restraint and slope coefficients adapt online to changing IBR fault contributions. |
| **Commutation failure** | LCC HVDC condition where the next valve fails to take over current; relevant fault scenario in `05_data/hvdc/`. |
| **DTaaS (Digital Twin as a Service)** | Cloud-delivered digital-twin platform (SAMS Digital Twin) hosting model-based protection studies for utility customers. |
| **EKF** | Extended Kalman Filter — one of the GFM/GFL estimator approaches in the APPEEC 2026 P2 paper. |
| **Fidelity-validated trajectory prediction** | DT-side capability to extrapolate system state forward in time with bounded error, used for protection decision support (APPEEC 2026 P3). |
| **GFM (grid-forming inverter)** | IBR with voltage-source behavior, can operate islanded; presents distinct fault characteristics from GFL. |
| **GFL (grid-following inverter)** | IBR with current-source behavior, requires grid voltage reference; dominant present-deployment mode. |
| **HIL (hardware-in-the-loop)** | Validation method using a real relay (e.g. SEL-411L per TR-98) connected to a real-time simulator. |
| **HVDC** | High-Voltage Direct Current. Programme covers LCC, VSC, MMC topologies (TR-H01+). |
| **IBR (inverter-based resource)** | Generic term covering all power-electronic interfaced sources (PV, wind, BESS, HVDC). |
| **k_ibr** | Per-IBR fault-current contribution coefficient driving adaptive 87L restraint logic; estimation is core to APPEEC 2026 P2. |
| **LCC / VSC / MMC** | Three HVDC converter topologies. Line-commutated, voltage-source, modular multilevel — each has distinct protection challenges. |
| **PINN** | Physics-Informed Neural Network. One of the GFM/GFL estimator approaches. |
| **Protection coordination under IBR** | Reconciliation of relay settings (pickup, time-grading, directionality) under IBR-dominated fault current that is voltage-controlled rather than fault-current driven. |
| **RLS** | Recursive Least Squares — one of the GFM/GFL estimator approaches. |
| **SAMBPS** | Self-Adaptive Model-Based Protection — the methodology. |
| **SAMS Architect** | AI research-design engine product line under SAMS. |
| **SAMS Digital Twin** | Cloud DTaaS platform product line under SAMS. |
| **SEL-411L** | Schweitzer Engineering Laboratories line-current differential relay used for HIL validation in TR-98. |
| **TR-90 federated learning** | Federated-learning approach for cross-substation relay coordination; APPEEC 2026 P4 paper backing. |
| **WAPC (Wide-Area Protection and Control)** | TR-50 master topic; supervisory layer above local relays using wide-area measurements. |
