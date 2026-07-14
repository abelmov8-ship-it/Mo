"""HMAC verification for Chapa payment webhooks.

Chapa signs every webhook two ways (developer.chapa.co/integrations/webhooks):
  chapa-signature   = HMAC_SHA256(key=secret, msg=secret)    -- proves you hold the secret
  x-chapa-signature = HMAC_SHA256(key=secret, msg=raw_body)  -- proves the payload wasn't altered
Chapa's own docs say to accept the request if EITHER header matches, and
discard it if neither header is present or neither matches.
"""
from __future__ import annotations

import hashlib
import hmac


def verify_chapa_signature(
    secret: str,
    raw_body: bytes,
    chapa_signature: str | None,
    x_chapa_signature: str | None,
) -> bool:
    """Returns True if either signature header is a valid HMAC for *secret*."""
    secret_bytes = secret.encode()
    expected_secret_sig = hmac.new(secret_bytes, secret_bytes, hashlib.sha256).hexdigest()
    expected_payload_sig = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()

    if chapa_signature and hmac.compare_digest(chapa_signature, expected_secret_sig):
        return True
    if x_chapa_signature and hmac.compare_digest(x_chapa_signature, expected_payload_sig):
        return True
    return False
