from __future__ import annotations

import logging
from typing import Any

from bot.database.models.user import UserLanguage

logger = logging.getLogger(__name__)


def render(template: str, **kwargs: Any) -> str:
    """Replaces {key} tokens in a template string.

    Lives here (not formatters.py) so formatters.py can import t() from
    this module without the two importing each other — this is the one
    piece formatters.py's own format_*() functions and t() both need.

    Example: render("Hello {first_name}!", first_name="Selam") -> "Hello Selam!"
    """
    return template.format(**kwargs)


# Shipped defaults for every admin-editable string, namespaced by the
# module that owns it ("start.welcome") so a key traces back to its call
# site. This dict IS the key registry: handlers/admin/texts.py lists and
# groups these (by the part before the first ".") for the admin browse
# screen. Admin edits never touch this dict — they land as per-language
# overrides in the `settings` table (SettingsService get/set_text) and get
# merged on top of this at runtime by hydrate_bot_texts(). A key nobody has
# overridden costs zero DB rows and just renders what's here, so shipping a
# new user-facing string is exactly one entry in this dict.
_DEFAULTS: dict[str, dict[str, str]] = {
    "start.welcome": {
        "en": "Welcome to Movie Bot, {first_name}!",
        "am": "እንኳን ደህና መጡ፣ {first_name}!",
    },
    "search.prompt": {
        "en": "Type a movie title to search:",
        "am": "የፊልም ስም ይፈልጉ:",
    },
    "search.no_results": {
        "en": 'No results found for "{query}".',
        "am": 'ለ"{query}" ምንም ውጤት አልተገኘም።',
    },
    "vip.expired": {
        "en": "⚠️ Your VIP subscription has expired.\n\nTap 💎 VIP Package to renew and restore your access.",
        "am": "የ VIP ምዝገባዎ ጊዜው አልፏል።",
    },
    "payment.pending": {
        "en": "Payment submitted. Awaiting admin approval.",
        "am": "ክፍያ ቀርቧል። የአስተዳዳሪ ፈቃድ እየጠበቁ ነው።",
    },

    # ── start.py ─────────────────────────────────────────────────────────
    # start.choose_language / start.welcome (above) intentionally aren't
    # shown per the user's *saved* language — choose_language is what
    # establishes it in the first place, and cmd_start's very first message
    # to a brand-new user (also literally "choose your language") has the
    # same problem. Both stay as fixed bot copy rather than routing through
    # this key/locale system; see handlers/user/start.py.
    "start.referral_reward": {
        "en": "🎉 You earned <b>{days} VIP days</b> for reaching {milestone} referrals!",
    },
    "start.language_set": {
        "en": "✅ Language set!",
    },
    "start.choose_language": {
        "en": "Choose your language:",
    },
    "start.links_label": {
        "en": "🔗 Links:",
    },
    "start.quick_actions_label": {
        "en": "⚡ Quick Actions:",
    },
    "start.action_expired": {
        "en": "This button's action no longer exists.",
    },
    "start.back_to_main": {
        "en": "Back to main menu.",
    },

    # ── channels.py ──────────────────────────────────────────────────────
    "channels.category_prompt": {"en": "🎬 <b>Movie Channels</b>\n\nChoose a category:"},
    "channels.category_prompt_back": {"en": "🎬 Choose a category:"},
    "channels.free_label": {"en": "🆓 Free Channels"},
    "channels.vip_label": {"en": "💎 VIP Channels"},
    "channels.vip_only": {"en": "💎 VIP channels are for subscribers only."},
    "channels.empty_category": {"en": "No channels in this category yet."},
    "channels.select_channel": {"en": "<b>{label}</b>\n\nSelect a channel:"},
    "channels.back_button": {"en": "⬅️ Back"},
    "channels.not_found": {"en": "Channel not found."},
    "channels.one_time_link": {
        "en": "Here's your one-time link for <b>{name}</b>.\nThis link works once — use it immediately.",
    },
    "channels.open_button": {"en": "👉 Open {name}"},

    # ── trending.py ──────────────────────────────────────────────────────
    "trending.empty": {"en": "📭 No trending posters yet. Check back soon!"},

    # ── referral.py ──────────────────────────────────────────────────────
    "referral.start_first": {"en": "Please /start first."},
    "referral.summary": {
        "en": (
            "📢 <b>Referral Rewards</b>\n\n"
            "Share your link and earn <b>{reward_days} VIP days</b> for every "
            "<b>{milestone} friends</b> who join!\n\n"
            "🔗 Your link:\n<code>{link}</code>\n\n"
            "👥 Total invites: <b>{invite_count}</b>\n"
            "🎯 {remaining} more to unlock your next reward!"
        ),
    },

    # ── profile.py ───────────────────────────────────────────────────────
    "profile.not_found": {"en": "User not found. Please /start again."},
    "profile.not_found_alert": {"en": "User not found."},
    "profile.watchlist_button": {"en": "👀 My Watchlist"},
    "profile.watchlist_remove_button": {"en": "❌ {title}"},
    "profile.watchlist_empty": {
        "en": "📭 Your watchlist is empty.\n\nTap ➕ Watch Later under any search result to save it here.",
    },
    "profile.watchlist_header": {
        "en": "👀 <b>My Watchlist</b> ({count})\n\nSearch a title below to get the file. Tap ❌ to remove it.",
    },
    "profile.watchlist_showing_recent": {"en": "\n\nShowing the {max} most recent."},
    "profile.watchlist_removed": {"en": "➖ Removed."},

    # ── vip.py ───────────────────────────────────────────────────────────
    "vip.packages_intro": {
        "en": (
            "💎 <b>VIP Packages</b>\n\n"
            "Unlock all VIP channels, skip PPV fees, and enjoy priority access.\n\n"
            "Choose a plan:"
        ),
    },
    "vip.packages_intro_short": {"en": "💎 <b>VIP Packages</b>\n\nChoose a plan:"},
    "vip.invalid_plan": {"en": "Invalid plan."},
    # price arrives pre-formatted ("1200", not 1200.0) from the call site —
    # every admin-editable template sticks to plain {name} placeholders,
    # never a format spec like {price:.0f}, since that's an easy thing for
    # a non-programmer editing text in a Telegram chat to break.
    "vip.plan_selected_toast": {"en": "Selected: {plan} — {price} Birr"},
    "vip.plan_selected": {
        "en": "✅ Plan selected: <b>{plan}</b> — <b>{price} Birr</b>\n\nTap <b>💳 Payment</b> from the main menu to complete your purchase.",
    },

    # ── wallet.py ────────────────────────────────────────────────────────
    "wallet.redeem_usage": {"en": "Usage: <code>/redeem CODE</code>"},
    "wallet.start_first": {"en": "Please /start the bot first."},
    "wallet.error_loading": {"en": "Error loading data."},
    "wallet.insufficient_balance": {"en": "❌ Insufficient balance. You need {price} Birr."},
    "wallet.deduction_failed": {"en": "Deduction failed. Please try again."},
    "wallet.unlocked_toast": {"en": "✅ Unlocked! New balance: {balance} Birr"},
    "wallet.unlocked_caption": {"en": "🎬 <b>{title}</b>\nUnlocked via wallet 🔓"},

    # ── utils/movie_delivery.py ──────────────────────────────────────────
    # The "add to watchlist" state of this button is watch_later["label"]
    # (admin-editable, via SettingsService's default-button-config slots —
    # see handlers/admin/delivery_buttons.py). This key is only its OTHER
    # state, once already added — a fixed string this session's original
    # sweep missed, since movie_delivery.py was only touched back then for
    # locale-threading, not a full per-string audit. Caught while wiring up
    # bilingual support for the admin-editable slot right next to it —
    # leaving this one hardcoded would mean the button visibly flips from
    # Amharic to English text the moment a user taps it.
    "movie.in_watchlist_label": {"en": "✅ In Watchlist"},

    # ── services/promo_service.py ───────────────────────────────────────
    "promo.invalid": {"en": "❌ Invalid promo code."},
    "promo.expired": {"en": "❌ This promo code has expired."},
    "promo.exhausted": {"en": "❌ This promo code has reached its usage limit."},
    "promo.redeemed_vip": {"en": "🎉 Redeemed! You've been granted <b>{days} VIP days</b>."},
    "promo.redeemed_wallet": {"en": "🎉 Redeemed! <b>{amount} Birr</b> added to your wallet."},

    # ── search.py ────────────────────────────────────────────────────────
    "search.must_join": {"en": "⚠️ You must join the following channels to use the bot:"},
    "search.query_too_short": {"en": "Please enter at least 2 characters."},
    "search.subscription_ok": {"en": "✅ Great! You're all set. Now search for any movie."},
    "search.not_found_alert": {"en": "User not found."},
    "search.watchlist_added": {"en": "➕ Added to watchlist!"},
    "search.watchlist_already": {"en": "Already in your watchlist."},
    "search.watchlist_removed": {"en": "➖ Removed from watchlist."},
    "search.watchlist_not_in": {"en": "Wasn't in your watchlist."},
    "search.reported": {"en": "⚠️ Reported! Thank you."},
    "search.request_logged": {"en": "📣 Your request has been logged!"},

    # ── support.py (FAQ entry content itself stays single-language for now
    # — see the summary for why that's a separate, larger follow-up) ──────
    "support.contact_button": {"en": "💬 Contact Support"},
    "support.faq_button": {"en": "❓ FAQ"},
    "support.center_intro": {"en": "🆘 <b>Support Center</b>\n\nHow can we help?"},
    "support.faq_empty": {"en": "❓ No FAQ entries yet. Contact support with your question."},
    "support.faq_header": {"en": "❓ <b>Frequently Asked Questions</b>\n"},
    "support.contact_prompt": {"en": "💬 Type your message below and we'll get back to you as soon as possible:"},
    "support.ticket_sent": {"en": "✅ Your message has been sent to support. We'll reply shortly."},
    "support.ticket_failed": {"en": "⚠️ Automated routing failed. Please contact {handle} directly."},

    # ── payment.py ───────────────────────────────────────────────────────
    "payment.menu_intro": {"en": "💳 <b>Payment</b>\n\nChoose your payment method:"},
    "payment.bank_line": {"en": "🏦 <b>{name}</b>\nAccount: <code>{account}</code>\nHolder: {holder}"},
    "payment.no_banks": {"en": "No bank accounts are configured. Please contact support."},
    "payment.bank_transfer_intro": {
        "en": (
            "🏦 <b>Bank Transfer</b>\n\nAmount: <b>{amount} Birr</b>\n\n{bank_lines}\n\n"
            "After transferring, send your payment screenshot here:"
        ),
    },
    "payment.cancelled": {"en": "❌ Payment cancelled."},
    "payment.chapa_unavailable": {"en": "Chapa is currently unavailable."},
    "payment.start_first": {"en": "Please /start the bot first."},
    "payment.chapa_init_failed": {"en": "❌ Couldn't start the Chapa checkout. Please try another method."},
    "payment.chapa_no_checkout_url": {"en": "❌ Chapa didn't return a checkout link. Please try another method."},
    "payment.pay_now_button": {"en": "💳 Pay Now"},
    "payment.verify_button": {"en": "✅ I've Paid — Verify"},
    "payment.cancel_button": {"en": "❌ Cancel"},
    "payment.chapa_checkout_intro": {
        "en": (
            "💳 <b>Chapa Checkout</b>\n\nAmount: <b>{amount} Birr</b>\n\n"
            "Tap below to pay — you'll get a confirmation automatically. "
            "If it doesn't arrive within a minute, tap Verify."
        ),
    },
    "payment.checking_toast": {"en": "⏳ Checking..."},
    "payment.topup_disabled": {
        "en": "Wallet top-ups are currently unavailable. Please upgrade to a full VIP package to watch this movie.",
    },
    "payment.topup_prompt": {"en": "💳 How much would you like to top up (in Birr)?"},
    "payment.topup_invalid": {"en": "❌ Send a positive number, e.g. 100."},
    "payment.topup_method_prompt": {"en": "Top-up amount: <b>{amount} Birr</b>\n\nChoose how to pay:"},
    "payment.insufficient_balance": {"en": "❌ Insufficient balance. You need {amount} Birr."},
    "payment.deduction_failed": {"en": "Deduction failed. Please try again."},
    "payment.paid_from_wallet_toast": {"en": "✅ Paid from wallet! New balance: {balance} Birr"},

    # ── utils/formatters.py — shared across profile/search/payment/vip ────
    "common.expiry_none": {"en": "—"},
    "common.expiry_expired": {"en": "❌ Expired"},
    "common.expiry_days": {"en": "✅ {days}d {hours}h remaining"},
    "common.expiry_hours": {"en": "✅ {hours}h {minutes}m remaining"},
    "profile.header": {
        "en": (
            "👤 <b>Profile</b>\n\n"
            "🆔 ID: <code>{id}</code>\n"
            "📛 Name: {name}\n"
            "🌐 Language: {language}\n"
            "💰 Wallet: <b>{wallet} Birr</b>\n\n"
            "📋 <b>Subscription</b>\n"
            "Status: {status}\n"
            "Expires: {expiry}"
        ),
    },
    "search.result_ppv": {"en": "🔒 <b>{title}</b>\n💳 PPV — {price} Birr to unlock"},
    "search.result_free": {"en": "🎬 <b>{title}</b>"},
    "payment.pending_detail": {
        "en": (
            "⏳ <b>Payment Submitted</b>\n\n"
            "Amount: <b>{amount} Birr</b>\n"
            "Gateway: {gateway}\n\n"
            "Your receipt is under review. You will be notified once approved."
        ),
    },
    "vip.granted": {
        "en": (
            "🎉 <b>VIP Activated!</b>\n\n"
            "Duration: <b>{days} days</b>\n"
            "Expires: <b>{expires}</b>\n\n"
            "Enjoy your premium access! 💎"
        ),
    },

    # ── services/chapa_fulfillment.py ───────────────────────────────────
    "payment.not_found": {"en": "❌ We couldn't find that payment. Please contact support."},
    "payment.already_confirmed": {"en": "✅ Already confirmed — you're all set!"},
    "payment.account_not_found": {"en": "❌ We couldn't find your account. Please contact support."},
    "payment.verify_pending": {
        "en": "⏳ Payment not confirmed yet. If you've already paid, wait a moment and try again.",
    },
    "payment.wallet_topped_up": {"en": "✅ Wallet topped up by <b>{amount} Birr</b>! New balance: {balance} Birr"},

    # ── tasks/reminders.py & tasks/abandoned_payment.py ─────────────────
    "reminder.expiry": {
        "en": (
            "⏰ <b>VIP Expiry Reminder</b>\n\n"
            "Your subscription expires in <b>{days} day{suffix}</b>.\n"
            "{expiry}\n\n"
            "Tap 💎 VIP Package to renew now."
        ),
    },
    "reminder.abandoned_payment": {
        "en": (
            "👋 Looks like you didn't finish your payment.\n\n"
            "Amount: <b>{amount} Birr</b>\n\n"
            "Tap 💳 Payment to pick up where you left off — or if you've "
            "already paid, open the checkout message again and tap Verify."
        ),
    },

    # ── photo_editor.py ──────────────────────────────────────────────────
    "photo.processing": {"en": "⏳ Processing…"},
    "photo.processing_error": {"en": "❌ Processing error: {error}"},
    "photo.editor_intro": {"en": "🎨 <b>Photo Editor</b>\n\nWhat would you like to do?"},
    "photo.editor_closed": {"en": "❌ Photo editor closed."},
    "photo.collage_start": {"en": "🗂 Send 2–{max} photos, one by one, for the collage."},
    "photo.prompt_resize": {"en": "📐 Send me the photo you want to resize."},
    "photo.prompt_rotate": {"en": "🔄 Send me the photo you want to rotate or flip."},
    "photo.prompt_text": {"en": "✏️ Send me the photo you want to add text to."},
    "photo.prompt_frame": {"en": "🖼 Send me the photo you want to frame."},
    "photo.prompt_generic": {"en": "Send me a photo."},
    "photo.pick_size": {"en": "📐 Pick a size:"},
    "photo.pick_direction": {"en": "🔄 Pick a direction:"},
    "photo.pick_frame": {"en": "🖼 Pick a frame style:"},
    "photo.enter_overlay_text": {"en": "✏️ Now type the text you want to overlay on the photo:"},
    "photo.collage_max_reached": {"en": "⚠️ Maximum {max} photos reached. Tap Finish to build the collage."},
    "photo.collage_progress": {"en": "✅ Got it ({count}/{max}). Send another or finish."},
    "photo.collage_need_more": {"en": "Send at least 2 photos first."},
    "photo.collage_pick_layout": {"en": "🗂 Choose a layout:"},
    "photo.collage_ready": {"en": "✅ Collage ready ({count} photos, {cols} columns)."},
    "photo.custom_size_prompt": {"en": "✏️ Send the size as <code>WIDTHxHEIGHT</code>, e.g. <code>800x600</code>."},
    "photo.resized": {"en": "✅ Resized to {width}×{height}."},
    "photo.custom_size_invalid": {"en": "❌ Use the format WIDTHxHEIGHT (whole numbers, 1–6000), e.g. 800x600."},
    "photo.done": {"en": "✅ Done."},
    "photo.text_added": {"en": "✅ Text added: <i>{text}</i>"},
    "photo.overlay_text_empty": {"en": "❌ Send some text to overlay."},

    # ── keyboards/user/main_menu.py — repeated pagination chrome ────────
    # 🛠 Admin Panel and the 🇬🇧/🇪🇹 language-picker labels are deliberately
    # NOT here — see handlers/user/start.py for why.
    "ui.prev": {"en": "◀️ Prev"},
    "ui.next": {"en": "Next ▶️"},
    # Deliberately NOT the same text as the admin's fixed "⬅️ Back to Main
    # Menu" reply button (handlers/admin/panel.py) — that string is outside
    # this system on purpose (see start.py), and giving an admin-editable
    # key the identical default would make the two ambiguous the moment
    # anyone's reply keyboard shows both at once.
    "ui.back_to_menu": {"en": "🏠 Main Menu"},

    # ── keyboards/user/payment.py ───────────────────────────────────────
    "vip.plan_one_week": {"en": "1 Week"},
    "vip.plan_two_weeks": {"en": "2 Weeks"},
    "vip.plan_one_month": {"en": "1 Month"},
    "vip.plan_three_months": {"en": "3 Months"},
    "vip.plan_six_months": {"en": "6 Months"},
    "vip.plan_one_year": {"en": "1 Year"},
    "payment.plan_price_button": {"en": "{label} — {price} Birr"},
    "payment.chapa_button": {"en": "💳 Pay with Chapa"},
    "payment.bank_button": {"en": "🏦 Bank Transfer"},
    "payment.wallet_button": {"en": "👛 Use Wallet ({balance} Birr)"},
    "payment.ppv_unlock_button": {"en": "🔓 Unlock for {price} Birr"},
    "payment.topup_button": {"en": "💳 Top-up Wallet"},
    "payment.upgrade_vip_button": {"en": "💎 Upgrade to VIP"},

    # ── keyboards/user/search.py ─────────────────────────────────────────
    "search.join_button": {"en": "👉 Join {name}"},
    "search.check_again_button": {"en": "✅ I've Joined — Check Again"},

    # ── keyboards/user/photo_editor.py ──────────────────────────────────
    "photo.tool_resize": {"en": "📐 Resize"},
    "photo.tool_rotate": {"en": "🔄 Rotate / Flip"},
    "photo.tool_text": {"en": "✏️ Add Text"},
    "photo.tool_frame": {"en": "🖼 Add Frame"},
    "photo.tool_collage": {"en": "🗂 Collage"},
    "photo.cancel_button": {"en": "❌ Cancel"},
    "photo.size_a4": {"en": "A4  (1240×1754)"},
    "photo.size_a5": {"en": "A5  (874×1240)"},
    "photo.size_a6": {"en": "A6  (620×874)"},
    "photo.size_b4": {"en": "B4  (1476×2079)"},
    "photo.size_b5": {"en": "B5  (1039×1476)"},
    "photo.size_custom": {"en": "✏️ Custom"},
    "photo.back_button": {"en": "⬅️ Back"},
    "photo.rotate_ccw90": {"en": "↩ Rotate 90° CCW"},
    "photo.rotate_cw90": {"en": "↪ Rotate 90° CW"},
    "photo.flip_horizontal": {"en": "↔ Flip Horizontal"},
    "photo.flip_vertical": {"en": "↕ Flip Vertical"},
    "photo.frame_black": {"en": "⬛ Black Border"},
    "photo.frame_white": {"en": "⬜ White Border"},
    "photo.frame_gold": {"en": "🟫 Gold Border"},
    "photo.collage_finish_button": {"en": "✅ Finish ({count}/{max})"},
    "photo.collage_2col": {"en": "▦ 2 Columns"},
    "photo.collage_3col": {"en": "▦ 3 Columns"},
}

# Populated once at startup (bot.main, alongside hydrate_runtime_settings)
# and kept live after that: every admin save writes here too, so the very
# next message reflects it with no per-message DB round trip — same
# immediate-effect pattern as settings.DELETE_TIMER_MINUTES in
# handlers/admin/system.py.
_overrides: dict[str, dict[str, str]] = {}


async def hydrate_bot_texts(session) -> None:
    """Call once at startup, after create_db_and_tables()."""
    from bot.services.settings_service import SettingsService
    svc = SettingsService(session)
    _overrides.clear()
    _overrides.update(await svc.get_all_text_overrides())

    # ponytail: one-time bridge for admins who already customized the
    # welcome message through the old bespoke editor (which wrote
    # welcome_message_en/am directly, before "welcome" became just another
    # key here). Promotes each legacy value into the new format — but only
    # if nothing's been saved under the new key yet — then deletes the
    # legacy row, so this is self-limiting: safe to run every startup, and
    # a true no-op once every environment has migrated once. Ceiling: this
    # is specific to the one key the old editor covered; it's not a general
    # migration mechanism and shouldn't grow into one.
    for lang in ("en", "am"):
        if lang in _overrides.get("start.welcome", {}):
            continue
        legacy = await svc.get(f"welcome_message_{lang}")
        if legacy:
            await save_text_override(session, "start.welcome", lang, legacy)
            await svc.delete(f"welcome_message_{lang}")
    await session.commit()


async def save_text_override(session, key: str, lang: str, value: str) -> None:
    """The only way admin handlers should write a text override — keeps the
    DB row and the live cache from drifting apart (a write that updated one
    but not the other would silently not take effect until restart, or
    would revert on the next one). value="" clears back to the default."""
    from bot.services.settings_service import SettingsService
    await SettingsService(session).set_text(key, lang, value)
    if value.strip():
        _overrides.setdefault(key, {})[lang] = value.strip()
    else:
        _overrides.get(key, {}).pop(lang, None)


def known_keys() -> list[str]:
    """Every registered text key, for the admin browse screen."""
    return sorted(_DEFAULTS)


def current_value(key: str, lang: str) -> tuple[str | None, bool]:
    """(value, is_override) for a key/lang — value is None if there's
    neither an admin override nor a shipped default for that language."""
    override = _overrides.get(key, {}).get(lang)
    if override is not None:
        return override, True
    return _DEFAULTS.get(key, {}).get(lang), False


def t(key: str, locale: UserLanguage | str = UserLanguage.EN, **kwargs: object) -> str:
    """Look up `key` for the given locale: admin override in that language,
    then the shipped default in that language, then admin override in
    English, then the shipped default in English, then the bare key.

    A template that fails to render (e.g. an admin edit with a typo'd
    {placeholder}) is skipped rather than raised, so one bad edit degrades
    to the next fallback instead of breaking every user who hits that
    screen — mirrors the try/except that used to live in start.py's
    _welcome_text before "welcome" became just another key here.
    ponytail: if the *shipped* default is also malformed that's a real code
    bug, not a content bug — the loop still bottoms out at the bare key so
    a message goes out rather than the handler raising.
    """
    lang = locale.value if isinstance(locale, UserLanguage) else str(locale)
    override, default = _overrides.get(key, {}), _DEFAULTS.get(key, {})
    # Exhausts the requested language first (override, then its own shipped
    # default) before ever falling back to English — checking the English
    # override before the requested language's default would leak an
    # English-only edit into every other language for any key that already
    # has a real translation, which is the opposite of "leave the other
    # language unchanged."
    for template in (override.get(lang), default.get(lang), override.get("en"), default.get("en")):
        if not template:
            continue
        try:
            return render(template, **kwargs)
        except (KeyError, ValueError, IndexError):
            logger.warning("Bad template for key=%s lang=%s — trying next fallback.", key, lang)
    return key
