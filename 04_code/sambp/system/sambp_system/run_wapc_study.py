"""
run_wapc_study.py
SAMBP TR-50/2026: Wide-Area Protection Coordinator (WAPC)

Centralised multi-relay decision engine that aggregates IED reports
from across a substation group, performs synchrophasor-assisted fault
localisation, checks N-1 security before issuing trip commands, and
coordinates GOOSE messaging via IEC 61850.

Studies:
  A — Network topology: 10-bus test system, relay-zone adjacency graph
  B — Synchrophasor fault localisation: PMU voltage-dip triangulation
  C — N-1 security check: connectivity after tripping each relay
  D — WAPC vs distributed relay coordination latency
  E — Integration test: 50-scenario end-to-end coordination
"""

import math
import random
import numpy as np
from collections import defaultdict, deque

random.seed(42)
np.random.seed(42)

# ── 10-bus test network ───────────────────────────────────────────────────
# Buses: 0-9  |  Sources at buses 0 (grid), 5 (GFM IBR)
LINES = [
    (0, 1, 0.05, 'R01'),
    (1, 2, 0.04, 'R02'),
    (2, 3, 0.06, 'R03'),
    (3, 4, 0.05, 'R04'),
    (1, 5, 0.03, 'R05'),
    (5, 6, 0.04, 'R06'),
    (6, 7, 0.05, 'R07'),
    (7, 8, 0.06, 'R08'),
    (8, 9, 0.04, 'R09'),
    (4, 9, 0.07, 'R10'),   # tie line
    (3, 7, 0.05, 'R11'),   # inter-area
]
SOURCES = {0, 5}
N_BUS  = 10
N_LINE = len(LINES)
RELAY_IDS = [l[3] for l in LINES]

# ── Graph utilities ───────────────────────────────────────────────────────
def build_adj(excluded_relay=None):
    adj = defaultdict(list)
    for a, b, z, r in LINES:
        if r != excluded_relay:
            adj[a].append((b, z))
            adj[b].append((a, z))
    return adj

def is_connected(removed_relay=None):
    """BFS: all N_BUS buses reachable from bus 0 after removing one line."""
    adj = build_adj(excluded_relay=removed_relay)
    visited = set()
    q = deque([0])
    while q:
        n = q.popleft()
        if n in visited: continue
        visited.add(n)
        for nb, _ in adj[n]:
            if nb not in visited:
                q.append(nb)
    return len(visited) == N_BUS

def dijkstra(src, adj):
    """Shortest electrical-distance (impedance) from src to all buses."""
    dist = {i: 1e9 for i in range(N_BUS)}
    dist[src] = 0
    visited = set()
    while True:
        # Pick unvisited node with smallest dist
        u = min((d, n) for n, d in dist.items() if n not in visited)[1]
        visited.add(u)
        if len(visited) == N_BUS: break
        for nb, z in adj[u]:
            if nb not in visited and dist[u] + z < dist[nb]:
                dist[nb] = dist[u] + z
    return dist

# ── PMU voltage model ─────────────────────────────────────────────────────
def pmu_voltages(fault_line_idx, alpha, sigma_v=0.01):
    """
    Simulate PMU voltage magnitudes during fault.
    Fault at position alpha from bus_a on LINES[fault_line_idx].
    Voltage dip at each bus is inversely proportional to electrical
    distance from bus to fault point.
    """
    fa, fb, zl, _ = LINES[fault_line_idx]
    z_fault_to_a = alpha * zl           # impedance: fault → bus_a
    z_fault_to_b = (1 - alpha) * zl     # impedance: fault → bus_b

    # Build a temporary graph with a "fault bus" F inserted on the line
    # For simplicity: use Dijkstra from bus_a and bus_b, combine
    adj = build_adj()
    dist_a = dijkstra(fa, adj)
    dist_b = dijkstra(fb, adj)

    V = np.ones(N_BUS)
    DIP_SCALE = 0.40   # max voltage dip magnitude (pu)
    for bus in range(N_BUS):
        # Electrical distance from bus to fault via the two line endpoints
        d_via_a = dist_a[bus] + z_fault_to_a
        d_via_b = dist_b[bus] + z_fault_to_b
        d_fault = min(d_via_a, d_via_b)
        dip = DIP_SCALE / (1 + 20 * d_fault)
        V[bus] = max(0.10, 1.0 - dip)

    V += np.random.normal(0, sigma_v, N_BUS)
    return np.clip(V, 0.05, 1.10)

# ── Fault localisation ────────────────────────────────────────────────────
def localise_fault(V):
    """
    Identify faulted line using PMU voltages.
    Criterion: largest sum of voltage dips at the two endpoint buses
    (the faulted line endpoints experience the greatest combined dip).
    Returns (relay_id, alpha_estimate).
    """
    best_score = -1
    best_idx   = 0
    for idx, (a, b, zl, rid) in enumerate(LINES):
        dv_a = max(0, 1.0 - V[a])
        dv_b = max(0, 1.0 - V[b])
        score = dv_a + dv_b   # maximise combined endpoint dip
        if score > best_score:
            best_score = score
            best_idx   = idx
    fa, fb, zl, rid = LINES[best_idx]
    dv_a = max(0, 1.0 - V[fa])
    dv_b = max(0, 1.0 - V[fb])
    alpha_est = dv_a / (dv_a + dv_b) if (dv_a + dv_b) > 1e-6 else 0.5
    return rid, alpha_est

print("=" * 64)
print("SAMBP TR-50: Wide-Area Protection Coordinator (WAPC)")
print("=" * 64)

# ════════════════════════════════════════════════════════════════════════
# Study A — Network topology and relay-zone adjacency
# ════════════════════════════════════════════════════════════════════════
print("\n── Study A: Network Topology ──")

print(f"\n  Buses:   {N_BUS}")
print(f"  Lines:   {N_LINE}")
print(f"  Relays:  {len(RELAY_IDS)}")
print(f"  Sources: buses {sorted(SOURCES)}")

# Relay-zone adjacency (relays sharing a bus)
zone_adj = defaultdict(set)
bus_relays = defaultdict(list)
for a, b, z, rid in LINES:
    bus_relays[a].append(rid)
    bus_relays[b].append(rid)
for bus, relays in bus_relays.items():
    for i, r1 in enumerate(relays):
        for r2 in relays[i+1:]:
            zone_adj[r1].add(r2)
            zone_adj[r2].add(r1)

n_adj_pairs = sum(len(v) for v in zone_adj.values()) // 2
max_degree  = max(len(v) for v in zone_adj.values())
mean_degree = sum(len(v) for v in zone_adj.values()) / len(RELAY_IDS)

print(f"\n  Relay adjacency pairs (shared bus): {n_adj_pairs}")
print(f"  Max relay degree:  {max_degree}")
print(f"  Mean relay degree: {mean_degree:.2f}")

# ════════════════════════════════════════════════════════════════════════
# Study B — Synchrophasor fault localisation
# ════════════════════════════════════════════════════════════════════════
print("\n── Study B: Synchrophasor Fault Localisation ──")

N_LOC = 400
correct_line  = 0
alpha_errors  = []

for _ in range(N_LOC):
    fidx       = random.randint(0, N_LINE - 1)
    alpha_true = random.uniform(0.10, 0.90)
    V          = pmu_voltages(fidx, alpha_true)
    pred_rid, alpha_est = localise_fault(V)

    if pred_rid == LINES[fidx][3]:
        correct_line += 1
        alpha_errors.append(abs(alpha_est - alpha_true))

loc_acc       = correct_line / N_LOC * 100
mean_loc_err  = np.mean(alpha_errors) * 100 if alpha_errors else 0   # % of line

# Localisation by noise level
print(f"\n  {'Noise sigma_V':>14s} {'Line acc%':>10s} {'Alpha err%':>12s}")
print(f"  {'-'*14} {'-'*10} {'-'*12}")
for sigma in [0.005, 0.010, 0.020, 0.040]:
    c, errs = 0, []
    for _ in range(200):
        fidx = random.randint(0, N_LINE-1)
        at   = random.uniform(0.1, 0.9)
        V    = pmu_voltages(fidx, at, sigma_v=sigma)
        rid_p, ae = localise_fault(V)
        if rid_p == LINES[fidx][3]:
            c += 1
            errs.append(abs(ae - at))
    print(f"  {sigma:>14.3f} {c/200*100:>10.1f} {np.mean(errs)*100 if errs else 0:>12.2f}")

print(f"\n  Baseline (sigma=0.01): {loc_acc:.1f}% correct line, "
      f"{mean_loc_err:.2f}% mean location error")

# ════════════════════════════════════════════════════════════════════════
# Study C — N-1 security check
# ════════════════════════════════════════════════════════════════════════
print("\n── Study C: N-1 Security Check ──")

print(f"\n  {'Relay':>6s}  {'N-1 OK?':>8s}  {'Islanding risk':>16s}  {'Action':>20s}")
print(f"  {'-'*6}  {'-'*8}  {'-'*16}  {'-'*20}")

secure_trips = 0
insecure_relays = []

for rid in RELAY_IDS:
    ok     = is_connected(removed_relay=rid)
    action = "Direct trip" if ok else "Escalate to operator"
    if ok:
        secure_trips += 1
    else:
        insecure_relays.append(rid)
    print(f"  {rid:>6s}  {'YES':>8s}  {'LOW':>16s}  {action:>20s}"
          if ok else
          f"  {rid:>6s}  {'NO':>8s}  {'HIGH – island':>16s}  {action:>20s}")

print(f"\n  Secure trips (direct WAPC trip):  {secure_trips}/{len(RELAY_IDS)}")
print(f"  Escalated (operator confirm req): {len(insecure_relays)}/{len(RELAY_IDS)}")
if insecure_relays:
    print(f"  Insecure relays: {', '.join(insecure_relays)}")

# ════════════════════════════════════════════════════════════════════════
# Study D — WAPC vs distributed relay latency
# ════════════════════════════════════════════════════════════════════════
print("\n── Study D: WAPC vs Distributed Relay Latency ──")

latency_dist = [
    ('IED local decision',    2.0),
    ('GOOSE trip command',    2.0),
]
latency_wapc = [
    ('IED → WAPC report (GOOSE)',  2.0),
    ('PMU → WAPC data (250 Hz)',   4.0),
    ('WAPC fault localisation',    0.5),
    ('WAPC N-1 BFS check',         0.2),
    ('WAPC ML advisory (PINN)',    0.3),
    ('WAPC → IED trip (GOOSE)',    2.0),
]
total_dist = sum(v for _,v in latency_dist)
total_wapc = sum(v for _,v in latency_wapc)

print(f"\n  Distributed path:  {total_dist:.1f} ms")
for n, v in latency_dist:
    print(f"    {n:>34s}: {v:.1f} ms")

print(f"\n  WAPC centralised path: {total_wapc:.1f} ms")
for n, v in latency_wapc:
    print(f"    {n:>34s}: {v:.1f} ms")

print(f"\n  Overhead vs distributed: +{total_wapc - total_dist:.1f} ms")
print(f"  Both within 50 ms trip budget: YES  ({total_wapc/50*100:.0f}% used)")

# ════════════════════════════════════════════════════════════════════════
# Study E — Integration test (50 scenarios)
# ════════════════════════════════════════════════════════════════════════
print("\n── Study E: Integration Test (50 Scenarios) ──")

N_SCEN = 50
results = []

for _ in range(N_SCEN):
    fidx  = random.randint(0, N_LINE - 1)
    alpha = random.uniform(0.05, 0.95)
    true_rid = LINES[fidx][3]

    # Distributed: correct with 95%, miscoords 5% to adjacent relay
    adj_relays = list(zone_adj.get(true_rid, {true_rid}))
    dist_rid = true_rid if random.random() > 0.05 else random.choice(adj_relays)

    # WAPC: PMU localisation
    V = pmu_voltages(fidx, alpha)
    wapc_rid, alpha_est = localise_fault(V)

    # N-1 check
    n1_ok = is_connected(removed_relay=wapc_rid)
    wapc_correct = (wapc_rid == true_rid)

    results.append({
        'true': true_rid,
        'dist': dist_rid, 'dist_ok': dist_rid == true_rid,
        'wapc': wapc_rid, 'wapc_ok': wapc_correct,
        'n1_ok': n1_ok,
    })

dist_acc   = sum(r['dist_ok']  for r in results) / N_SCEN * 100
wapc_acc   = sum(r['wapc_ok']  for r in results) / N_SCEN * 100
n1_blocked = sum(1 for r in results if not r['n1_ok'])
both_wrong = sum(1 for r in results if not r['dist_ok'] and not r['wapc_ok'])
either_right = sum(1 for r in results if r['dist_ok'] or r['wapc_ok'])

print(f"\n  {'Metric':>40s} {'Value':>10s}")
print(f"  {'-'*40} {'-'*10}")
print(f"  {'Distributed relay accuracy':>40s} {dist_acc:>9.1f}%")
print(f"  {'WAPC accuracy (fault localisation)':>40s} {wapc_acc:>9.1f}%")
print(f"  {'N-1 security blocks issued':>40s} {n1_blocked:>9d}")
print(f"  {'Cases correct by at least one system':>40s} {either_right:>9d}")
print(f"  {'Cases wrong by both systems':>40s} {both_wrong:>9d}")

# WAPC adds value in cases where distributed miscoordinates
wapc_saves = sum(1 for r in results if not r['dist_ok'] and r['wapc_ok'])
dist_saves = sum(1 for r in results if r['dist_ok'] and not r['wapc_ok'])
print(f"\n  WAPC corrects distributed miscoordination: {wapc_saves} cases")
print(f"  Distributed correct where WAPC wrong:      {dist_saves} cases")

print("\n" + "=" * 64)
print("TR-50 WAPC study complete.")
print(f"  Fault localisation: {loc_acc:.1f}% correct line "
      f"({mean_loc_err:.2f}% alpha error)")
print(f"  N-1 security: {len(insecure_relays)}/{len(RELAY_IDS)} relays require escalation")
print(f"  WAPC latency: {total_wapc:.1f} ms ({total_wapc/50*100:.0f}% of 50 ms budget)")
print(f"  Integration: WAPC {wapc_acc:.1f}% | Distributed {dist_acc:.1f}%")
print("=" * 64)
