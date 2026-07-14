"""
Runnable self-check for verify_chapa_signature (utils/chapa_signature.py).

This is the trust boundary for the whole webhook feature: anyone on the
internet can POST to /webhooks/chapa, and this function is the only thing
standing between "Chapa told us this payment succeeded" and "a stranger
told us this payment succeeded." Both of Chapa's documented header schemes
are checked (chapa-signature = HMAC of the secret; x-chapa-signature = HMAC
of the payload), plus the failure modes: wrong secret, tampered body,
missing headers.

Pure stdlib (hmac/hashlib) — no aiogram/sqlalchemy/httpx needed, so this
runs anywhere, including a bare Python interpreter.

Run directly: `python3 tests/check_chapa_webhook_signature.py`
"""
from __future__ import annotations

import hashlib
import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bot.utils.chapa_signature import verify_chapa_signature  # noqa: E402


def check(label: str, condition: bool) -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    if not condition:
        raise SystemExit(1)


SECRET = "whsec_test_12345"
BODY = b'{"tx_ref": "bot-abc123", "status": "success"}'

real_chapa_sig = hmac.new(SECRET.encode(), SECRET.encode(), hashlib.sha256).hexdigest()
real_payload_sig = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()

# Valid chapa-signature header alone is enough.
check(
    "valid chapa-signature (secret-derived) header accepted",
    verify_chapa_signature(SECRET, BODY, real_chapa_sig, None),
)

# Valid x-chapa-signature header alone is enough.
check(
    "valid x-chapa-signature (payload-derived) header accepted",
    verify_chapa_signature(SECRET, BODY, None, real_payload_sig),
)

# Both present and valid.
check(
    "both headers valid together accepted",
    verify_chapa_signature(SECRET, BODY, real_chapa_sig, real_payload_sig),
)

# Neither header present -> reject.
check(
    "missing both headers rejected",
    not verify_chapa_signature(SECRET, BODY, None, None),
)

# Wrong secret used to sign -> reject.
wrong_secret_sig = hmac.new(b"not-the-secret", SECRET.encode(), hashlib.sha256).hexdigest()
check(
    "chapa-signature computed with wrong secret rejected",
    not verify_chapa_signature(SECRET, BODY, wrong_secret_sig, None),
)

# Tampered body: signature was computed over the original body, not this one.
tampered_body = b'{"tx_ref": "bot-abc123", "status": "success", "amount": 999999}'
check(
    "x-chapa-signature no longer matches a tampered body",
    not verify_chapa_signature(SECRET, tampered_body, None, real_payload_sig),
)

# Garbage/random signature values -> reject.
check(
    "random garbage signature rejected",
    not verify_chapa_signature(SECRET, BODY, "deadbeef" * 8, "cafebabe" * 8),
)

print("\nAll Chapa webhook signature checks passed.")
