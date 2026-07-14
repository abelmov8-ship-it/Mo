from __future__ import annotations

import uuid
import logging

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

_BASE = settings.CHAPA_BASE_URL


class ChapaError(Exception):
    pass


class ChapaService:
    """
    Thin async wrapper around the Chapa payment API.
    All methods raise ChapaError on API or network failures.
    """

    def __init__(self) -> None:
        if not settings.CHAPA_SECRET_KEY:
            raise ChapaError("CHAPA_SECRET_KEY is not configured.")
        self._key = settings.CHAPA_SECRET_KEY.get_secret_value()
        self._headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    async def initiate_payment(
        self,
        amount: float,
        email: str,
        first_name: str,
        last_name: str = "",
        phone: str = "",
        callback_url: str = "",
        return_url: str = "",
        tx_ref: str | None = None,
    ) -> dict:
        """
        Creates a new Chapa checkout session.
        Returns the full API response dict on success, with `tx_ref` set on
        it so the caller can later call verify_payment(tx_ref) — Chapa's own
        response body doesn't echo it back.
        """
        tx_ref = tx_ref or f"bot-{uuid.uuid4().hex[:12]}"
        payload = {
            "amount": str(amount),
            "currency": "ETB",
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "phone_number": phone,
            "tx_ref": tx_ref,
            "callback_url": callback_url,
            "return_url": return_url,
            "customization[title]": "VIP Subscription",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.post(f"{_BASE}/transaction/initialize", headers=self._headers, json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ChapaError(f"HTTP error: {exc}") from exc

        data = resp.json()
        if data.get("status") != "success":
            raise ChapaError(f"Chapa error: {data.get('message', 'unknown')}")
        data["tx_ref"] = tx_ref
        return data

    async def verify_payment(self, tx_ref: str) -> dict:
        """Verifies a completed transaction by its reference ID."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                resp = await client.get(
                    f"{_BASE}/transaction/verify/{tx_ref}", headers=self._headers
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise ChapaError(f"HTTP error: {exc}") from exc

        data = resp.json()
        if data.get("status") != "success":
            raise ChapaError(f"Verification failed: {data.get('message', 'unknown')}")
        return data
