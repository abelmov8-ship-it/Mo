from aiogram.fsm.state import State, StatesGroup


class MenuWizardStates(StatesGroup):
    selecting_action = State()        # step 1: what the button does
    selecting_keyboard_type = State() # step 2: reply or inline
    entering_label = State()          # step 3: display text (also reused for standalone label edits)
