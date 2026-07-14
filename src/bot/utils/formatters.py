from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.database.models.user import User, UserLanguage
from bot.database.models.subscription import Subscription
from bot.utils.i18n import t


def user_context(user: User) -> dict[str, Any]:
    """Returns a dict of common user tokens for use in template rendering."""
    return {
        "first_name": user.first_name,
        "username": f"@{user.username}" if user.username else "N/A",
        "user_id": user.telegram_id,
        "wallet_balance": f"{user.wallet_balance:.2f}",
        "language": user.language.value.upper(),
        "status": "💎 VIP" if user.is_vip else "🆓 Free",
    }


def format_expiry(sub: Subscription | None, locale: UserLanguage = UserLanguage.EN) -> str:
    if sub is None:
        return t("common.expiry_none", locale)
    now = datetime.now(timezone.utc)
    delta = sub.expires_at - now
    if delta.total_seconds() <= 0:
        return t("common.expiry_expired", locale)
    days = delta.days
    hours, rem = divmod(delta.seconds, 3600)
    if days > 0:
        return t("common.expiry_days", locale, days=days, hours=hours)
    return t("common.expiry_hours", locale, hours=hours, minutes=rem // 60)


def format_profile(user: User, sub: Subscription | None, locale: UserLanguage = UserLanguage.EN) -> str:
    return t(
        "profile.header", locale,
        id=user.telegram_id,
        name=user.first_name,
        language=user.language.value.upper(),
        wallet=f"{user.wallet_balance:.2f}",
        status="💎 VIP" if user.is_vip else "🆓 Free",
        expiry=format_expiry(sub, locale),
    )


def format_search_result(title: str, file_id: str, ppv_price: float, locale: UserLanguage = UserLanguage.EN) -> str:
    if ppv_price > 0:
        return t("search.result_ppv", locale, title=title, price=f"{ppv_price:.0f}")
    return t("search.result_free", locale, title=title)


def format_payment_pending(amount: float, gateway: str, locale: UserLanguage = UserLanguage.EN) -> str:
    return t("payment.pending_detail", locale, amount=f"{amount:.2f}", gateway=gateway)


def format_vip_granted(days: int, expires_at: datetime, locale: UserLanguage = UserLanguage.EN) -> str:
    return t("vip.granted", locale, days=days, expires=expires_at.strftime("%Y-%m-%d %H:%M UTC"))


def format_analytics(
    total_users: int,
    vip_users: int,
    active_today: int,
    pending_payments: int,
) -> str:
    # Admin-only dashboard (handlers/admin/analytics.py) — deliberately not
    # routed through t(); see the "Zero Hardcoding" summary for why
    # admin-only screens are out of scope for this system.
    return (
        f"📊 <b>Live Analytics</b>\n\n"
        f"👥 Total Users: <b>{total_users:,}</b>\n"
        f"💎 VIP Members: <b>{vip_users:,}</b>\n"
        f"🟢 Active Today: <b>{active_today:,}</b>\n"
        f"⏳ Pending Payments: <b>{pending_payments}</b>"
    )
