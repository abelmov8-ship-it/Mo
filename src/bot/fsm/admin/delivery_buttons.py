from aiogram.fsm.state import State, StatesGroup


class DeliveryButtonStates(StatesGroup):
    renaming_default_slot  = State()  # rename one of the 4 fixed default slots
    entering_custom_label  = State()  # custom file button: add/edit label
    entering_custom_url    = State()  # custom file button: add/edit URL
    entering_backup_label  = State()  # backup channel link: add/edit label
    entering_backup_url    = State()  # backup channel link: add/edit URL
