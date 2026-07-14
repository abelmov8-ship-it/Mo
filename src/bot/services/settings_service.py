from __future__ import annotations

import json
from typing import Any

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.setting import Setting

# Fixed set of default delivery-button slots — a closed set (like
# MenuButtonAction) since each name is tied to real, specific handler
# behavior (watchlist toggle, broken-link report, etc.), not admin-defined.
_DEFAULT_BUTTON_DEFAULTS: dict[str, dict] = {
    "watch_later":    {"label": "➕ Watch Later", "enabled": True},
    "report_broken":  {"label": "⚠️ Report Broken Link", "enabled": True},
    "request_movie":  {"label": "📣 Request Movie", "enabled": True},
    "backup_channel": {"label": "🔗 Check Backup Channel", "enabled": True},
}


def button_label(item: dict, locale) -> str:
    """item["label_am"] if set and Amharic was asked for, else
    item["label"] — the one place this fallback is decided for every
    consumer of the generic (label, url) list shape below (welcome_buttons,
    movie_delivery_buttons, backup_channel_links): a plain dict, not an ORM
    row, so this can't live on a model method the way MenuButton.
    display_label does. Takes UserLanguage or a plain "en"/"am" string."""
    lang = locale.value if hasattr(locale, "value") else str(locale)
    label_am = item.get("label_am")
    return label_am if (lang == "am" and label_am) else item["label"]


class SettingsService:
    """
    Typed read/write access to the generic `settings` table.

    Every method takes a `default` so callers can fall back to the static
    value in config.py until an admin overrides it — nothing breaks for
    users who never touch the admin panel.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Raw string get/set ────────────────────────────────────────────────────

    async def get(self, key: str, default: str | None = None) -> str | None:
        row = await self.session.get(Setting, key)
        return row.value if row else default

    async def set(self, key: str, value: str) -> None:
        row = await self.session.get(Setting, key)
        if row:
            row.value = value
        else:
            self.session.add(Setting(key=key, value=value))
        await self.session.flush()

    async def delete(self, key: str) -> None:
        row = await self.session.get(Setting, key)
        if row:
            await self.session.delete(row)
            await self.session.flush()

    # ── Typed convenience wrappers ────────────────────────────────────────────

    async def get_bool(self, key: str, default: bool) -> bool:
        val = await self.get(key)
        return val == "1" if val is not None else default

    async def set_bool(self, key: str, value: bool) -> None:
        await self.set(key, "1" if value else "0")

    async def get_int(self, key: str, default: int) -> int:
        val = await self.get(key)
        return int(val) if val is not None else default

    async def set_int(self, key: str, value: int) -> None:
        await self.set(key, str(value))

    async def get_float(self, key: str, default: float) -> float:
        val = await self.get(key)
        return float(val) if val is not None else default

    async def set_float(self, key: str, value: float) -> None:
        await self.set(key, str(value))

    async def get_json(self, key: str, default: Any) -> Any:
        val = await self.get(key)
        return json.loads(val) if val is not None else default

    async def set_json(self, key: str, value: Any) -> None:
        await self.set(key, json.dumps(value))

    # ── Bank accounts (stored as one JSON list — no relational needs) ───────

    async def get_banks(self) -> list[dict]:
        return await self.get_json("bank_accounts", [])

    async def add_bank(self, name: str, account: str, holder: str) -> dict:
        banks = await self.get_banks()
        next_id = max((b["id"] for b in banks), default=0) + 1
        bank = {"id": next_id, "name": name, "account": account, "holder": holder}
        banks.append(bank)
        await self.set_json("bank_accounts", banks)
        return bank

    async def update_bank(self, bank_id: int, **fields: str) -> bool:
        banks = await self.get_banks()
        for bank in banks:
            if bank["id"] == bank_id:
                bank.update(fields)
                await self.set_json("bank_accounts", banks)
                return True
        return False

    async def delete_bank(self, bank_id: int) -> bool:
        banks = await self.get_banks()
        remaining = [b for b in banks if b["id"] != bank_id]
        if len(remaining) == len(banks):
            return False
        await self.set_json("bank_accounts", remaining)
        return True

    # ── Generic (label, url) list CRUD — shared by welcome_buttons,
    # movie_delivery_buttons, and backup_channel_links below. These are
    # structurally identical (same id/label/url/is_visible/order shape),
    # differing only by which settings key they're stored under, so one
    # implementation backs all three instead of three copies that could
    # silently drift apart if one got a bugfix and the others didn't. ────

    async def get_button_list(self, key: str) -> list[dict]:
        return await self.get_json(key, [])

    async def add_button_to_list(self, key: str, label: str, url: str) -> dict:
        items = await self.get_button_list(key)
        next_id = max((i["id"] for i in items), default=0) + 1
        next_order = max((i.get("order", 0) for i in items), default=-1) + 1
        item = {"id": next_id, "label": label, "url": url, "is_visible": True, "order": next_order}
        items.append(item)
        await self.set_json(key, items)
        return item

    async def update_button_in_list(self, key: str, item_id: int, **fields) -> bool:
        items = await self.get_button_list(key)
        for item in items:
            if item["id"] == item_id:
                item.update(fields)
                await self.set_json(key, items)
                return True
        return False

    async def delete_button_from_list(self, key: str, item_id: int) -> bool:
        items = await self.get_button_list(key)
        remaining = [i for i in items if i["id"] != item_id]
        if len(remaining) == len(items):
            return False
        await self.set_json(key, remaining)
        return True

    async def move_button_in_list(self, key: str, item_id: int, direction: int) -> bool:
        items = sorted(await self.get_button_list(key), key=lambda i: i.get("order", 0))
        idx = next((i for i, item in enumerate(items) if item["id"] == item_id), None)
        if idx is None:
            return False
        target = idx + direction
        if not (0 <= target < len(items)):
            return False
        items[idx]["order"], items[target]["order"] = items[target]["order"], items[idx]["order"]
        await self.set_json(key, items)
        return True

    # ── Welcome message buttons — now thin wrappers over the generic list
    # CRUD above. Same method names/signatures/return shapes as before, so
    # handlers/admin/welcome_buttons.py needed zero changes. ────────────

    async def get_welcome_buttons(self) -> list[dict]:
        return await self.get_button_list("welcome_buttons")

    async def add_welcome_button(self, label: str, url: str) -> dict:
        return await self.add_button_to_list("welcome_buttons", label, url)

    async def update_welcome_button(self, button_id: int, **fields) -> bool:
        return await self.update_button_in_list("welcome_buttons", button_id, **fields)

    async def delete_welcome_button(self, button_id: int) -> bool:
        return await self.delete_button_from_list("welcome_buttons", button_id)

    async def move_welcome_button(self, button_id: int, direction: int) -> bool:
        return await self.move_button_in_list("welcome_buttons", button_id, direction)

    # ── Custom buttons attached to every delivered movie file ──────────

    async def get_movie_delivery_buttons(self) -> list[dict]:
        return await self.get_button_list("movie_delivery_buttons")

    async def add_movie_delivery_button(self, label: str, url: str) -> dict:
        return await self.add_button_to_list("movie_delivery_buttons", label, url)

    async def update_movie_delivery_button(self, button_id: int, **fields) -> bool:
        return await self.update_button_in_list("movie_delivery_buttons", button_id, **fields)

    async def delete_movie_delivery_button(self, button_id: int) -> bool:
        return await self.delete_button_from_list("movie_delivery_buttons", button_id)

    async def move_movie_delivery_button(self, button_id: int, direction: int) -> bool:
        return await self.move_button_in_list("movie_delivery_buttons", button_id, direction)

    # ── Backup channel links (zero-result screen) — used to be a single
    # zero_result_alt_channel_url string; get_backup_channel_links()
    # migrates that value in, once, the first time this is read, so an
    # admin who already configured one link doesn't silently lose it. ──

    async def get_backup_channel_links(self) -> list[dict]:
        existing = await self.get_json("backup_channel_links", None)
        if existing is not None:
            return existing
        legacy_url = await self.get("zero_result_alt_channel_url")
        # Only migrate it forward if it's actually a usable URL — carrying
        # a malformed legacy value into the new list just leaves a dead
        # entry that silently never renders (build_zero_result_keyboard's
        # render-time guard would skip it), which is more confusing to an
        # admin than simply not migrating it at all.
        valid_legacy = legacy_url if legacy_url and legacy_url.startswith(("http://", "https://", "tg://")) else None
        links = (
            [{"id": 1, "label": "🔗 Check Backup Channel", "url": valid_legacy, "is_visible": True, "order": 0}]
            if valid_legacy else []
        )
        await self.set_json("backup_channel_links", links)
        return links

    async def add_backup_channel_link(self, label: str, url: str) -> dict:
        await self.get_backup_channel_links()  # ensures migration has run first
        return await self.add_button_to_list("backup_channel_links", label, url)

    async def update_backup_channel_link(self, link_id: int, **fields) -> bool:
        return await self.update_button_in_list("backup_channel_links", link_id, **fields)

    async def delete_backup_channel_link(self, link_id: int) -> bool:
        return await self.delete_button_from_list("backup_channel_links", link_id)

    async def move_backup_channel_link(self, link_id: int, direction: int) -> bool:
        return await self.move_button_in_list("backup_channel_links", link_id, direction)

    # ── Default delivery buttons (Watch Later, Report Broken Link,
    # Request Movie, Check Backup Channel) — label + on/off per fixed
    # slot. Same "label != function" split as MenuButton: renaming or
    # hiding one of these never touches what it actually does, since the
    # callback_data each slot fires is hardcoded in the handler, not
    # derived from the label. ───────────────────────────────────────────

    async def get_default_button_config(self) -> dict:
        config = await self.get_json("default_button_config", None)
        if config is not None:
            return config

        # First read ever: seed from defaults, migrating the one legacy
        # value that already existed (the request-button on/off toggle)
        # instead of silently resetting an admin's existing choice to True.
        config = {slot: dict(vals) for slot, vals in _DEFAULT_BUTTON_DEFAULTS.items()}
        if await self.get("zero_result_request_enabled") is not None:
            config["request_movie"]["enabled"] = await self.get_bool("zero_result_request_enabled", True)
        await self.set_json("default_button_config", config)
        return config

    async def set_default_button_label(self, slot: str, lang: str, label: str) -> bool:
        config = await self.get_default_button_config()
        if slot not in config:
            return False
        config[slot]["label" if lang == "en" else "label_am"] = label
        await self.set_json("default_button_config", config)
        return True

    async def clear_default_button_label_am(self, slot: str) -> bool:
        config = await self.get_default_button_config()
        if slot not in config:
            return False
        config[slot].pop("label_am", None)
        await self.set_json("default_button_config", config)
        return True

    async def toggle_default_button(self, slot: str) -> bool | None:
        config = await self.get_default_button_config()
        if slot not in config:
            return None
        config[slot]["enabled"] = not config[slot]["enabled"]
        await self.set_json("default_button_config", config)
        return config[slot]["enabled"]

    # ── FAQ entries — same CRUD shape as the button lists above, but with
    # question/answer fields instead of label/url, so it doesn't fit
    # get_button_list()'s shape without renaming its keys underneath admins
    # who already rely on that shape for welcome/delivery/backup buttons. ──

    _DEFAULT_FAQ: list[dict] = [
        {"question": "How do I subscribe to VIP?", "answer": "Tap 💎 VIP Package, choose a plan, then tap 💳 Payment."},
        {"question": "How do I pay?", "answer": "We accept Chapa and bank transfers. Upload your receipt after paying."},
        {"question": "How do referrals work?", "answer": "Share your referral link. Every 5 friends who join earns you 3 VIP days."},
        {"question": "A movie link is broken.", "answer": "Tap ⚠️ Report Broken Link under the movie. Admins are notified immediately."},
    ]

    async def get_faq(self) -> list[dict]:
        existing = await self.get_json("faq", None)
        if existing is not None:
            return existing
        # First read ever: seed from the FAQ that used to be hardcoded in
        # support.py, so an admin who never opens this screen still sees
        # the same FAQ that shipped before this became editable.
        seeded = [
            {"id": i, "is_visible": True, "order": i - 1, **entry}
            for i, entry in enumerate(self._DEFAULT_FAQ, start=1)
        ]
        await self.set_json("faq", seeded)
        return seeded

    async def add_faq_entry(self, question: str, answer: str) -> dict:
        items = await self.get_faq()
        next_id = max((i["id"] for i in items), default=0) + 1
        next_order = max((i.get("order", 0) for i in items), default=-1) + 1
        item = {"id": next_id, "question": question, "answer": answer, "is_visible": True, "order": next_order}
        items.append(item)
        await self.set_json("faq", items)
        return item

    async def update_faq_entry(self, entry_id: int, **fields) -> bool:
        items = await self.get_faq()
        for item in items:
            if item["id"] == entry_id:
                item.update(fields)
                await self.set_json("faq", items)
                return True
        return False

    async def delete_faq_entry(self, entry_id: int) -> bool:
        items = await self.get_faq()
        remaining = [i for i in items if i["id"] != entry_id]
        if len(remaining) == len(items):
            return False
        await self.set_json("faq", remaining)
        return True

    async def move_faq_entry(self, entry_id: int, direction: int) -> bool:
        items = sorted(await self.get_faq(), key=lambda i: i.get("order", 0))
        idx = next((i for i, item in enumerate(items) if item["id"] == entry_id), None)
        if idx is None:
            return False
        target = idx + direction
        if not (0 <= target < len(items)):
            return False
        items[idx]["order"], items[target]["order"] = items[target]["order"], items[idx]["order"]
        await self.set_json("faq", items)
        return True

    # ── Bot texts — admin-editable copy for every user-facing string, keyed
    # like "start.welcome" / "search.no_results" (see bot.utils.i18n). Same
    # one-row-per-language shape as welcome_message_en/am above, generalized
    # to every key instead of just one — a single-field edit costs one row
    # write, not a read-modify-write of a big blob. The full key list and
    # shipped-default text live in code (i18n._DEFAULTS); this table only
    # ever holds *overrides*, so a key no admin has touched costs zero rows.

    async def get_text(self, key: str, lang: str) -> str | None:
        return await self.get(f"text:{key}:{lang}")

    async def set_text(self, key: str, lang: str, value: str) -> None:
        value = value.strip()
        if value:
            await self.set(f"text:{key}:{lang}", value)
        else:
            # Empty input clears the override back to the shipped default,
            # rather than persisting an empty string admins would have to
            # separately notice and delete. Also what the "Reset" button uses.
            await self.delete(f"text:{key}:{lang}")

    async def get_all_text_overrides(self) -> dict[str, dict[str, str]]:
        """One query for every saved override, keyed like _DEFAULTS
        ({key: {lang: value}}) — used to hydrate the in-process t() cache
        at startup and to render the admin browse list."""
        rows = (await self.session.execute(
            select(Setting).where(Setting.key.like("text:%"))
        )).scalars().all()
        overrides: dict[str, dict[str, str]] = {}
        for row in rows:
            _, key, lang = row.key.split(":", 2)
            overrides.setdefault(key, {})[lang] = row.value
        return overrides


# Setting key -> (attribute on bot.config.settings, caster). Every admin
# toggle that previously only mutated settings.X in-process now also writes
# through here, so a restart re-applies the same override instead of
# silently reverting to the .env defaults.
_RUNTIME_OVERRIDES: dict[str, tuple[str, type]] = {
    "maintenance_mode": ("MAINTENANCE_MODE", bool),
    "delete_timer_minutes": ("DELETE_TIMER_MINUTES", int),
    "chapa_enabled": ("CHAPA_ENABLED", bool),
    "wallet_topup_enabled": ("WALLET_TOPUP_ENABLED", bool),
    "anti_spam_threshold": ("ANTI_SPAM_THRESHOLD", int),
    "support_username": ("SUPPORT_USERNAME", str),
    "channels_keyboard_type": ("CHANNELS_KEYBOARD_TYPE", str),
    "payment_keyboard_type": ("PAYMENT_KEYBOARD_TYPE", str),
}


async def hydrate_runtime_settings(session: AsyncSession) -> None:
    """Call once at startup, after create_db_and_tables(). Applies any
    admin-saved overrides onto the live `settings` singleton."""
    from bot.config import settings

    svc = SettingsService(session)
    for key, (attr, caster) in _RUNTIME_OVERRIDES.items():
        raw = await svc.get(key)
        if raw is None:
            continue
        value = (raw == "1") if caster is bool else caster(raw)
        setattr(settings, attr, value)

    secret = await svc.get("chapa_secret_key")
    if secret:
        settings.CHAPA_SECRET_KEY = SecretStr(secret)

    webhook_secret = await svc.get("chapa_webhook_secret")
    if webhook_secret:
        settings.CHAPA_WEBHOOK_SECRET = SecretStr(webhook_secret)
