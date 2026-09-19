"""Constants for the Roborock Rooms integration."""

DOMAIN = "roborock_rooms"

CONF_USER_DATA = "user_data"
CONF_SCAN_INTERVAL_MINUTES = "scan_interval_minutes"

DATA_COORDINATORS = "coordinators"
DATA_ROOM_SETTINGS = "room_settings"
DATA_ACTIVE_QUEUES = "active_queues"

DEFAULT_SCAN_INTERVAL_MINUTES = 30
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 180

CONSECUTIVE_FAILURES_BEFORE_REPAIR = 3

SERVICE_CLEAN_ROOMS = "clean_rooms"
ATTR_DEVICE_ID = "device_id"
ATTR_SEGMENTS = "segments"
ATTR_REPEAT = "repeat"
ATTR_USE_ROOM_SETTINGS = "use_room_settings"

SERVICE_RUN_ROUTINE = "run_routine"
ATTR_ROUTINE_ID = "routine_id"

# When rooms have different settings they are cleaned one group at a time; these
# control how the integration waits for the vacuum to finish a group.
QUEUE_POLL_SECONDS = 20
QUEUE_START_GRACE_SECONDS = 120
QUEUE_GROUP_TIMEOUT_SECONDS = 4 * 60 * 60
