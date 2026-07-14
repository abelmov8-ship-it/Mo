from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models.user import UserLanguage
from bot.keyboards.user.payment import ppv_unlock_keyboard
from bot.services.movie_service import MovieService
from bot.services.promo_service import PromoService
from bot.services.user_service import UserService
from bot.services.wallet_service import WalletService
from bot.services.watchlist_service import WatchlistService
from bot.utils.i18n import t
from bot.utils.movie_delivery import build_delivered_movie_keyboard, deliver_movie

router = Router(name="user:wallet")


@router.message(Command("redeem"))
async def redeem_promo(
    message: Message, command: CommandObject, session: AsyncSession,
    locale: UserLanguage = UserLanguage.EN,
) -> None:
    if not command.args:
        await message.answer(t("wallet.redeem_usage", locale))
        return

    user_svc = UserService(session)
    user = await user_svc.get_by_telegram_id(message.from_user.id)
    if not user:
        await message.answer(t("wallet.start_first", locale))
        return

    _ok, result_msg = await PromoService(session).redeem(command.args, user)
    await message.answer(result_msg)


@router.callback_query(F.data.startswith("ppv_unlock:"))
async def unlock_ppv(callback: CallbackQuery, session: AsyncSession, locale: UserLanguage = UserLanguage.EN) -> None:
    movie_id = int(callback.data.split(":")[1])

    user_svc = UserService(session)
    movie_svc = MovieService(session)
    wallet_svc = WalletService(session)

    user = await user_svc.get_by_telegram_id(callback.from_user.id)
    movie = await movie_svc.get_by_id(movie_id)

    if not user or not movie:
        await callback.answer(t("wallet.error_loading", locale), show_alert=True)
        return

    lang = user.language
    if not wallet_svc.can_afford(user, movie.ppv_price):
        # ponytail: this only fires on the stale-keyboard race (balance spent
        # elsewhere between message-send and tap) since the Unlock button
        # itself is only ever shown when wallet_ok was true — refresh the
        # keyboard to the correct top-up/VIP state rather than leaving a
        # dead-end alert with no way forward.
        await callback.answer(
            t("wallet.insufficient_balance", lang, price=f"{movie.ppv_price:.0f}"),
            show_alert=True,
        )
        await callback.message.edit_reply_markup(
            reply_markup=ppv_unlock_keyboard(movie.id, movie.ppv_price, wallet_ok=False, locale=lang)
        )
        return

    success, new_balance, _payment = await wallet_svc.deduct(user, movie.ppv_price)
    if not success:
        await callback.answer(t("wallet.deduction_failed", lang), show_alert=True)
        return

    await movie_svc.increment_view(movie_id)
    await callback.answer(t("wallet.unlocked_toast", lang, balance=f"{new_balance:.2f}"), show_alert=True)
    in_watchlist = await WatchlistService(session).is_in_watchlist(user.id, movie.id)
    await deliver_movie(
        callback.message, movie,
        reply_markup=await build_delivered_movie_keyboard(session, movie.id, in_watchlist, lang),
        caption=t("wallet.unlocked_caption", lang, title=movie.title),
    )
