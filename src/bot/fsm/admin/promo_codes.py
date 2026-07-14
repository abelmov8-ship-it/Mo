from aiogram.fsm.state import State, StatesGroup

class PromoCodeStates(StatesGroup):
    selecting_type = State()   # VIP Days / Wallet Credit
    entering_code  = State()   # the promo string
    entering_value = State()   # days or credit amount
    entering_limit = State()   # max redemptions (blank = unlimited)
    entering_expiry = State()  # expiry date (blank = never)
