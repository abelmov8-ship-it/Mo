from aiogram.fsm.state import State, StatesGroup


class TextEditStates(StatesGroup):
    entering_value = State()  # key/lang being edited live in FSM data, not a separate state each
