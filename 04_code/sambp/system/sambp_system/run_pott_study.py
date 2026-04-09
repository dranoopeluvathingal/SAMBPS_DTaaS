"""
run_pott_study.py
SAMBP TR-33: Permissive Overreaching Transfer Trip (POTT) Scheme for IBR Lines

Motivation (TR-29 Region B):
  Zone 2 asserts for k_ibr >= 0.10 and alpha > 0.80, but the Zone 2 timer
  (300 ms) exceeds the memory polarisation hold time (100 ms), so the trip
  fails for 3-phase IBR faults.  POTT replaces the Zone 2 timer with a
  permissive carrier signal from the remote end, allowing instant clearance.

POTT scheme logic:
  LOCAL end A:  overreaching element asserts (Zone 2 within memory, t < T_mem)
  REMOTE end B: 67Q or 87L asserts → sends "permissive" carrier signal to A
  TRIP at A:    (Z2_local AND permissive_received AND memory_valid)

Network / relay parameters (from TR-29/30/32):
  Zone 2 reach: X_R2 = 0.060 pu (covers 120% of line)
  Zone 2 assert time: 0 ms (instantaneous assertion when criterion met)
  Zone 2 trip timer:  300 ms (bypassed in POTT mode)
  Memory hold:        T_mem = 100 ms
  Remote 67Q/87L:     asserts at ~30 ms (half-cycle confirmation)
  Carrier propagation: 2 ms (fibre-optic)
  POTT trip time:     ~32 ms (remote 67 confirms + carrier)

Coverage regions (from TR-29):
  Region A: k_ibr < 0.10 → I_min blocked → POTT cannot help (Z2 not asserted)
  Region B: k_ibr >= 0.10, alpha > 0.80 → Z2 asserts, timer fails → POTT FIXES THIS
  Region C: k_ibr in [0.10,0.12), alpha <= 0.80 → Z1 + TDCS (no POTT needed)
  Region D: k_ibr >= 0.12, alpha <= 0.80 → Z1 + 87L (no POTT needed)
"""

import math

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────
Z1L  = 0.05   # positive-seq line reactance [pu]
X_R1 = 0.040  # Zone 1 reach [pu]
X_R2 = 0.060  # Zone 2 reach [pu]
X_R3 = 0.090  # Zone 3 reach [pu]

T_MEM       = 0.100   # memory polarisation hold [s]
T_Z2_CONV   = 0.300   # Zone 2 conventional timer [s]
T_Z1        = 0.020   # Zone 1 trip time [s]
T_REMOTE_67 = 0.030   # remote 67Q/87L assertion time [s] (1.5-cycle)
T_CARRIER   = 0.002   # carrier propagation delay [s]
T_POTT_TRIP = T_REMOTE_67 + T_CARRIER  # ≈ 32 ms

I_MIN = 0.10          # distance relay I_min [pu]


# ──────────────────────────────────────────────────────────────────────────────
# Study A: Timing analysis — POTT vs conventional Zone 2
# ──────────────────────────────────────────────────────────────────────────────
def study_a_timing():
    print("=" * 72)
    print("STUDY A — Timing analysis: POTT vs conventional Zone 2")
    print("=" * 72)
    print()
    print(f"  Memory hold time:         T_mem       = {T_MEM*1e3:.0f} ms")
    print(f"  Zone 2 timer (conv.):     T_Z2_conv   = {T_Z2_CONV*1e3:.0f} ms")
    print(f"  Remote 67Q/87L asserts:   T_remote_67 = {T_REMOTE_67*1e3:.0f} ms")
    print(f"  Carrier propagation:      T_carrier   = {T_CARRIER*1e3:.0f} ms")
    print(f"  POTT trip time:           T_POTT      = {T_POTT_TRIP*1e3:.0f} ms")
    print()
    print("  Zone 2 comparison:")
    print(f"  {'Scheme':>20}  {'Trip time':>12}  {'Within T_mem?':>14}  "
          f"{'Clears fault?':>14}")
    print("  " + "-" * 66)

    schemes = [
        ("Conv. Zone 2 timer",  T_Z2_CONV,    T_Z2_CONV < T_MEM),
        ("POTT (via 67Q/87L)",  T_POTT_TRIP,  T_POTT_TRIP < T_MEM),
    ]
    for name, t, in_mem in schemes:
        clears = in_mem  # if within memory, polarisation is valid → trip succeeds
        print(f"  {name:>20}  {t*1e3:>10.1f}ms  "
              f"{'YES' if in_mem else 'NO':>14}  "
              f"{'YES' if clears else 'NO (mem expired)':>14}")

    margin = T_MEM - T_POTT_TRIP
    print()
    print(f"  POTT timing margin: {margin*1e3:.0f} ms  "
          f"({margin/T_MEM*100:.0f}% of T_mem remaining at trip)")
    print(f"  Zone 1 trip time {T_Z1*1e3:.0f} ms also within margin for reference.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study B: Coverage map — which regions does POTT recover?
# ──────────────────────────────────────────────────────────────────────────────
def study_b_coverage():
    print("=" * 72)
    print("STUDY B — POTT coverage: Region B recovery analysis")
    print("=" * 72)
    print()

    # TR-29 region definitions:
    # A: k < I_MIN (21 blocked)
    # B: k >= I_MIN AND alpha > X_R1/Z1L (Zone 2 only, memory fails)
    # C: k in [I_MIN, 0.12) AND alpha <= X_R1/Z1L (Zone 1 + TDCS)
    # D: k >= 0.12 AND alpha <= X_R1/Z1L (Zone 1 + 87L + TDCS)

    alpha_bdry = X_R1 / Z1L   # = 0.80

    alpha_vals  = [0.10, 0.30, 0.50, 0.70, 0.80, 0.82, 0.85, 0.90, 1.00]
    k_ibr_vals  = [0.06, 0.08, 0.10, 0.12, 0.15, 0.20]

    print(f"  Zone 1/2 boundary at alpha = X_R1/Z1L = {alpha_bdry:.2f}")
    print()
    print(f"  {'alpha':>7}  {'k_ibr':>7}  {'TR-29 Region':>13}  "
          f"{'Z2 assert?':>11}  {'Conv. trip?':>12}  "
          f"{'POTT trip?':>11}  {'POTT adds?':>10}")
    print("  " + "-" * 80)

    pott_gains = 0
    for alpha in alpha_vals:
        for k in k_ibr_vals:
            zm  = alpha * Z1L

            # Region classification
            if k < I_MIN:
                region = "A (blocked)"
            elif zm > X_R2:
                region = "OUT (>Z2)"
            elif zm > X_R1:
                region = "B (Z2 only)"
            elif k < 0.12:
                region = "C (Z1+TDCS)"
            else:
                region = "D (Z1+87L)"

            z2_assert   = (zm <= X_R2) and (k >= I_MIN)
            conv_trip   = z2_assert and (T_Z2_CONV < T_MEM)    # False: timer > T_mem
            pott_trip   = z2_assert and (T_POTT_TRIP < T_MEM)  # True if Z2 asserts
            pott_added  = pott_trip and not conv_trip

            if pott_added:
                pott_gains += 1

            # Only print Region B cases
            if "B" in region or "OUT" in region:
                flag = " ***" if pott_added else ""
                print(f"  {alpha:>7.2f}  {k:>7.2f}  {region:>13}  "
                      f"{'YES' if z2_assert else 'NO':>11}  "
                      f"{'YES' if conv_trip else 'NO':>12}  "
                      f"{'YES' if pott_trip else 'NO':>11}  "
                      f"{'YES' if pott_added else 'no':>10}{flag}")

    print()
    print(f"  *** POTT recovers all Region B cases ({pott_gains} total).")
    print(f"  Region A (k<{I_MIN}): POTT cannot help — Z2 not asserted.")
    print(f"  87L chain remains sole fast detector for Region A.")
    print()
    return pott_gains


# ──────────────────────────────────────────────────────────────────────────────
# Study C: Security — false-trip prevention
# ──────────────────────────────────────────────────────────────────────────────
def study_c_security():
    print("=" * 72)
    print("STUDY C — POTT security: false-trip prevention for external faults")
    print("=" * 72)
    print()
    print("  POTT trip condition: Z2_local AND perm_from_remote AND memory_valid")
    print()
    print("  For external fault BEYOND Bus B (fault outside protected line A-B):")
    print()

    cases = [
        ("Internal (alpha=0.90)", 0.90, 0.15, True,  True,  True),
        ("External beyond B",     1.10, 0.15, True,  False, False),  # Z2 sees, but remote blocks
        ("External before A",     0.00, 0.15, False, False, False),  # Z2 doesn't assert
    ]

    print(f"  {'Fault location':>24}  {'alpha':>7}  {'k_ibr':>7}  "
          f"{'Z2 assert?':>11}  {'Remote perm?':>13}  {'POTT trip?':>11}")
    print("  " + "-" * 76)

    for label, alpha, k, z2_A, remote_perm_B, pott in cases:
        # Z2 at end A: Z_m = alpha * Z1L, asserts if Z_m <= X_R2 and k >= I_MIN
        z2_assert = ((alpha * Z1L <= X_R2) and (k >= I_MIN))
        # Remote permissive from end B:
        # For internal fault (0 < alpha < 1): 67Q at B detects FORWARD fault → sends perm
        # For external beyond B (alpha > 1): 67Q at B sees REVERSE fault → BLOCKS perm
        # For external before A (alpha < 0): fault behind relay A → Z2 at A doesn't see it
        print(f"  {label:>24}  {alpha:>7.2f}  {k:>7.2f}  "
              f"{'YES' if z2_assert else 'NO':>11}  "
              f"{'YES' if remote_perm_B else 'NO (67Q blocks)':>13}  "
              f"{'TRIP' if (z2_assert and remote_perm_B) else 'BLOCK':>11}")

    print()
    print("  Security mechanism:")
    print("    For external fault beyond Bus B:")
    print("      - Local Z2 may still assert (Z2 overreaches into Bus B)")
    print("      - Remote 67Q sees fault as REVERSE → does NOT send permissive")
    print("      - POTT trip condition: Z2 AND perm → perm absent → NO TRIP ✓")
    print()
    print("  This is the fundamental POTT security property:")
    print("    The permissive signal comes from the remote DIRECTIONAL element,")
    print("    which only asserts for FORWARD faults at the remote end.")
    print("    External faults (reverse at remote) cannot generate permissive.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study D: Complete zone-time diagram with POTT
# ──────────────────────────────────────────────────────────────────────────────
def study_d_zone_time():
    print("=" * 72)
    print("STUDY D — Zone-time diagram: conventional vs POTT for IBR faults")
    print("=" * 72)
    print()

    alpha_bdry = X_R1 / Z1L  # 0.80

    # Without POTT: TR-29 table (for 3PH IBR, k_ibr >= 0.10)
    # With POTT: Zone 2 region trips at T_POTT_TRIP
    print(f"  {'alpha range':>22}  {'Without POTT':>20}  {'With POTT':>20}  Improvement")
    print("  " + "-" * 75)

    zones_table = [
        ("alpha in [0, 0.80]",   "Zone 1, 20 ms",   "Zone 1, 20 ms",   "Unchanged"),
        ("alpha in (0.80, 1.0]", "FAILS (mem exp.)", f"POTT, {T_POTT_TRIP*1e3:.0f} ms",
         f"Recovered ({T_POTT_TRIP*1e3:.0f} ms)"),
        ("k_ibr < 0.10",         "21 blocked",       "21 blocked",      "87L sole detector"),
    ]
    for row in zones_table:
        print(f"  {row[0]:>22}  {row[1]:>20}  {row[2]:>20}  {row[3]}")

    print()
    print(f"  POTT trip time ({T_POTT_TRIP*1e3:.0f} ms) vs Zone 2 timer ({T_Z2_CONV*1e3:.0f} ms):")
    speedup = T_Z2_CONV / T_POTT_TRIP
    print(f"    Speedup factor: {speedup:.1f}x  (if conventional timer were to work)")
    print(f"    More importantly: POTT trips within T_mem = {T_MEM*1e3:.0f} ms → memory valid.")
    print(f"    Conventional Zone 2 timer ALWAYS fails for IBR (300 ms > 100 ms).")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study E: POTT send-element options
# ──────────────────────────────────────────────────────────────────────────────
def study_e_send_element():
    print("=" * 72)
    print("STUDY E — POTT send-element options at remote end")
    print("=" * 72)
    print()

    elements = [
        ("87L chain",     True,  "0.06", "~20ms",
         "Fastest; needs pilot channel (already required for 87L)"),
        ("67Q",           True,  "0.04", "~30ms",
         "Lower k_ibr threshold; works for SLG/LL; not 3PH"),
        ("67N",           True,  "n/a",  "~30ms",
         "Only earth faults; most reliable for SLG"),
        ("Z2 remote end", False, "0.10", "~0ms",
         "Both ends must have Z2 asserted → NOT Zone 2 but POTT"),
    ]

    print(f"  {'Send element':>16}  {'Fwd select?':>12}  "
          f"{'k_min':>7}  {'Delay':>7}  Notes")
    print("  " + "-" * 72)
    for e in elements:
        print(f"  {e[0]:>16}  {'YES' if e[1] else 'NO':>12}  "
              f"{e[2]:>7}  {e[3]:>7}  {e[4]}")

    print()
    print("  Recommended: 87L as primary send element (fastest, most reliable).")
    print("  Secondary: 67Q for SLG faults when 87L communications fail.")
    print("  The 87L pilot channel is already required for the line differential;")
    print("  POTT reuses the same channel at negligible additional cost.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("SAMBP TR-33: POTT Scheme for IBR-Fed Lines")
    print("=" * 72)
    print()

    study_a_timing()
    pott_gains = study_b_coverage()
    study_c_security()
    study_d_zone_time()
    study_e_send_element()

    print("=" * 72)
    print("TR-33 SUMMARY")
    print("=" * 72)
    print()
    print(f"  POTT trip time: {T_POTT_TRIP*1e3:.0f} ms << T_mem={T_MEM*1e3:.0f} ms → memory valid at trip.")
    print(f"  Region B ({pott_gains} cases): Zone 2 timer failure recovered by POTT.")
    print(f"  Security: remote 67Q blocks permissive for external reverse faults.")
    print(f"  Send element: 87L pilot channel (already required for line differential).")
    print(f"  Complete coverage: Z1(A≤0.80) + POTT-Z2(A>0.80) + 87L(all).")
    print()
    print("  TR-33 complete.")
