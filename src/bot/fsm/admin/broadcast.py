from aiogram.fsm.state import State, StatesGroup

class BroadcastStates(StatesGroup):
    selecting_audience = State()   # All / VIP only
    composing_content  = State()   # text / photo / video
    adding_buttons     = State()   # optional Like / Share buttons
    confirming         = State()   # preview + confirm
