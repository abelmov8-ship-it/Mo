from aiogram.fsm.state import State, StatesGroup

class AdminPaymentStates(StatesGroup):
    adding_bank_name    = State()
    adding_bank_account = State()
    adding_bank_holder  = State()
    editing_bank        = State()
    updating_chapa_key  = State()
    updating_chapa_webhook_secret = State()
    updating_price      = State()
