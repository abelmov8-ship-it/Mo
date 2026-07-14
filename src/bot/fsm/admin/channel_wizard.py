from aiogram.fsm.state import State, StatesGroup

class ChannelWizardStates(StatesGroup):
    selecting_category = State()   # Free / VIP
    selecting_status   = State()   # Force Join ON / OFF
    entering_name      = State()   # display name
    entering_url       = State()   # invite link or @username
    entering_channel_id = State()  # numeric Telegram ID
    entering_custom_price = State()  # per-channel PPV price override (edit-only, no create-wizard step)
