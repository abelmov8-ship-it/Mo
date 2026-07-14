# Changes — Chapa automation, abandoned-payment recovery, dynamic FAQ

Auto-kick and expiry reminders (3-day + 1-day) already existed and run
unchanged — see "Already there" below. Everything below is new/modified.

## 1. Chapa webhook automation

**The core problem**: a webhook is a server-to-server POST with no
FSMContext and no callback_data. The old flow only knew *what* to credit
(VIP plan vs. wallet top-up, amount) from data smuggled through Telegram
callback_data — a webhook has none of that. So the real fix wasn't "add a
route", it was "persist the payment intent to the DB at checkout time
instead of at confirmation time", which then powers both the webhook and
the abandoned-payment reminder.

- `handlers/user/payment.py` — `handle_chapa_payment` now creates a
  `Payment(status=PENDING)` row immediately when checkout starts (not
  after confirmation), and passes `callback_url` to Chapa. `verify_chapa_payment`
  is now a thin wrapper around the shared finalize function.
- `services/chapa_fulfillment.py` (new) — `finalize_chapa_payment()`:
  verifies with Chapa's own API (never trusts a webhook payload's claimed
  status alone), atomically claims the row, credits VIP/wallet, and
  returns a message. Shared by the manual Verify button and the webhook —
  one code path, not two.
- `services/payment_service.py` — `try_claim_pending()`: an atomic
  `UPDATE … WHERE status='pending'` so if the webhook and a manual Verify
  tap land at the same moment, exactly one of them wins and credits the
  user — never both.
- `webapp.py` (new) — tiny aiohttp server on `WEBHOOK_PORT` (default
  8080), started alongside the polling bot in `main.py`. Route:
  `POST /webhooks/chapa`. Verifies Chapa's signature before touching
  anything (`utils/chapa_signature.py`, checks both header schemes Chapa
  documents — pure stdlib, has its own passing check script).
- `database/models/payment.py` + migration `d8f9bf71f12c` — unique
  constraint on `reference` (DB-level guarantee, not just an app
  assumption) and a new `reminder_sent_at` column.
- Admin panel → 💳 Payment → ⚙️ Chapa Settings now shows the exact
  webhook URL to paste into Chapa's dashboard, plus a button to set the
  webhook secret live from chat (no redeploy needed).

**No new dependency** — `aiohttp` ships with `aiogram` already.

**You need to do before this works automatically:**
1. Set `PUBLIC_BASE_URL` (e.g. `https://yourdomain.com`) in your env —
   without it, `callback_url` is left blank and Chapa never calls back
   (manual Verify still works exactly as before).
2. Point something (reverse proxy / PaaS router) at port `WEBHOOK_PORT`
   with HTTPS in front — this process only speaks plain HTTP.
3. In Chapa's dashboard, set the webhook URL to `<PUBLIC_BASE_URL>/webhooks/chapa`
   and set a webhook secret — then paste that same secret into the bot via
   Admin Panel → Payment → Chapa Settings → 🔐 Update Webhook Secret.

**Migration caution**: if your live DB somehow already has two payments
sharing a non-null `reference` (only possible via the old flow's
pre-webhook race), the migration will fail fast rather than silently drop
data — reconcile those rows first. Fresh installs don't need this: the
model itself carries the same constraint.

## 2. Abandoned payment recovery (the one missing piece of #2)

- `tasks/abandoned_payment.py` (new) — every 5 min, reminds users with a
  Chapa payment still PENDING after 15 min, once each (tracked via
  `reminder_sent_at`).
- Registered in `tasks/scheduler.py` alongside the existing jobs.

## 3. Dynamic FAQ

- `services/settings_service.py` — FAQ CRUD (`get_faq`/`add_faq_entry`/
  `update_faq_entry`/`delete_faq_entry`/`move_faq_entry`), stored as JSON
  via the settings table you already have. First read seeds from the old
  hardcoded list so nothing changes until an admin edits it.
- `handlers/user/support.py` — FAQ now reads from the DB, filtered/ordered
  by admin settings. Hardcoded `_FAQ` list deleted.
- `handlers/admin/faq.py`, `keyboards/admin/faq.py`, `fsm/admin/faq.py`
  (new) — Add/Edit/Delete/Reorder/Show-Hide, mirroring your existing
  Welcome Buttons admin UX exactly. Entry point: Admin Panel → 📢 Broadcast
  → ❓ Manage FAQ.

**About "Action Mapping"**: this already exists — your Menu Builder
(`handlers/admin/menu.py` + the `MenuButtonAction` enum) already lets an
admin create a button, pick which existing feature it triggers, and set
its label, order, and visibility, all from chat. That's deliberately a
closed set of actions, not a free-form "map to any code path" system —
the docstring on `MenuButtonAction` explains why. A truly-arbitrary
mapping with zero developer involvement would need a scripting/expression
engine (real complexity and a real security surface) to do safely; a new
*feature* still needs someone to write the handler for it, same as any
software. Nothing changed here — flagging it so it's clear this wasn't
missed, just already solved the sane way.

## Self-checks

| Script | Status |
|---|---|
| `tests/check_chapa_webhook_signature.py` | ✅ ran here, passes (pure stdlib) |
| `tests/check_chapa_idempotency.py` | Written, needs sqlalchemy+aiosqlite to run (not available in this sandbox) |
| `tests/check_abandoned_payment_cutoff.py` | Written, needs aiogram to import (not available in this sandbox) |
| `tests/check_faq_settings.py` | Written, needs sqlalchemy+aiosqlite to run (not available in this sandbox) |

Run the three DB/aiogram-dependent ones in your real environment:
`python3 tests/check_chapa_idempotency.py` etc.

## Hotfix — `ChannelService.update()` TypeError from production logs

Pre-existing bug, unrelated to the three features above (not something my
changes touched or introduced).

`update(self, channel_id: int, **kwargs)` named its "which row" parameter
`channel_id` — but `Channel` also has an actual **field** called
`channel_id` (the Telegram chat ID). The moment a caller needed to update
that field — `update(row_id, channel_id=new_value)` — it collided with
itself: `TypeError: got multiple values for argument 'channel_id'`.

Two call sites in `handlers/admin/channels.py` had this exact shape (the
typed-ID and forwarded-message variants of "edit a channel's ID"). Your
log only shows the typed one crashing; the forwarded-message one has the
identical bug and would have crashed the same way the first time someone
used that path instead.

**Fix**: renamed the identifier parameter to `id` across
`get_by_id`/`update`/`delete` in `services/channel_service.py` (all three
do the same row-lookup, so fixing one and leaving the others named
`channel_id` would've been an inconsistent half-fix). All 6 real call
sites pass the identifier positionally, so none needed to change —
verified by grep. `add()`'s `channel_id` param (setting the field on a
*new* row) and `set_force_join()`'s `channel_id` param (harmless — never
takes kwargs, so it can't collide, just a leftover imprecise name) were
both left alone since neither is broken or directly part of this fix.

New check: `tests/check_channel_service_update.py` — reproduces the exact
crashing call shape and asserts it now succeeds.
