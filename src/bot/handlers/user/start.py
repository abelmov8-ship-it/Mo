from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database.models.menu_button import MenuButtonAction, MenuButtonType
from bot.database.models.user import UserLanguage
from bot.filters.menu_action import MenuAction
from bot.filters.text_key_match import TextKeyMatch
from bot.keyboards.user.main_menu import (
    inline_menu_keyboard, language_keyboard, reply_menu_keyboard, welcome_buttons_keyboard,
)
from bot.services.menu_service import MenuButtonService
from bot.services.referral_service import ReferralService
from bot.services.settings_service import SettingsService
from bot.services.user_service import UserService
from bot.utils.formatters import user_context
from bot.utils.i18n import t

# These are the target functions every main-menu action ultimately opens.
# Importing them here (rather than each of those files declaring its own
# "menu:go:x" callback handler) keeps the fan-out in one obvious place — nine
# near-identical one-line callback handlers scattered across nine files would
# be harder to audit than one dispatch table.
from bot.handlers.user.channels import show_categories
from bot.handlers.user.payment import open_payment_menu
from bot.handlers.user.photo_editor import open_photo_editor
from bot.handlers.user.profile import show_profile
from bot.handlers.user.referral import show_referral
from bot.handlers.user.search import prompt_search
from bot.handlers.user.support import open_support
from bot.handlers.user.trending import show_trending
from bot.handlers.user.vip import show_vip_packages

router = Router(name="user:start")


async def _welcome_text(session: AsyncSession, user) -> str:
    """Admin-customized welcome message if one was saved for the user's
    language (bot.utils.i18n handles the override/default/malformed-
    template fallback chain), passing every user_context() field so a
    custom template can reference {user_id}, {status}, etc. — not just
    {first_name} — same as the old bespoke editor advertised."""
    return t("start.welcome", user.language, **user_context(user))


async def render_main_menu(
    message: Message, session: AsyncSession, is_admin: bool, text: str,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    """Sends the welcome text with the reply keyboard, then — each only if
    configured — the admin's welcome-message buttons and the inline main
    menu. Three possible messages, not one, because Telegram doesn't allow
    attaching more than one keyboard to a message, and a reply keyboard and
    two independent inline keyboards is three keyboards. Bots that haven't
    touched either feature get exactly the one message they always got."""
    svc = MenuButtonService(session)
    reply_buttons = await svc.get_visible(MenuButtonType.REPLY)
    inline_buttons = await svc.get_visible(MenuButtonType.INLINE)

    settings_svc = SettingsService(session)
    welcome_buttons = await settings_svc.get_welcome_buttons()
    nav_enabled = await settings_svc.get_bool("welcome_nav_enabled", default=True)

    await message.answer(text, reply_markup=reply_menu_keyboard(reply_buttons, is_admin=is_admin, locale=locale))

    welcome_markup = welcome_buttons_keyboard(welcome_buttons, page=0, paginated=nav_enabled, locale=locale)
    if welcome_markup:
        await message.answer(t("start.links_label", locale), reply_markup=welcome_markup)

    if inline_buttons:
        await message.answer(
            t("start.quick_actions_label", locale),
            reply_markup=inline_menu_keyboard(inline_buttons, page=0, locale=locale),
        )


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()

    user_svc = UserService(session)
    tg = message.from_user

    user, created = await user_svc.get_or_create(
        telegram_id=tg.id,
        first_name=tg.first_name or "User",
        username=tg.username,
    )

    # Handle referral deep-link: /start ref_<code>
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_") and created:
        ref_code = args[1][4:]
        ref_svc = ReferralService(session)
        ref, milestone = await ref_svc.record_invite(ref_code)
        if ref and milestone:
            referrer = await user_svc.get_by_id(ref.user_id)
            if referrer:
                await user_svc.grant_vip(referrer, days=settings.REFERRAL_REWARD_DAYS, plan="referral")
                try:
                    await message.bot.send_message(
                        referrer.telegram_id,
                        t(
                            "start.referral_reward", referrer.language,
                            days=settings.REFERRAL_REWARD_DAYS, milestone=settings.REFERRAL_MILESTONE,
                        ),
                    )
                except Exception:
                    pass

    if created:
        # Deliberately not routed through t()/locale — this is the message
        # that exists to establish what the user's language even is, so
        # localizing it by their (not yet chosen) language is circular.
        # Same reasoning as the fixed 🇬🇧/🇪🇹 labels in language_keyboard().
        await message.answer(
            "👋 Welcome! Please choose your language:",
            reply_markup=language_keyboard(),
        )
    else:
        is_admin = tg.id in settings.ADMIN_IDS
        await render_main_menu(message, session, is_admin, await _welcome_text(session, user), user.language)


@router.message(F.text.in_({"🇬🇧 English", "🇪🇹 አማርኛ"}))
async def handle_language_selection(message: Message, session: AsyncSession) -> None:
    lang_map = {"🇬🇧 English": UserLanguage.EN, "🇪🇹 አማርኛ": UserLanguage.AM}
    lang = lang_map[message.text]

    user_svc = UserService(session)
    await user_svc.set_language(message.from_user.id, lang)
    user = await user_svc.get_by_telegram_id(message.from_user.id)

    is_admin = message.from_user.id in settings.ADMIN_IDS
    welcome = await _welcome_text(session, user) if user else t("start.language_set", lang)
    await render_main_menu(message, session, is_admin, welcome, lang)


@router.message(MenuAction(MenuButtonAction.LANGUAGE))
async def handle_change_language(message: Message, locale: UserLanguage = UserLanguage.EN) -> None:
    await message.answer(t("start.choose_language", locale), reply_markup=language_keyboard())


@router.message(TextKeyMatch("ui.back_to_menu"))
async def handle_back_to_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    """The escape hatch on every temporary reply keyboard a sub-flow shows
    in place of the main menu (see handlers/user/channels.py and
    handlers/user/payment.py's *_KEYBOARD_TYPE == "reply" paths) — clears
    whatever FSM state that sub-flow left behind and restores the real
    main menu. One shared handler rather than one per sub-flow, since
    "leave this temporary keyboard" means exactly the same thing everywhere
    it appears."""
    await state.clear()
    is_admin = message.from_user.id in settings.ADMIN_IDS
    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    locale = user.language if user else UserLanguage.EN
    await render_main_menu(message, session, is_admin, t("start.back_to_main", locale), locale)


# ── Inline main-menu dispatch ───────────────────────────────────────────────
# Each target already has its own real signature (some need session, some
# need state, none need all five) — small lambdas adapt the uniform call
# below to each one exactly, rather than changing nine functions' signatures
# just to make them uniform for this one caller.
_ACTION_DISPATCH = {
    MenuButtonAction.SEARCH: lambda m, bot, session, state, locale: prompt_search(m, bot, session, state, locale),
    MenuButtonAction.CHANNELS: lambda m, bot, session, state, locale: show_categories(m, locale),
    MenuButtonAction.TRENDING: lambda m, bot, session, state, locale: show_trending(m, session, locale),
    MenuButtonAction.REFERRAL: lambda m, bot, session, state, locale: show_referral(m, session),
    MenuButtonAction.VIP_PACKAGE: lambda m, bot, session, state, locale: show_vip_packages(m, session, locale),
    MenuButtonAction.PAYMENT: lambda m, bot, session, state, locale: open_payment_menu(m, session, state),
    MenuButtonAction.PHOTO_EDITOR: lambda m, bot, session, state, locale: open_photo_editor(m, state, locale),
    MenuButtonAction.PROFILE: lambda m, bot, session, state, locale: show_profile(m, session),
    MenuButtonAction.LANGUAGE: lambda m, bot, session, state, locale: handle_change_language(m, locale),
    MenuButtonAction.SUPPORT: lambda m, bot, session, state, locale: open_support(m, state, locale),
}


@router.callback_query(F.data.startswith("menu:go:"))
async def handle_inline_menu_action(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    state: FSMContext,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    try:
        action = MenuButtonAction(callback.data.split(":", 2)[2])
    except ValueError:
        await callback.answer(t("start.action_expired", locale), show_alert=True)
        return
    await callback.answer()
    # Runs against callback.message (the "Quick Actions" card), not a fresh
    # incoming user message — every target here already just sends its own
    # new prompt rather than editing whatever triggered it, exactly like a
    # reply-keyboard tap already does today, so this matches existing
    # navigation behaviour rather than introducing a second style.
    await _ACTION_DISPATCH[action](callback.message, bot, session, state, locale)


@router.callback_query(F.data.startswith("menu:page:"))
async def handle_inline_menu_page(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    page = int(callback.data.split(":")[2])
    inline_buttons = await MenuButtonService(session).get_visible(MenuButtonType.INLINE)
    await callback.message.edit_reply_markup(reply_markup=inline_menu_keyboard(inline_buttons, page=page, locale=locale))
    await callback.answer()


@router.callback_query(F.data.startswith("wbtn:page:"))
async def handle_welcome_buttons_page(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    page = int(callback.data.split(":")[2])
    settings_svc = SettingsService(session)
    buttons = await settings_svc.get_welcome_buttons()
    nav_enabled = await settings_svc.get_bool("welcome_nav_enabled", default=True)
    await callback.message.edit_reply_markup(
        reply_markup=welcome_buttons_keyboard(buttons, page=page, paginated=nav_enabled, locale=locale)
    )
    await callback.answer()


@router.callback_query(F.data == "menu:noop")
async def handle_inline_menu_noop(callback: CallbackQuery) -> None:
    await callback.answer()
