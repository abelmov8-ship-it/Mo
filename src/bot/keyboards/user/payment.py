from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.config import settings
from bot.database.models.subscription import PlanDuration
from bot.database.models.user import UserLanguage
from bot.utils.i18n import t


# ── VIP package duration picker ───────────────────────────────────────────────

_PLAN_LABEL_KEYS: dict[PlanDuration, str] = {
    PlanDuration.ONE_WEEK:     "vip.plan_one_week",
    PlanDuration.TWO_WEEKS:    "vip.plan_two_weeks",
    PlanDuration.ONE_MONTH:    "vip.plan_one_month",
    PlanDuration.THREE_MONTHS: "vip.plan_three_months",
    PlanDuration.SIX_MONTHS:   "vip.plan_six_months",
    PlanDuration.ONE_YEAR:     "vip.plan_one_year",
}


def vip_plans_keyboard(prices: dict[PlanDuration, float], locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan, label_key in _PLAN_LABEL_KEYS.items():
        price = prices.get(plan, 0.0)
        builder.button(
            text=t("payment.plan_price_button", locale, label=t(label_key, locale), price=f"{price:.0f}"),
            callback_data=f"buy_vip:{plan.value}",
        )
    builder.adjust(2)
    return builder.as_markup()


# ── Payment method selection ──────────────────────────────────────────────────

def payment_methods_keyboard(
    chapa_enabled: bool,
    has_banks: bool,
    wallet_balance: float,
    locale: UserLanguage = UserLanguage.EN,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if chapa_enabled:
        builder.button(text=t("payment.chapa_button", locale), callback_data="pay:chapa")
    if has_banks:
        builder.button(text=t("payment.bank_button", locale),  callback_data="pay:bank")
    if wallet_balance > 0:
        builder.button(
            text=t("payment.wallet_button", locale, balance=f"{wallet_balance:.0f}"),
            callback_data="pay:wallet",
        )

    builder.adjust(1)
    return builder.as_markup()


def payment_methods_reply_keyboard(
    chapa_enabled: bool,
    has_banks: bool,
    wallet_balance: float,
    locale: UserLanguage = UserLanguage.EN,
) -> ReplyKeyboardMarkup:
    """Same choices, same labels, same admin-editable text as
    payment_methods_keyboard above — just rendered as a persistent reply
    keyboard instead of inline buttons, per settings.PAYMENT_KEYBOARD_TYPE.
    Includes the shared 🏠 Main Menu escape hatch since, unlike an inline
    keyboard, this one replaces whatever reply keyboard the user had
    (typically the main menu) until they explicitly leave."""
    builder = ReplyKeyboardBuilder()

    if chapa_enabled:
        builder.button(text=t("payment.chapa_button", locale))
    if has_banks:
        builder.button(text=t("payment.bank_button", locale))
    if wallet_balance > 0:
        builder.button(text=t("payment.wallet_button", locale, balance=f"{wallet_balance:.0f}"))
    builder.button(text=t("ui.back_to_menu", locale))

    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)


# ── PPV unlock prompt ─────────────────────────────────────────────────────────

def ppv_unlock_keyboard(movie_id: int, price: float, wallet_ok: bool, locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if wallet_ok:
        builder.button(
            text=t("payment.ppv_unlock_button", locale, price=f"{price:.0f}"),
            callback_data=f"ppv_unlock:{movie_id}",
        )
    elif settings.WALLET_TOPUP_ENABLED:
        builder.button(text=t("payment.topup_button", locale), callback_data="pay:wallet_topup")
    # Always offered, not just as a fallback — a locked movie should always
    # give both paths (pay-per-view via wallet, or upgrade to VIP), not force
    # a choice between them.
    builder.button(text=t("payment.upgrade_vip_button", locale), callback_data="nav:vip")
    builder.adjust(1)
    return builder.as_markup()


# ── Receipt upload cancel ─────────────────────────────────────────────────────

def receipt_cancel_keyboard(locale: UserLanguage = UserLanguage.EN) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=t("payment.cancel_button", locale), callback_data="pay:cancel")
    return builder.as_markup()
