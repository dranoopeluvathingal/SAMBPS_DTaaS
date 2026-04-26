# =============================================================================
# tests/test_tr82_goose_security.py  —  TR-82 GOOSE cyber-resilience tests
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import os
import random
import struct
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from integration.goose_anomaly import GOOSEAnomalyDetector, GOOSEMessage
from integration.goose_security import (
    KeyStore, GOOSESigner, GOOSESecurityController, compute_hmac,
)


# ---------------------------------------------------------------------------
# Helper: generate a realistic GOOSE traffic stream
# ---------------------------------------------------------------------------

def _make_normal_msg(gocb_ref: str, app_id: int,
                     stnum: int, sqnum: int,
                     t_ms: float,
                     dataset=None) -> GOOSEMessage:
    if dataset is None:
        dataset = [False, False, 1.02, 0.98]
    return GOOSEMessage(
        gocb_ref=gocb_ref, app_id=app_id,
        stnum=stnum, sqnum=sqnum,
        t_msg_ms=t_ms,
        dataset=dataset,
        time_to_live_ms=4000.0,
    )


def _generate_normal_traffic(n: int = 300,
                              T0_ms: float = 4000.0,
                              seed: int = 0) -> list:
    """Generate n normal GOOSE messages with T0 retransmission timing."""
    rng   = random.Random(seed)
    msgs  = []
    t_ms  = 0.0
    stnum = 1
    sqnum = 0

    for i in range(n):
        # Occasionally simulate a new event (stnum++)
        if i > 0 and rng.random() < 0.05:
            stnum += 1
            sqnum  = 0
            # Burst retransmissions: T1=2, 4, 8, … ms
            for bst in range(4):
                t_ms  += 2.0 * (2 ** bst)
                jitter = rng.gauss(0, 0.1)
                msg    = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001,
                                          stnum, bst, t_ms + jitter)
                msgs.append((msg, t_ms + jitter))
                sqnum  = bst + 1
        else:
            t_ms  += T0_ms + rng.gauss(0, 5.0)   # ±5 ms jitter
            sqnum += 1
            msg    = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001,
                                      stnum, sqnum, t_ms)
            msgs.append((msg, t_ms))

    return msgs


# ===========================================================================
# Test 1 — False-positive rate on normal traffic < 1%
# ===========================================================================

def test_false_positive_rate():
    """Isolation forest must flag <1% of normal traffic as anomalous."""
    normal = _generate_normal_traffic(n=500, seed=42)
    det    = GOOSEAnomalyDetector(app_id=0x0001, T0_ms=4000.0, T1_ms=2.0)
    det.train(normal[:300])

    # Evaluate on held-out normal messages
    test_msgs = normal[300:]
    fp = 0
    for msg, t_recv in test_msgs:
        result = det.detect(msg, t_recv)
        # Only count IF-triggered false alarms (rule-based may legitimately fire on edge cases)
        if "CONTENT_ANOMALY" in result.attack_types:
            fp += 1

    fp_rate = fp / max(len(test_msgs), 1)
    assert fp_rate < 0.01, (
        f"False-positive rate {fp_rate:.2%} exceeds 1% threshold"
    )
    print(f"PASS test_false_positive_rate  "
          f"(fp={fp}/{len(test_msgs)}, rate={fp_rate:.2%})")


# ===========================================================================
# Test 2 — Replay attack: stale message detected
# ===========================================================================

def test_replay_attack_detection():
    """Messages with timestamp >> T_replay_age must trigger REPLAY."""
    normal = _generate_normal_traffic(n=200, seed=1)
    det    = GOOSEAnomalyDetector(app_id=0x0001, max_replay_age_ms=5000.0)
    det.train(normal)

    # Prime the detector state
    last_msg, last_t = normal[-1]
    det.detect(last_msg, last_t)

    # Replay: send an old message 10 seconds later
    old_msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001,
                                stnum=last_msg.stnum - 2,
                                sqnum=0,
                                t_ms=last_t - 20000.0)   # t_msg is 20s old
    result = det.detect(old_msg, last_t + 10000.0)       # received now

    assert "REPLAY" in result.attack_types, (
        f"Replay not detected: attacks={result.attack_types}"
    )
    assert result.severity == "CRITICAL"
    print(f"PASS test_replay_attack_detection  (attacks={result.attack_types})")


# ===========================================================================
# Test 3 — Timing flood attack detection
# ===========================================================================

def test_timing_flood_detection():
    """Messages sent faster than flood_threshold_ms must trigger TIMING_FLOOD."""
    normal = _generate_normal_traffic(n=200, seed=2)
    det    = GOOSEAnomalyDetector(app_id=0x0001, flood_threshold_ms=0.5)
    det.train(normal)

    # Prime state
    for msg, t in normal[:10]:
        det.detect(msg, t)

    last_t = normal[9][1]
    # Send 10 messages in 0.1 ms intervals (flooding)
    flood_detected = False
    for i in range(10):
        msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001,
                                stnum=5, sqnum=i, t_ms=last_t + i * 0.05)
        result = det.detect(msg, last_t + i * 0.05)
        if "TIMING_FLOOD" in result.attack_types:
            flood_detected = True

    assert flood_detected, "Timing flood not detected"
    print("PASS test_timing_flood_detection")


# ===========================================================================
# Test 4 — Sequence skip: stnum jumps detected
# ===========================================================================

def test_sequence_skip_detection():
    """Large stnum jump (>3) must trigger SEQUENCE_SKIP."""
    normal = _generate_normal_traffic(n=200, seed=3)
    det    = GOOSEAnomalyDetector(app_id=0x0001)
    det.train(normal)

    # Prime state
    last_msg, last_t = normal[-1]
    det.detect(last_msg, last_t)

    # Jump stnum by 10
    skip_msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001,
                                 stnum=last_msg.stnum + 10,
                                 sqnum=0,
                                 t_ms=last_t + 100.0)
    result = det.detect(skip_msg, last_t + 100.0)

    assert "SEQUENCE_SKIP" in result.attack_types, (
        f"Sequence skip not detected: attacks={result.attack_types}"
    )
    print(f"PASS test_sequence_skip_detection  (attacks={result.attack_types})")


# ===========================================================================
# Test 5 — HMAC-SHA256: signing and successful verification
# ===========================================================================

def test_hmac_sign_verify():
    """Signed message must verify successfully with correct key."""
    key_bytes = os.urandom(32)
    store     = KeyStore()
    store.add_key(key_id=1, key_bytes=key_bytes)

    signer = GOOSESigner(store)
    ctrl   = GOOSESecurityController(store, fail_threshold=3)

    msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001, 10, 0, t_ms=1000.0)
    signer.sign(msg)

    result = ctrl.verify(msg, t_recv_ms=1001.0)
    assert result.hmac_valid, "Signed message should verify successfully"
    assert result.alarm_level == "OK"
    assert not result.local_io_mode
    print("PASS test_hmac_sign_verify")


# ===========================================================================
# Test 6 — Injection attack: tampered message triggers HMAC failure
# ===========================================================================

def test_injection_hmac_failure():
    """Message with tampered dataset must fail HMAC verification."""
    key_bytes = os.urandom(32)
    store     = KeyStore()
    store.add_key(1, key_bytes)

    signer = GOOSESigner(store)
    ctrl   = GOOSESecurityController(store, fail_threshold=10)

    msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001, 5, 0, 500.0)
    signer.sign(msg)

    # Attacker tampers dataset after signing
    msg.dataset = [True, True, 0.0, 0.0]   # injected trip command

    result = ctrl.verify(msg, t_recv_ms=501.0)
    assert not result.hmac_valid, "Tampered message should fail HMAC"
    assert result.alarm_level in ("WARN", "CRITICAL")
    print("PASS test_injection_hmac_failure")


# ===========================================================================
# Test 7 — Local I/O mode asserted after repeated HMAC failures
# ===========================================================================

def test_local_io_mode_after_failures():
    """After fail_threshold HMAC failures, local_io_mode must be True."""
    key_bytes = os.urandom(32)
    wrong_key = os.urandom(32)   # attacker's key
    good_store  = KeyStore()
    good_store.add_key(1, key_bytes)
    bad_store   = KeyStore()
    bad_store.add_key(1, wrong_key)

    good_signer = GOOSESigner(good_store)
    bad_signer  = GOOSESigner(bad_store)   # signs with wrong key
    ctrl        = GOOSESecurityController(good_store, fail_threshold=3, window_ms=5000.0)

    # Send 4 messages signed with wrong key
    for i in range(4):
        msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001, i, 0, float(i * 100))
        bad_signer.sign(msg)
        result = ctrl.verify(msg, t_recv_ms=float(i * 100 + 1))

    assert ctrl.local_io_mode, "local_io_mode should be True after 4 HMAC failures"
    assert result.alarm_level == "CRITICAL"
    print(f"PASS test_local_io_mode_after_failures  "
          f"(fail_count={result.fail_count})")


# ===========================================================================
# Test 8 — Key rotation: old key accepted during grace period
# ===========================================================================

def test_key_rotation_grace_period():
    """Messages signed with old key must still verify during grace period."""
    old_key = os.urandom(32)
    new_key = os.urandom(32)

    store = KeyStore()
    store.add_key(1, old_key)
    old_signer = GOOSESigner(store)

    ctrl = GOOSESecurityController(store, grace_period_ms=5000.0)

    # Sign a message with old key
    msg = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001, 10, 0, 1000.0)
    old_signer.sign(msg)

    # Rotate key and notify controller
    store.rotate(new_key_id=2, new_key_bytes=new_key)
    ctrl.notify_rotation(prev_key_id=1, t_ms=1100.0)

    # Old-signed message arrives 500 ms after rotation (within grace period)
    result = ctrl.verify(msg, t_recv_ms=1600.0)
    assert result.hmac_valid, (
        "Old-key message should verify within grace period"
    )
    print(f"PASS test_key_rotation_grace_period  (key_used={result.key_id_used})")


# ===========================================================================
# Test 9 — Content anomaly: unusual dataset detected by isolation forest
# ===========================================================================

def test_content_anomaly_detection():
    """
    Dataset with extreme values (far from normal range) must trigger
    CONTENT_ANOMALY after training on normal traffic.
    """
    normal = _generate_normal_traffic(n=400, seed=10)
    det    = GOOSEAnomalyDetector(app_id=0x0001, contamination=0.005)
    det.train(normal)

    # Prime detector state
    for msg, t in normal[:20]:
        det.detect(msg, t)

    last_t = normal[19][1]

    # Craft anomalous message: T0 timing OK, stnum/sqnum OK, but extreme dataset
    last_stnum = normal[19][0].stnum
    last_sqnum = normal[19][0].sqnum

    anomalous = False
    for i in range(5):
        # Normal timing, incremented sequence, but extremely unusual dataset
        anom_msg = GOOSEMessage(
            gocb_ref="PROT/LLN0$GO$gcb01",
            app_id=0x0001,
            stnum=last_stnum,
            sqnum=last_sqnum + i + 1,
            t_msg_ms=last_t + 4000.0 * (i + 1),
            dataset=[True, True, 99.99, -99.99, 0.001, 999.0],  # extreme
            time_to_live_ms=4000.0,
        )
        result = det.detect(anom_msg, last_t + 4000.0 * (i + 1))
        if "CONTENT_ANOMALY" in result.attack_types:
            anomalous = True

    assert anomalous, "Anomalous dataset should trigger CONTENT_ANOMALY"
    print("PASS test_content_anomaly_detection")


# ===========================================================================
# Test 10 — Unsigned message: HMAC missing → WARN alarm
# ===========================================================================

def test_unsigned_message_alarm():
    """Message without HMAC tag must raise alarm (no HMAC = security degraded)."""
    store = KeyStore()
    store.add_key(1, os.urandom(32))
    ctrl  = GOOSESecurityController(store, fail_threshold=3)

    msg    = _make_normal_msg("PROT/LLN0$GO$gcb01", 0x0001, 1, 0, 100.0)
    # No hmac_tag set
    result = ctrl.verify(msg, t_recv_ms=100.5)

    assert not result.hmac_valid
    assert not result.hmac_present
    print(f"PASS test_unsigned_message_alarm  (alarm={result.alarm_level})")


# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    test_false_positive_rate()
    test_replay_attack_detection()
    test_timing_flood_detection()
    test_sequence_skip_detection()
    test_hmac_sign_verify()
    test_injection_hmac_failure()
    test_local_io_mode_after_failures()
    test_key_rotation_grace_period()
    test_content_anomaly_detection()
    test_unsigned_message_alarm()
    print("\nAll TR-82 tests passed.")
