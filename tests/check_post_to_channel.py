"""
Runnable self-check for Phase 5 (Post-to-Channel captions + social links).

1. _toggle_fixed_button: watch/reactions add-then-remove correctly and
   don't disturb other button kinds already accumulated.
2. _buttons_menu_keyboard: checkmarks reflect current state, and the
   "Add Social Media Button" option disappears once MAX_SOCIAL_BUTTONS is
   reached — the cap is enforced in the UI, not just documented in a
   comment.
3. _build_post_markup: builds the right mix of url= and callback_data=
   buttons from an accumulated list, and returns None (not an empty
   keyboard) when nothing was added — this is what makes "buttons are
   optional" actually true rather than just claimed.

Run directly: `python3 tests/check_post_to_channel.py`
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bot.handlers.admin.content import (
    MAX_SOCIAL_BUTTONS,
    _build_post_markup,
    _buttons_menu_keyboard,
    _buttons_status_text,
    _toggle_fixed_button,
)


def check_toggle_fixed_button():
    empty: list[dict] = []
    with_watch = _toggle_fixed_button(empty, "watch")
    assert with_watch == [{"kind": "watch"}]

    back_to_empty = _toggle_fixed_button(with_watch, "watch")
    assert back_to_empty == [], "tapping the same kind again must remove it"

    mixed = [{"kind": "url", "label": "TikTok", "url": "https://t.co"}]
    with_reactions = _toggle_fixed_button(mixed, "reactions")
    assert len(with_reactions) == 2 and mixed[0] in with_reactions, "toggling one kind must not disturb others"

    print("✓ _toggle_fixed_button: add/remove correctly, without disturbing other button kinds")


def check_buttons_menu_reflects_state():
    def labels(markup):
        return [b.text for row in markup.inline_keyboard for b in row]

    empty_labels = labels(_buttons_menu_keyboard([]))
    assert "✅ 🎬 Watch Button" not in empty_labels
    assert "🔗 Add Social Media Button" in empty_labels

    with_watch = labels(_buttons_menu_keyboard([{"kind": "watch"}]))
    assert "✅ 🎬 Watch Button" in with_watch, "checkmark must appear once added"

    maxed_out = [{"kind": "url", "label": f"L{i}", "url": f"https://x.com/{i}"} for i in range(MAX_SOCIAL_BUTTONS)]
    maxed_labels = labels(_buttons_menu_keyboard(maxed_out))
    assert "🔗 Add Social Media Button" not in maxed_labels, "cap must actually hide the option, not just cosmetic"

    print("✓ _buttons_menu_keyboard: checkmarks and the social-button cap both reflect real state")


def check_status_text():
    assert "optional" in _buttons_status_text([]).lower()
    text = _buttons_status_text([{"kind": "watch"}, {"kind": "url", "label": "TikTok", "url": "https://t.co"}])
    assert "Watch" in text and "TikTok" in text

    print("✓ _buttons_status_text: reflects empty and populated states correctly")


def check_build_post_markup():
    assert _build_post_markup({"post_buttons": []}, "mybot") is None, "no buttons -> None, not an empty keyboard"

    mixed = {
        "post_buttons": [
            {"kind": "watch"},
            {"kind": "reactions"},
            {"kind": "url", "label": "📱 TikTok", "url": "https://tiktok.com/@x"},
            {"kind": "url", "label": "▶️ YouTube", "url": "https://youtube.com/x"},
        ]
    }
    markup = _build_post_markup(mixed, "mybot")
    all_buttons = [b for row in markup.inline_keyboard for b in row]

    watch_btn = next(b for b in all_buttons if b.text == "🎬 Watch in Bot")
    assert watch_btn.url == "https://t.me/mybot"

    like_btn = next(b for b in all_buttons if b.text == "👍")
    assert like_btn.callback_data == "react:like"

    tiktok_btn = next(b for b in all_buttons if b.text == "📱 TikTok")
    assert tiktok_btn.url == "https://tiktok.com/@x"

    assert len(all_buttons) == 5  # watch + like + dislike + tiktok + youtube

    print("✓ _build_post_markup: correct mix of url= and callback_data= buttons, None when empty")


if __name__ == "__main__":
    check_toggle_fixed_button()
    check_buttons_menu_reflects_state()
    check_status_text()
    check_build_post_markup()
    print("\nAll post-to-channel checks passed.")
