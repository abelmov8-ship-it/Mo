from aiogram.fsm.state import State, StatesGroup

class SupportStates(StatesGroup):
    composing_message = State()   # writing the support ticket
    awaiting_reply    = State()   # open ticket, waiting for admin reply
