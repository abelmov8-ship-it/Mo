from aiogram.fsm.state import State, StatesGroup


class FaqStates(StatesGroup):
    entering_question = State()  # add-wizard step 1; also reused for standalone "Edit Question"
    entering_answer   = State()  # add-wizard step 2; also reused for standalone "Edit Answer"
