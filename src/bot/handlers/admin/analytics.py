from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.search_log import SearchLog, SearchLogKind
from bot.filters.is_admin import IsAdmin
from bot.keyboards.admin.analytics import analytics_menu_keyboard
from bot.services.movie_service import MovieService
from bot.services.user_service import UserService
from bot.utils.formatters import format_analytics

router = Router(name="admin:analytics")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(F.text == "📊 Analytics")
async def show_analytics(message: Message, session: AsyncSession) -> None:
    user_svc = UserService(session)

    total = await user_svc.count_total()
    vip   = await user_svc.count_vip()
    today = await user_svc.count_active_today()

    from bot.database.models.payment import Payment, PaymentStatus
    from sqlalchemy import func
    pending_result = await session.execute(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.PENDING)
    )
    pending = pending_result.scalar_one()

    await message.answer(format_analytics(total, vip, today, pending), reply_markup=analytics_menu_keyboard())


@router.message(F.text == "🔗 Broken Links")
async def show_broken_links(message: Message, session: AsyncSession) -> None:
    movie_svc = MovieService(session)
    broken = await movie_svc.get_broken()
    if not broken:
        await message.answer("✅ No broken links reported.")
        return

    lines = [f"⚠️ <b>Broken Links Queue</b> ({len(broken)} items)\n"]
    for m in broken[:20]:
        lines.append(f"• ID <code>{m.id}</code> — {m.title}")
    await message.answer("\n".join(lines))


@router.message(F.text == "📣 Search Log")
async def show_search_log(message: Message, session: AsyncSession) -> None:
    misses = await session.execute(
        select(SearchLog)
        .where(SearchLog.kind == SearchLogKind.MISS)
        .order_by(SearchLog.created_at.desc())
        .limit(15)
    )
    requests = await session.execute(
        select(SearchLog)
        .where(SearchLog.kind == SearchLogKind.REQUEST)
        .where(SearchLog.notified.is_(False))
        .order_by(SearchLog.created_at.desc())
        .limit(15)
    )
    miss_rows = list(misses.scalars().all())
    request_rows = list(requests.scalars().all())

    lines = [f"📣 <b>Open Requests</b> ({len(request_rows)})"]
    lines += [f"• {r.query}" for r in request_rows] or ["  (none)"]
    lines.append(f"\n🔍 <b>Recent Zero-Result Searches</b> ({len(miss_rows)})")
    lines += [f"• {m.query}" for m in miss_rows] or ["  (none)"]
    await message.answer("\n".join(lines))


