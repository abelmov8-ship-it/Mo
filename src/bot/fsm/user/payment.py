from aiogram.fsm.state import State, StatesGroup

class PaymentStates(StatesGroup):
    selecting_method      = State()   # Chapa / Bank / Wallet
    selecting_plan        = State()   # VIP duration picker
    entering_topup_amount = State()   # custom wallet top-up amount
    awaiting_receipt       = State()   # user uploads screenshot
    pending_approval       = State()   # waiting for admin
