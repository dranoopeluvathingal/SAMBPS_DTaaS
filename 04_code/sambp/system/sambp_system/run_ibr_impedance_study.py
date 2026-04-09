"""
run_ibr_impedance_study.py
============================
SAMBP TR-29/2026 — IBR Apparent Impedance Trajectory Analysis

Quantifies distance relay 21 performance under IBR fault current limitation
across the full k_ibr operating envelope.

Three studies:

  Study A — Apparent impedance Z_m(alpha, k_ibr)
    Shows Z_m = alpha * Z_line for IBR-fed faults (identical to SG).
    The Mho measurement is correct — the relay's problem is operational,
    not measurement.

  Study B — Relay voltage V_relay profile
    V_relay = k_ibr * alpha * |Z_line|  (IBR radial network)
    V_relay_SG = V_pre * alpha * Z_line / (Z_src + alpha * Z_line)  (SG)
    Shows ALL IBR-fed faults on this line produce V_relay < V_min_self = 0.10 pu.
    Memory / cross-polarisation is mandatory for all IBR fault scenarios.

  Study C — Minimum current threshold: I_relay vs I_min
    Distance relay blocked when I_relay = k_ibr < I_min = 0.10 pu.
    For k_ibr in [0.06, 0.10): relay completely blind to all line faults.
    For k_ibr in [0.10, 0.20]: relay operates (with memory) for alpha <= 0.80.

Results are compared to the combined 87L chain (TR-27):
    87L chain detects ALL k_ibr >= 0.06 line faults instantaneously.

Network (from TR-18 / radial_network.py):
  Z_src  = j0.10 pu
  Z_line = j0.05 pu
  V_pre  = 1.00 pu

Distance relay (TR-18):
  Zone 1 reach factor k1 = 0.80  (instant)
  Zone 2 reach factor k2 = 1.20  (t2 = 0.30 s)
  Zone 3 reach factor k3 = 1.80  (t3 = 0.60 s)
  I_min          = 0.10 pu   (IEC 60255-121 minimum operating current)
  V_min_self     = 0.10 pu   (minimum voltage for self-polarised Mho)
  V_min_memory   = 0.02 pu   (minimum voltage for memory / cross-pol Mho)
  Memory duration = 5 cycles = 100 ms at 50 Hz

Combined 87L chain thresholds (TR-27 / eq. 1):
  I1_thr  = 0.12 pu   (87L positive-sequence element)
  I2_thr  = 0.06 pu   (87LN negative-sequence — 0 for 3PH)
  I0_thr  = 0.04 pu   (87LN0 zero-sequence — 0 for 3PH)
  TDCS    fires for k_ibr >= 0.06 pu (all IBR scenarios — TR-26 guarantee)
"""

from __future__ import annotations
import math

# ---------------------------------------------------------------------------
# Network and relay parameters
# ---------------------------------------------------------------------------

Z_SRC   = 0.10    # |Z_src|  [pu]
Z_LINE  = 0.05    # |Z_line| [pu]
V_PRE   = 1.00    # pre-fault voltage [pu]

K1, K2, K3 = 0.80, 1.20, 1.80      # zone reach factors
T2, T3     = 0.30, 0.60             # zone time delays [s]

I_MIN        = 0.10   # minimum operating current [pu]
V_MIN_SELF   = 0.10   # minimum voltage, self-polarised [pu]
V_MIN_MEMORY = 0.02   # minimum voltage, memory / cross-polarised [pu]
T_MEMORY     = 0.100  # memory duration [s]  (5 cycles at 50 Hz)

# Zone reach absolute values
Z_REACH = {1: K1 * Z_LINE,   # 0.040 pu
           2: K2 * Z_LINE,   # 0.060 pu
           3: K3 * Z_LINE}   # 0.090 pu

# Combined 87L chain
I1_THR   = 0.12
TDCS_MIN = 0.06   # TDCS fires for k_ibr >= 0.06 pu (TR-26 analytical guarantee)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def z_m_ibr(alpha: float) -> float:
    """
    Apparent impedance seen by relay for IBR-fed internal fault.

    Z_m = V_relay / I_relay = (k_ibr * alpha * Z_line) / k_ibr = alpha * Z_line

    The k_ibr cancels exactly — Z_m is independent of k_ibr.
    The measurement is CORRECT, but V_relay and I_relay may be too small
    for reliable relay operation.
    """
    return alpha * Z_LINE


def z_m_sg(alpha: float) -> float:
    """
    Apparent impedance for SG-fed fault.

    I_sg = V_pre / (Z_src + alpha * Z_line)
    V_relay = V_pre * alpha * Z_line / (Z_src + alpha * Z_line)
    Z_m = V_relay / I_relay = alpha * Z_line  (same result)
    """
    return alpha * Z_LINE   # identical to IBR result


def v_relay_ibr(alpha: float, k_ibr: float) -> float:
    """
    Relay voltage for IBR-fed fault.
    V_relay = k_ibr * alpha * |Z_line|
    (purely reactive network, so |V_relay| = k_ibr * alpha * Z_LINE)
    """
    return k_ibr * alpha * Z_LINE


def v_relay_sg(alpha: float) -> float:
    """
    Relay voltage for SG-fed fault.
    V_relay = V_pre * alpha * Z_line / (Z_src + alpha * Z_line)
    """
    return V_PRE * alpha * Z_LINE / (Z_SRC + alpha * Z_LINE)


def zone_operates(z_m: float, zone: int) -> bool:
    """Returns True if the fault impedance is inside the given Mho zone."""
    return z_m <= Z_REACH[zone]


def distance_relay_status(alpha: float, k_ibr: float) -> dict:
    """
    Full relay status for an IBR-fed fault at location alpha.

    Returns:
      blocked_current: bool — relay blocked by I_min threshold
      blocked_voltage: bool — relay blocked by V_min_self (needs memory)
      memory_adequate: bool — memory/cross-pol voltage adequate
      zone: int or None — first zone that operates (1, 2, 3, or None)
      clearing_time_21: float or None — clearing time [s] for distance relay
    """
    z_m    = z_m_ibr(alpha)
    i_relay = k_ibr
    v_relay = v_relay_ibr(alpha, k_ibr)

    blocked_current = i_relay < I_MIN
    blocked_voltage = v_relay < V_MIN_SELF   # requires memory/cross-pol
    memory_adequate = v_relay >= V_MIN_MEMORY

    if blocked_current:
        return {
            "z_m": z_m, "v_relay": v_relay, "i_relay": i_relay,
            "blocked_current": True, "blocked_voltage": blocked_voltage,
            "memory_adequate": False,
            "zone": None, "clearing_time_21": None,
            "zone_note": "blocked I_min",
        }

    # Memory / cross-polarised Mho analysis:
    #
    # Memory stores V_pre = 1.0 pu.  It is valid for T_MEMORY = 100 ms.
    # During the memory window the Mho characteristic operates at nominal size.
    # After memory expires the relay must use the live V_relay for polarisation.
    #
    # For IBR-fed faults: V_relay = k_ibr * alpha * Z_LINE
    # Maximum V_relay = 0.20 * 1.0 * 0.05 = 0.010 pu  <<  V_MIN_SELF = 0.10 pu
    #
    # Consequence:
    #   Zone 1 (instant, ~20 ms):  within memory window  -> operates correctly
    #   Zone 2 (timed, 300 ms):    memory expires at 100 ms;
    #                              after 100 ms V_relay < V_MIN_SELF
    #                              -> self-pol fails; Zone 2 timer never completes
    #   Zone 3 (timed, 600 ms):    same problem; Zone 3 also fails

    if zone_operates(z_m, 1):
        # Zone 1 trips before memory expires — valid
        zone_op = 1
        t_clear = 0.020
        zone_note = "Zone 1 (memory OK)"
    elif zone_operates(z_m, 2):
        # Zone 2 timer = 300 ms > T_MEMORY = 100 ms
        # After memory expires, self-pol fails (V_relay < V_MIN_SELF)
        # Zone 2 de-asserts at ~100 ms — trip never reached
        zone_op = 2
        t_clear = None   # FAILS: memory expires before Zone 2 timer completes
        zone_note = "Zone 2 assert but memory expires; trip fails"
    elif zone_operates(z_m, 3):
        zone_op = 3
        t_clear = None   # same reason
        zone_note = "Zone 3 assert but memory expires; trip fails"
    else:
        zone_op = None
        t_clear = None
        zone_note = "outside all zones"

    return {
        "z_m": z_m, "v_relay": v_relay, "i_relay": i_relay,
        "blocked_current": False, "blocked_voltage": blocked_voltage,
        "memory_adequate": memory_adequate,
        "zone": zone_op, "clearing_time_21": t_clear,
        "zone_note": zone_note,
    }


def chain_87l_status(k_ibr: float) -> dict:
    """
    Combined 87L chain status for 3PH IBR internal fault.
    From TR-27: TDCS detects all k_ibr >= 0.06 pu.
    87L (|I1| >= 0.12) also fires for k_ibr >= 0.12 pu.
    """
    trip_87l   = k_ibr >= I1_THR
    trip_tdcs  = k_ibr >= TDCS_MIN    # TR-26 analytical guarantee
    trip_any   = trip_tdcs or trip_87l
    return {
        "trip_87l": trip_87l,
        "trip_tdcs": trip_tdcs,
        "trip_any": trip_any,
        "clearing_time_87l": 0.020 if trip_any else None,   # < 20 ms
        "primary": "87L+TDCS" if trip_87l else ("TDCS" if trip_tdcs else "none"),
    }


# ---------------------------------------------------------------------------
# Study A: Z_m measurement accuracy
# ---------------------------------------------------------------------------

def study_a() -> None:
    """
    Confirm Z_m = alpha * Z_line for IBR-fed faults.
    Show Z_m is identical to SG measurement.
    """
    alphas = [0.25, 0.50, 0.75, 0.79, 0.80, 0.82, 1.00]
    print("\n" + "=" * 70)
    print("Study A — Apparent impedance Z_m vs fault location")
    print("(Z_m is the SAME for IBR and SG — measurement is correct)")
    print("=" * 70)
    print(f"{'alpha':>6}  {'Z_m [pu]':>12}  {'Z_m_SG [pu]':>12}  "
          f"{'Zone1 (0.040)':>14}  {'Zone2 (0.060)':>14}")
    print("-" * 70)
    for a in alphas:
        zm  = z_m_ibr(a)
        zsg = z_m_sg(a)
        z1  = "inside" if zone_operates(zm, 1) else "outside"
        z2  = "inside" if zone_operates(zm, 2) else "outside"
        print(f"{a:>6.2f}  {zm:>12.4f}  {zsg:>12.4f}  {z1:>14s}  {z2:>14s}")


# ---------------------------------------------------------------------------
# Study B: V_relay profile
# ---------------------------------------------------------------------------

def study_b() -> None:
    """
    V_relay = k_ibr * alpha * |Z_line|  (IBR)
    V_relay = V_pre * alpha * Z_line / (Z_src + alpha * Z_line)  (SG)
    Shows IBR V_relay always << V_min_self; memory essential.
    """
    k_ibr_vals = [0.06, 0.10, 0.15, 0.20]
    alphas     = [0.10, 0.25, 0.50, 0.75, 1.00]

    print("\n" + "=" * 75)
    print("Study B — Relay voltage |V_relay| [pu] vs alpha and k_ibr")
    print(f"V_min_self = {V_MIN_SELF:.2f} pu (self-pol),  "
          f"V_min_memory = {V_MIN_MEMORY:.3f} pu (memory pol)")
    print("=" * 75)

    header = f"{'alpha':>6}  {'SG [pu]':>10}"
    for k in k_ibr_vals:
        header += f"  {'IBR k='+str(k):>12}"
    print(header)
    print("-" * 75)

    for a in alphas:
        v_sg = v_relay_sg(a)
        row  = f"{a:>6.2f}  {v_sg:>10.4f}"
        for k in k_ibr_vals:
            v_ibr = v_relay_ibr(a, k)
            flag  = " *" if v_ibr < V_MIN_MEMORY else ""
            row  += f"  {v_ibr:>10.4f}{flag:>2}"
        print(row)

    print("-" * 75)
    print(f"* = below V_min_memory ({V_MIN_MEMORY:.3f} pu) — polarisation uncertain")
    print(f"SG values: adequate (>{V_MIN_SELF:.2f}) for alpha > 0.10")
    print(f"IBR max V_relay = {0.20 * 1.0 * Z_LINE:.4f} pu "
          f"(k=0.20, alpha=1.0) — always below V_min_self")


# ---------------------------------------------------------------------------
# Study C: Operating status over (alpha, k_ibr) grid
# ---------------------------------------------------------------------------

def study_c() -> None:
    """
    Full relay status grid: (alpha, k_ibr) -> 21 status + 87L chain status.
    """
    k_ibr_vals = [0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.14, 0.16, 0.18, 0.20]
    alphas     = [0.50, 0.80, 0.85, 1.00]

    print("\n" + "=" * 100)
    print("Study C — Combined operating status: distance relay 21 vs combined 87L chain")
    print("=" * 100)
    header = (f"{'k_ibr':>6}  {'alpha':>5}  "
              f"{'I_relay':>8}  {'V_relay':>8}  "
              f"{'21 blocked':>10}  {'21 zone':>8}  {'21 t_clear':>10}  "
              f"{'87L primary':>12}  {'87L t_clear':>11}  {'Coverage':>12}")
    print(header)
    print("-" * 100)

    for k in k_ibr_vals:
        for a in alphas:
            d21  = distance_relay_status(a, k)
            d87l = chain_87l_status(k)

            blocked_str = "YES" if d21["blocked_current"] else "NO (memory)"
            zone_str    = str(d21["zone"]) if d21["zone"] else "none"
            t21_str     = f"{d21['clearing_time_21']:.3f}s" if d21["clearing_time_21"] else "—"
            t87_str     = f"{d87l['clearing_time_87l']:.3f}s" if d87l["clearing_time_87l"] else "—"

            # Coverage: 21 contributes only if it produces a clearance time
            if d21["blocked_current"] or d21["clearing_time_21"] is None:
                coverage = "87L only"
            elif d21["zone"] == 1:
                coverage = "Z1 + 87L"
            else:
                coverage = "87L only"

            print(f"{k:>6.2f}  {a:>5.2f}  "
                  f"{d21['i_relay']:>8.3f}  {d21['v_relay']:>8.4f}  "
                  f"{blocked_str:>10}  {zone_str:>8}  {t21_str:>10}  "
                  f"{d87l['primary']:>12}  {t87_str:>11}  {coverage:>12}")
        print()


# ---------------------------------------------------------------------------
# Coverage gap summary
# ---------------------------------------------------------------------------

def coverage_summary() -> None:
    """Summarise the coverage gap at specific k_ibr points."""
    print("\n" + "=" * 70)
    print("Coverage Gap Summary (3PH internal fault, alpha = 0.50)")
    print("=" * 70)
    print(f"{'k_ibr':>6}  {'21 operates':>12}  {'21 zone':>8}  "
          f"{'87L detects':>12}  {'Sole detector'}")
    print("-" * 70)
    for k in [0.06, 0.08, 0.10, 0.12, 0.15, 0.20]:
        d21  = distance_relay_status(0.50, k)
        d87l = chain_87l_status(k)
        trips21 = d21["clearing_time_21"] is not None
        op21 = "NO (I_min)" if d21["blocked_current"] else \
               (f"YES Z{d21['zone']} inst" if trips21 else
                f"Z{d21['zone']} (mem exp)")
        op87 = "YES (TDCS)" if d87l["trip_tdcs"] and not d87l["trip_87l"] else \
               "YES (87L+TDCS)" if d87l["trip_87l"] else "NO"
        sole = "87L chain" if (d21["blocked_current"] or not trips21) else "both"
        print(f"{k:>6.2f}  {op21:>15}  "
              f"{'—' if d21['blocked_current'] else str(d21['zone']):>5}  "
              f"{op87:>14}  {sole}")

    print("\n--- Critical thresholds ---")
    print(f"  Distance relay I_min threshold:    k_ibr_crit = {I_MIN:.2f} pu")
    print(f"  87L (|I1|) element threshold:      k_ibr      = {I1_THR:.2f} pu")
    print(f"  TDCS lowest operating k_ibr:       k_ibr      = {TDCS_MIN:.2f} pu")
    print(f"  V_relay(max IBR): k=0.20, a=1.0:   V          = "
          f"{v_relay_ibr(1.0, 0.20):.4f} pu  (< V_min_self = {V_MIN_SELF:.2f})")
    print(f"  V_relay(SG), a=0.5:                V          = "
          f"{v_relay_sg(0.5):.4f} pu  (> V_min_self = {V_MIN_SELF:.2f})")
    print(f"\n  CONCLUSION: For this line (|Z_line|={Z_LINE:.2f} pu),")
    print(f"    ALL IBR-fed faults require memory/cross-pol.")
    print(f"    IBR faults with k_ibr < {I_MIN:.2f} pu are INVISIBLE to distance relay.")
    print(f"    Combined 87L chain detects all k_ibr >= {TDCS_MIN:.2f} pu instantaneously.")


# ---------------------------------------------------------------------------
# Clearing time comparison
# ---------------------------------------------------------------------------

def clearing_time_comparison() -> None:
    """Fastest clearing time: 21 vs 87L chain, for all (alpha, k_ibr)."""
    scenarios = [
        (0.50, 0.08,  "3PH  alpha=0.50 k=0.08 (TDCS zone)"),
        (0.50, 0.10,  "3PH  alpha=0.50 k=0.10 (cusp)"),
        (0.50, 0.15,  "3PH  alpha=0.50 k=0.15 (87L+TDCS)"),
        (0.80, 0.15,  "3PH  alpha=0.80 k=0.15 (Zone 1 boundary)"),
        (0.82, 0.15,  "3PH  alpha=0.82 k=0.15 (just outside Zone 1)"),
        (1.00, 0.12,  "3PH  alpha=1.00 k=0.12 (end of line)"),
    ]

    print("\n" + "=" * 75)
    print("Clearing time comparison: distance relay 21 vs combined 87L chain")
    print("=" * 75)
    print(f"{'Scenario':<42}  {'t_21 [ms]':>10}  {'t_87L [ms]':>10}  {'Faster':>8}")
    print("-" * 75)
    for a, k, label in scenarios:
        d21  = distance_relay_status(a, k)
        d87l = chain_87l_status(k)
        t21  = d21["clearing_time_21"]
        t87  = d87l["clearing_time_87l"]
        t21s = f"{t21*1000:.0f}" if t21 else "—"
        t87s = f"{t87*1000:.0f}" if t87 else "—"
        if t21 is None:
            faster = "87L"
        elif t87 is None:
            faster = "21"
        else:
            faster = "87L" if t87 <= t21 else "21"
        print(f"{label:<42}  {t21s:>10}  {t87s:>10}  {faster:>8}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("SAMBP TR-29/2026 — IBR Apparent Impedance Study")
    print(f"Z_src={Z_SRC} pu  Z_line={Z_LINE} pu  "
          f"I_min={I_MIN} pu  V_min_self={V_MIN_SELF} pu")
    print("=" * 70)

    study_a()
    study_b()
    study_c()
    coverage_summary()
    clearing_time_comparison()
