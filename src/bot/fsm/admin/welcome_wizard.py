from aiogram.fsm.state import State, StatesGroup


class WelcomeButtonStates(StatesGroup):
    entering_label = State()  # add-wizard step 1; also reused for standalone "Edit Label"
    entering_url   = State()  # add-wizard step 2; also reused for standalone "Edit URL"
