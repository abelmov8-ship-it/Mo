from aiogram.fsm.state import State, StatesGroup

class PhotoEditorStates(StatesGroup):
    selecting_tool  = State()   # resize / rotate / text / frame / collage
    awaiting_image  = State()   # waiting for photo upload
    selecting_size  = State()   # A-series / B-series / custom
    entering_custom_size = State()   # free-form WIDTHxHEIGHT text entry
    selecting_rotation   = State()   # rotate/flip direction picker
    entering_text   = State()   # overlay text input
    selecting_frame = State()   # frame style picker
    collecting_collage      = State()  # accumulating photos for a collage
    selecting_collage_layout = State()  # column count picker before rendering
    preview         = State()   # confirm or re-edit
