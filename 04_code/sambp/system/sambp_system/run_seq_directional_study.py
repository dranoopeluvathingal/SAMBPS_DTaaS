"""
run_seq_directional_study.py
SAMBP TR-32: Negative- and Zero-Sequence Directional Elements (67Q, 67N)

Studies:
  A  67N forward/reverse discrimination — zero-seq directional
  B  67Q forward/reverse discrimination — negative-seq directional
  C  Sensitivity: minimum k_ibr for 67Q vs distance relay I_min
  D  Discrimination margin vs X/R ratio
  E  Element comparison: 67N/67Q vs 87L vs 21G (TR-31/32)

Reverse-fault model (physically correct):
  For a fault BEHIND the relay (source side):
  - The sequence currents flow in the OPPOSITE direction through the relay CT.
    -> I_seq_reverse = -I_seq_forward  (direction at CT reverses)
  - The relay bus sequence VOLTAGES are determined by the network and do NOT
    simply change sign; for a distant external fault they are approximately
    equal in magnitude to the forward case but retain the same polarity.
    -> V_seq_reverse ≈ +V_seq_forward  (bus voltage retains polarity)
  Combined: Re[-V_rev * conj(I_rev)] = Re[-V_fwd * conj(-I_fwd)]
                                      = Re[V_fwd * conj(I_fwd)]
                                      = -Re[-V_fwd * conj(I_fwd)] < 0  (reverse)
  This gives the correct sign flip for the directional criterion.

Network (X/R = 20, realistic HV):
  Z1L = 0.0025+j0.050 pu   Z0L = 0.0075+j0.150 pu
  Z1S = 0.0050+j0.100 pu   Z0S = 0.0150+j0.300 pu
"""

import cmath, math

Z1L = complex(0.0025, 0.050)
Z0L = complex(0.0075, 0.150)
Z1S = complex(0.0050, 0.100)
Z0S = complex(0.0150, 0.300)
V_PRE   = 1.00
I_MIN_67 = 0.04
I_MIN_21 = 0.10
THR_DIRN = 0.0       # strict zero-crossing


def slg_fwd(alpha, k_ibr):
    """Forward SLG: I1/I2 limited to k_ibr; I0 from network (independent)."""
    Z1T = Z1S + alpha * Z1L
    Z0T = Z0S + alpha * Z0L
    I1_sg = V_PRE / (2 * Z1T + Z0T)
    I0    = I1_sg
    mag   = min(abs(I1_sg), k_ibr)
    ang   = I1_sg / abs(I1_sg) if abs(I1_sg) > 1e-12 else complex(-1j)
    I1    = mag * ang
    I2    = I1
    V1    = V_PRE - I1 * Z1S
    V2    = -I2 * Z1S
    V0    = -I0 * Z0S
    return dict(I1=I1, I2=I2, I0=I0, V1=V1, V2=V2, V0=V0)


def slg_rev(alpha, k_ibr):
    """
    Reverse SLG: sequence currents reverse at relay CT; voltages unchanged.
    Physical basis: external fault → I_seq flows in opposite direction through
    relay current transformers; bus voltage polarity unchanged.
    """
    fwd = slg_fwd(alpha, k_ibr)
    return dict(I1=fwd["I1"], I2=-fwd["I2"], I0=-fwd["I0"],
                V1=fwd["V1"],  V2=fwd["V2"],  V0=fwd["V0"])


def dirn(V, I):
    """Active-power directional criterion. Returns (value, is_forward)."""
    val = (-V * I.conjugate()).real
    return val, val > THR_DIRN


def adeg(z):
    return math.degrees(cmath.phase(z))


# ──────────────────────────────────────────────────────────────────────────────
# Study A: 67N
# ──────────────────────────────────────────────────────────────────────────────
def study_a():
    print("=" * 74)
    print("STUDY A — 67N Zero-sequence directional (X/R = 20)")
    print("=" * 74)
    print(f"  Criterion: Re[ -V0 * conj(I0) ] > {THR_DIRN}  |  I0_min = {I_MIN_67} pu")
    print()
    hdr = (f"  {'alpha':>6}  {'k_ibr':>6}  {'|I0|':>7}  {'Arg I0':>8}  "
           f"{'Arg V0':>8}  {'Crit [pu^2]':>13}  {'Dir':>8}  Type")
    print(hdr)
    print("  " + "-" * 74)

    cases = [(0.50,0.10,"FWD"),(0.50,0.10,"REV"),
             (0.20,0.06,"FWD"),(0.20,0.06,"REV"),
             (0.80,0.20,"FWD"),(0.80,0.20,"REV")]
    for alpha,k,ftype in cases:
        seq  = slg_fwd(alpha,k) if ftype=="FWD" else slg_rev(alpha,k)
        I0,V0 = seq["I0"], seq["V0"]
        val, fwd = dirn(V0, I0)
        blk = abs(I0) < I_MIN_67
        print(f"  {alpha:>6.2f}  {k:>6.2f}  {abs(I0):>7.4f}  "
              f"{adeg(I0):>8.2f}°  {adeg(V0):>8.2f}°  "
              f"{val:>+13.6f}  {'FWD' if fwd else 'REV':>8}  "
              f"{ftype}{'(blk)' if blk else ''}")

    print()
    # Quantify margin at alpha=0.50, k=0.10
    fwd_seq = slg_fwd(0.50,0.10);  rev_seq = slg_rev(0.50,0.10)
    cf,_  = dirn(fwd_seq["V0"],fwd_seq["I0"])
    cr,_  = dirn(rev_seq["V0"],rev_seq["I0"])
    print(f"  Forward crit: {cf:>+.5f} pu^2")
    print(f"  Reverse crit: {cr:>+.5f} pu^2")
    print(f"  Margin: {cf-cr:>+.5f} pu^2  (= 2 × Re[-V0·I0*]_forward)")
    print()
    print("  67N: I0 is NETWORK-SOURCED → independent of k_ibr.")
    print("  For purely IBR-fed line: I0 only flows for forward faults")
    print("  (delta transformer blocks zero-seq from IBR end).")
    print("  -> 67N has inherent forward selectivity on IBR network.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study B: 67Q
# ──────────────────────────────────────────────────────────────────────────────
def study_b():
    print("=" * 74)
    print("STUDY B — 67Q Negative-sequence directional (X/R = 20)")
    print("=" * 74)
    print(f"  Criterion: Re[ -V2 * conj(I2) ] > {THR_DIRN}  |  I2_min = {I_MIN_67} pu")
    print()
    hdr = (f"  {'alpha':>6}  {'k_ibr':>6}  {'|I2|':>7}  {'Arg I2':>8}  "
           f"{'Arg V2':>8}  {'Crit [pu^2]':>13}  {'Dir':>8}  Type")
    print(hdr)
    print("  " + "-" * 74)

    cases = [(0.50,0.10,"FWD"),(0.50,0.10,"REV"),
             (0.20,0.06,"FWD"),(0.20,0.06,"REV"),
             (0.80,0.20,"FWD"),(0.80,0.20,"REV")]
    for alpha,k,ftype in cases:
        seq  = slg_fwd(alpha,k) if ftype=="FWD" else slg_rev(alpha,k)
        I2,V2 = seq["I2"], seq["V2"]
        val, fwd = dirn(V2, I2)
        blk = abs(I2) < I_MIN_67
        print(f"  {alpha:>6.2f}  {k:>6.2f}  {abs(I2):>7.4f}  "
              f"{adeg(I2):>8.2f}°  {adeg(V2):>8.2f}°  "
              f"{val:>+13.6f}  {'FWD' if fwd else 'REV':>8}  "
              f"{ftype}{'(blk)' if blk else ''}")

    print()
    fwd_seq = slg_fwd(0.50,0.10);  rev_seq = slg_rev(0.50,0.10)
    cf,_ = dirn(fwd_seq["V2"],fwd_seq["I2"])
    cr,_ = dirn(rev_seq["V2"],rev_seq["I2"])
    print(f"  Forward crit: {cf:>+.6f} pu^2")
    print(f"  Reverse crit: {cr:>+.6f} pu^2")
    print(f"  Margin: {cf-cr:>+.6f} pu^2")
    print()
    print("  67Q: I2 = k_ibr (IBR-injected); operates for k_ibr >= 0.04 pu.")
    print("  Margin proportional to |I2|^2 * Re[Z1S] = k_ibr^2 * R1S.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study C: Sensitivity
# ──────────────────────────────────────────────────────────────────────────────
def study_c():
    print("=" * 74)
    print("STUDY C — Sensitivity: minimum k_ibr for 67Q vs distance relay 21")
    print("=" * 74)
    print(f"  I_min_67 = {I_MIN_67} pu  |  I_min_21 = {I_MIN_21} pu")
    print()
    print(f"  {'k_ibr':>8}  {'|I0|':>9}  {'|I2|':>9}  "
          f"{'67N':>5}  {'67Q':>5}  {'21G':>5}  Note")
    print("  " + "-" * 60)

    alpha = 0.50
    for k in [0.02, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15, 0.20]:
        seq = slg_fwd(alpha, k)
        I0, I2 = abs(seq["I0"]), abs(seq["I2"])
        ok_67n = I0 >= I_MIN_67
        ok_67q = I2 >= I_MIN_67
        ok_21  = I2 >= I_MIN_21
        note = " <-- 67Q covers, 21 blocked" if (ok_67q and not ok_21) else ""
        print(f"  {k:>8.2f}  {I0:>9.4f}  {I2:>9.4f}  "
              f"{'yes' if ok_67n else 'NO':>5}  "
              f"{'yes' if ok_67q else 'NO':>5}  "
              f"{'yes' if ok_21 else 'NO':>5}{note}")

    print()
    print(f"  67Q extends earth-fault coverage from k_ibr={I_MIN_21} down to"
          f" k_ibr={I_MIN_67} pu.")
    ext = (I_MIN_21 - I_MIN_67) / I_MIN_21 * 100
    print(f"  -> {ext:.0f}% lower minimum k_ibr than distance relay.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study D: Margin vs X/R ratio
# ──────────────────────────────────────────────────────────────────────────────
def study_d():
    print("=" * 74)
    print("STUDY D — Discrimination margin vs line X/R ratio")
    print("=" * 74)
    print("  Margin = Re[-V_fwd*I_fwd*] - Re[-V_rev*I_rev*]")
    print("         = 2 * Re[Z_source] * |I_seq|^2  (from analytical formula)")
    print()
    print(f"  {'X/R':>7}  {'R1S':>8}  {'R0S':>8}  "
          f"{'Margin 67N':>12}  {'Margin 67Q':>12}  Note")
    print("  " + "-" * 58)

    alpha, k = 0.50, 0.10
    for xr in [5, 10, 20, 50, 100, 500]:
        r1 = 0.100 / xr;  r0 = 0.300 / xr
        z1s = complex(r1, 0.100);  z0s = complex(r0, 0.300)
        z1l = complex(0.050/xr, 0.050);  z0l = complex(0.150/xr, 0.150)

        Z1T = z1s + alpha * z1l
        Z0T = z0s + alpha * z0l
        I1_sg = V_PRE / (2*Z1T + Z0T)
        I0    = I1_sg
        mag   = min(abs(I1_sg), k)
        ang   = I1_sg/abs(I1_sg) if abs(I1_sg)>1e-12 else -1j
        I2    = mag * ang
        V0    = -I0 * z0s
        V2    = -I2 * z1s

        # forward
        cf_n = (-V0 * I0.conjugate()).real
        cf_q = (-V2 * I2.conjugate()).real
        # reverse (V unchanged, I negated)
        cr_n = (-V0 * (-I0).conjugate()).real   # = +Re[V0*I0*] = -cf_n
        cr_q = (-V2 * (-I2).conjugate()).real

        margin_n = cf_n - cr_n   # = 2*cf_n
        margin_q = cf_q - cr_q

        note = "  <-- SAMBP" if xr == 20 else ""
        print(f"  {xr:>7}  {r1:>8.4f}  {r0:>8.4f}  "
              f"{margin_n:>12.6f}  {margin_q:>12.6f}{note}")

    print()
    print("  Margin increases as X/R decreases (more resistance = more active power).")
    print("  At X/R=20 (SAMBP): robust positive margin for both 67N and 67Q.")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Study E: Element comparison
# ──────────────────────────────────────────────────────────────────────────────
def study_e():
    print("=" * 74)
    print("STUDY E — Element comparison: 67N/67Q vs 87L vs 21G")
    print("=" * 74)
    print()
    rows = [
        ("87L",   "Full",          "Full",          "0.06",  "20 ms",
         "Pilot comm. required"),
        ("21 Z1", "Full (α≤0.80)", "Z3 only (α≤0.35)","0.10","20 ms",
         "V_relay deficiency (TR-29)"),
        ("21G",   "N/A",           "Z3 α≤0.35",     "n/a",   "600 ms",
         "I0≫I1 Thevenin broken (TR-31)"),
        ("67N",   "N/A",           "Full (fwd only)","n/a*",  "~30 ms",
         "*I0 from network; no reverse I0 on IBR line"),
        ("67Q",   "N/A",           "Full (fwd+bck)", "0.04",  "~30 ms",
         "Needs I2=k_ibr ≥ 0.04 pu"),
    ]
    fmt = "  {:>8}  {:>16}  {:>16}  {:>7}  {:>7}  {}"
    print(fmt.format("Element","3PH faults","SLG faults","k_min","Speed","Limitation"))
    print("  "+"-"*82)
    for r in rows:
        print(fmt.format(*r))
    print()
    print("  Recommended IBR earth-fault scheme:")
    print("    Primary  : 87L + 67N + 67Q  (20–30 ms, k_ibr ≥ 0.04 pu, all alpha)")
    print("    Backup Z3: 21G cross-pol     (600 ms, alpha ≤ 0.35 only)")
    print()


# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print()
    print("SAMBP TR-32: Sequence Directional Elements 67Q/67N for IBR Networks")
    print("=" * 74)
    print()
    study_a()
    study_b()
    study_c()
    study_d()
    study_e()

    print("=" * 74)
    print("SUMMARY")
    print("=" * 74)
    print("  67N: I0 network-sourced, independent of k_ibr.  Discrimination")
    print("       margin = 2*Re[Z0S]*|I0|^2.  Inherently forward-selective on IBR.")
    print("  67Q: I2 = k_ibr; operates for k_ibr ≥ 0.04 pu (vs 0.10 for 21).")
    print("       Margin = 2*Re[Z1S]*|I2|^2 = 2*R1S*k_ibr^2.")
    print("  Both bypass 21G k0 compensation failure (TR-31).")
    print("  TR-32 complete.")
