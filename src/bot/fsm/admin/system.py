from aiogram.fsm.state import State, StatesGroup

class AdminTextInputStates(StatesGroup):
    """Single-text-prompt admin flows that don't need a multi-step wizard."""
    entering_support_username = State()   # 🌐 Link Settings
