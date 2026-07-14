from aiogram.fsm.state import State, StatesGroup


class TrendingAdminStates(StatesGroup):
    awaiting_poster_forward = State()  # admin forwards a photo from a designated source channel
