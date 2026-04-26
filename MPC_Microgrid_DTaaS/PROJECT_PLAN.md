# MPC_Microgrid_DTaaS — 90-day plan

| Week | Focus | Key prompt(s) |
|---|---|---|
| 1   | Local environment + sanity check | A.1, A.2 |
| 2-3 | Class A studies (baseline) + new topologies | B.1, C.1, C.2 |
| 4-5 | Class C coordination studies (APPEEC paper figures) | B.2 |
| 6-7 | Cross-tool adapter (pick one) | D.1 (pandapower) or D.2 (OpenModelica) |
| 8   | Class D fault studies | B.3 |
| 9-10| Docker stack live + dashboard live | E.1, G.2 |
| 11-12| APPEEC paper draft + thesis Ch4 outline | F.1, F.2 |
| 13  | Cross-tool sweep + final figures | I.1 |

## Deliverable contracts

- Every prompt's output goes into a `git commit` with a one-line message
  matching the prompt id (e.g. `commit -m "B.1: energy vs linear PI baseline"`).
- The `pytest` count must monotonically increase as new tests land.
- Every figure includes the simulation parameters in its caption + filename.
