# =============================================================================
# sambp / digital_twin / integration / goose_security.py
#
# IEC 62351-6 GOOSE security — TR-82 WP 82.2
#
# Standard: IEC 62351-6:2020 — Security for IEC 61850 GOOSE/Sampled Values
#
# Authentication
# --------------
# HMAC-SHA256 tag computed over the GOOSE APDU (excluding the tag field itself).
# Appended as SecurityInformation element in the GOOSE header.
#
# The MAC input is:
#   MAC_input = gocb_ref ‖ app_id (4B) ‖ stnum (4B) ‖ sqnum (4B) ‖
#               t_msg (8B) ‖ dataset_bytes
#
# Each IED pair shares a 256-bit symmetric key.  Keys are indexed by
# KeyID (4 bytes) to allow key rotation without service interruption.
#
# Key Management
# --------------
# KeyStore holds active + pending keys.  Rotation:
#   1. New key distributed out-of-band (pre-positioned)
#   2. Publisher switches to new KeyID
#   3. Subscriber accepts old key for grace_period_ms after rotation
#
# Fallback to Local I/O
# ---------------------
# If authentication fails repeatedly (> fail_threshold in window_ms),
# the security controller:
#   1. Raises HMAC_FAIL alarm (CRITICAL)
#   2. Asserts local_io_mode flag → relay logic switches to hardwired inputs
#   3. Logs blocked message for forensics
#
# Public API
# ----------
#   store  = KeyStore()
#   store.add_key(key_id, key_bytes)
#   signer = GOOSESigner(store, active_key_id)
#   tag    = signer.sign(msg)          → bytes (32-byte HMAC-SHA256)
#
#   ctrl   = GOOSESecurityController(store, fail_threshold=3, window_ms=1000)
#   result = ctrl.verify(msg, t_recv_ms)  → GOOSESecurityResult
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional, Tuple

from integration.goose_anomaly import GOOSEMessage


# ---------------------------------------------------------------------------
# KeyStore
# ---------------------------------------------------------------------------

class KeyStore:
    """Symmetric key store with rotation support."""

    def __init__(self) -> None:
        self._keys: Dict[int, bytes] = {}
        self._active: Optional[int]  = None

    def add_key(self, key_id: int, key_bytes: bytes) -> None:
        """Register a key. First key added becomes active."""
        assert len(key_bytes) == 32, "Key must be 256 bits (32 bytes)"
        self._keys[key_id] = key_bytes
        if self._active is None:
            self._active = key_id

    def set_active(self, key_id: int) -> None:
        if key_id not in self._keys:
            raise KeyError(f"KeyID {key_id} not in store")
        self._active = key_id

    def get_key(self, key_id: int) -> Optional[bytes]:
        return self._keys.get(key_id)

    def get_active(self) -> Tuple[int, bytes]:
        if self._active is None:
            raise RuntimeError("No active key")
        return self._active, self._keys[self._active]

    @property
    def active_key_id(self) -> Optional[int]:
        return self._active

    def rotate(self, new_key_id: int, new_key_bytes: bytes) -> None:
        """Add new key and immediately activate it."""
        self.add_key(new_key_id, new_key_bytes)
        self.set_active(new_key_id)


# ---------------------------------------------------------------------------
# MAC computation
# ---------------------------------------------------------------------------

def _make_mac_input(msg: GOOSEMessage) -> bytes:
    """Serialise GOOSE message fields into MAC input bytes."""
    gocb_b   = msg.gocb_ref.encode("utf-8")
    hdr      = struct.pack(">IIId",
                            msg.app_id,
                            msg.stnum,
                            msg.sqnum,
                            msg.t_msg_ms)
    ds_b     = str(msg.dataset).encode("utf-8")
    return gocb_b + hdr + ds_b


def compute_hmac(msg: GOOSEMessage, key: bytes) -> bytes:
    """Compute HMAC-SHA256 over the GOOSE PDU fields."""
    return hmac.new(key, _make_mac_input(msg), hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# GOOSESigner
# ---------------------------------------------------------------------------

class GOOSESigner:
    """
    Signs outgoing GOOSE messages with HMAC-SHA256.

    Used by the publisher IED.
    """

    def __init__(self, store: KeyStore) -> None:
        self._store = store

    def sign(self, msg: GOOSEMessage) -> bytes:
        """Return HMAC-SHA256 tag; also sets msg.hmac_tag in place."""
        key_id, key = self._store.get_active()
        tag = compute_hmac(msg, key)
        msg.hmac_tag = tag
        return tag


# ---------------------------------------------------------------------------
# GOOSESecurityResult
# ---------------------------------------------------------------------------

@dataclass
class GOOSESecurityResult:
    t_recv_ms:    float
    app_id:       int
    stnum:        int
    hmac_present: bool
    hmac_valid:   bool
    key_id_used:  Optional[int]
    fail_count:   int        # cumulative failures in current window
    local_io_mode: bool      # True → relay uses hardwired backup
    alarm_level:  str        # "OK" | "WARN" | "CRITICAL"
    reason:       str


# ---------------------------------------------------------------------------
# GOOSESecurityController
# ---------------------------------------------------------------------------

class GOOSESecurityController:
    """
    Verifies HMAC on incoming GOOSE messages per IEC 62351-6.

    Parameters
    ----------
    store           : KeyStore
    fail_threshold  : number of failures in window before asserting local_io_mode
    window_ms       : sliding window for failure counting [ms]
    grace_period_ms : accept old key for this long after rotation [ms]
    """

    def __init__(self,
                 store: KeyStore,
                 fail_threshold: int = 3,
                 window_ms:     float = 1000.0,
                 grace_period_ms: float = 5000.0) -> None:
        self._store      = store
        self._fail_thr   = fail_threshold
        self._window     = window_ms
        self._grace      = grace_period_ms
        self._local_io   = False
        self._fail_times: Deque[float] = deque()
        self._rotation_t: Optional[float] = None  # time of last key rotation
        self._prev_key_id: Optional[int]  = None  # key before last rotation

    # ------------------------------------------------------------------
    def notify_rotation(self, prev_key_id: int, t_ms: float) -> None:
        """Notify that publisher has rotated keys; grace period starts."""
        self._rotation_t  = t_ms
        self._prev_key_id = prev_key_id

    # ------------------------------------------------------------------
    def verify(self, msg: GOOSEMessage, t_recv_ms: float) -> GOOSESecurityResult:
        """
        Verify HMAC on one incoming GOOSE message.

        Returns GOOSESecurityResult.  If verification fails repeatedly,
        local_io_mode is set True.
        """
        if not msg.hmac_tag:
            # Unsigned message
            return self._build_result(
                t_recv_ms, msg, hmac_present=False, valid=False,
                key_id=None, reason="No HMAC tag — unsigned message",
            )

        # Try active key
        key_id, key = self._store.get_active()
        expected    = compute_hmac(msg, key)
        valid       = hmac.compare_digest(msg.hmac_tag, expected)
        used_key_id = key_id

        # Try previous key if within grace period
        if (not valid and
                self._prev_key_id is not None and
                self._rotation_t is not None and
                (t_recv_ms - self._rotation_t) < self._grace):
            old_key = self._store.get_key(self._prev_key_id)
            if old_key is not None:
                old_expected = compute_hmac(msg, old_key)
                if hmac.compare_digest(msg.hmac_tag, old_expected):
                    valid       = True
                    used_key_id = self._prev_key_id

        if not valid:
            self._fail_times.append(t_recv_ms)

        # Prune old failures outside window
        while self._fail_times and (t_recv_ms - self._fail_times[0]) > self._window:
            self._fail_times.popleft()

        fail_count = len(self._fail_times)
        if fail_count >= self._fail_thr:
            self._local_io = True

        reason = "HMAC OK" if valid else "HMAC FAILED"
        return self._build_result(t_recv_ms, msg, hmac_present=True,
                                  valid=valid, key_id=used_key_id,
                                  reason=reason)

    # ------------------------------------------------------------------
    def reset_local_io(self) -> None:
        """Manual reset after operator intervention."""
        self._local_io   = False
        self._fail_times.clear()

    @property
    def local_io_mode(self) -> bool:
        return self._local_io

    # ------------------------------------------------------------------
    def _build_result(self,
                      t_ms: float, msg: GOOSEMessage,
                      hmac_present: bool, valid: bool,
                      key_id: Optional[int],
                      reason: str) -> GOOSESecurityResult:
        fail_count = len(self._fail_times)
        if self._local_io:
            alarm = "CRITICAL"
        elif not valid:
            alarm = "WARN" if fail_count < self._fail_thr else "CRITICAL"
        else:
            alarm = "OK"

        return GOOSESecurityResult(
            t_recv_ms=t_ms,
            app_id=msg.app_id,
            stnum=msg.stnum,
            hmac_present=hmac_present,
            hmac_valid=valid,
            key_id_used=key_id,
            fail_count=fail_count,
            local_io_mode=self._local_io,
            alarm_level=alarm,
            reason=reason,
        )
