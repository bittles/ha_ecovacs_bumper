#sucks constants
# These consts define all of the vocabulary used by this library when presenting various states and components.
# Applications implementing this library should import these rather than hard-code the strings, for future-proofing.

CLEAN_MODE_AUTO = 'auto'
CLEAN_MODE_EDGE = 'edge'
CLEAN_MODE_SPOT = 'spot'
CLEAN_MODE_SPOT_AREA = 'spot_area'
CLEAN_MODE_SINGLE_ROOM = 'single_room'
CLEAN_MODE_STOP = 'stop'

CLEAN_ACTION_START = 'start'
CLEAN_ACTION_PAUSE = 'pause'
CLEAN_ACTION_RESUME = 'resume'
CLEAN_ACTION_STOP = 'stop'

FAN_SPEED_NORMAL = 'normal'
FAN_SPEED_HIGH = 'high'

CHARGE_MODE_RETURN = 'return'
CHARGE_MODE_RETURNING = 'returning'
CHARGE_MODE_CHARGING = 'charging'
CHARGE_MODE_IDLE = 'idle'

COMPONENT_SIDE_BRUSH = 'side_brush'
COMPONENT_MAIN_BRUSH = 'main_brush'
COMPONENT_FILTER = 'filter'

VACUUM_STATUS_OFFLINE = 'offline'

CLEANING_STATES = {CLEAN_MODE_AUTO, CLEAN_MODE_EDGE, CLEAN_MODE_SPOT, CLEAN_MODE_SPOT_AREA, CLEAN_MODE_SINGLE_ROOM}
CHARGING_STATES = {CHARGE_MODE_CHARGING}

# These dictionaries convert to and from Sucks's consts (which closely match what the UI and manuals use)
# to and from what the Ecovacs API uses (which are sometimes very oddly named and have random capitalization.)
CLEAN_MODE_TO_ECOVACS = {
    CLEAN_MODE_AUTO: 'auto',
    CLEAN_MODE_EDGE: 'border',
    CLEAN_MODE_SPOT: 'spot',
    CLEAN_MODE_SPOT_AREA: 'SpotArea',
    CLEAN_MODE_SINGLE_ROOM: 'singleroom',
    CLEAN_MODE_STOP: 'stop'
}

CLEAN_ACTION_TO_ECOVACS = {
    CLEAN_ACTION_START: 's',
    CLEAN_ACTION_PAUSE: 'p',
    CLEAN_ACTION_RESUME: 'r',
    CLEAN_ACTION_STOP: 'h',
}

CLEAN_ACTION_FROM_ECOVACS = {
    's': CLEAN_ACTION_START,
    'p': CLEAN_ACTION_PAUSE,
    'r': CLEAN_ACTION_RESUME,
    'h': CLEAN_ACTION_STOP,
}

CLEAN_MODE_FROM_ECOVACS = {
    'auto': CLEAN_MODE_AUTO,
    'border': CLEAN_MODE_EDGE,
    'spot': CLEAN_MODE_SPOT,
    'spot_area': CLEAN_MODE_SPOT_AREA,
    'SpotArea': CLEAN_MODE_SPOT_AREA,
    'singleroom': CLEAN_MODE_SINGLE_ROOM,
    'stop': CLEAN_MODE_STOP,
    'going': CHARGE_MODE_RETURNING,
}

FAN_SPEED_TO_ECOVACS = {
    FAN_SPEED_NORMAL: 'standard',
    FAN_SPEED_HIGH: 'strong'
}

FAN_SPEED_FROM_ECOVACS = {
    'standard': FAN_SPEED_NORMAL,
    'strong': FAN_SPEED_HIGH,
}

CHARGE_MODE_TO_ECOVACS = {
    CHARGE_MODE_RETURN: 'go',
    CHARGE_MODE_RETURNING: 'Going',
    CHARGE_MODE_CHARGING: 'SlotCharging',
    CHARGE_MODE_IDLE: 'Idle',
}

CHARGE_MODE_FROM_ECOVACS = {
    'going': CHARGE_MODE_RETURNING,
#    'Going': CHARGE_MODE_RETURNING,
    'slot_charging': CHARGE_MODE_CHARGING,
#    'SlotCharging': CHARGE_MODE_CHARGING,
    'idle': CHARGE_MODE_IDLE,
#    'Idle': CHARGE_MODE_IDLE,
}

COMPONENT_TO_ECOVACS = {
    COMPONENT_MAIN_BRUSH: 'Brush',
    COMPONENT_SIDE_BRUSH: 'SideBrush',
    COMPONENT_FILTER: 'DustCaseHeap',
}

COMPONENT_FROM_ECOVACS = {
    'brush': COMPONENT_MAIN_BRUSH,
#    'Brush': COMPONENT_MAIN_BRUSH,
    'side_brush': COMPONENT_SIDE_BRUSH,
#    'SideBrush': COMPONENT_SIDE_BRUSH,
    'dust_case_heap': COMPONENT_FILTER,
#    'DustCaseHeap': COMPONENT_FILTER,
}