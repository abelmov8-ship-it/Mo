from aiogram.fsm.state import State, StatesGroup

class FileManagerStates(StatesGroup):
    awaiting_forward  = State()   # admin forwards movie files
    searching_file    = State()   # search by ID or title
    editing_title     = State()
    editing_link      = State()
    editing_price     = State()   # per-file PPV micro-price
    editing_default_price = State()   # global default applied to new batch uploads
    confirming_delete = State()

class UserManagementStates(StatesGroup):
    entering_user_id  = State()
    granting_vip_days = State()
    adjusting_wallet  = State()
    confirming_ban    = State()

class ContentDeployStates(StatesGroup):
    selecting_channel = State()
    uploading_media   = State()
    entering_caption  = State()
    adding_buttons    = State()
    entering_social_label = State()   # sub-flow of adding_buttons: custom URL button, step 1
    entering_social_url   = State()   # sub-flow of adding_buttons: custom URL button, step 2
    confirming        = State()
    entering_schedule_time = State()   # 📅 Post Scheduling — when to fire
