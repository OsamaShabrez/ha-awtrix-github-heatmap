from __future__ import annotations

DOMAIN = "github_heatmap"

CONF_USERNAME = "username"
CONF_DEVICE_ID = "device_id"
CONF_REFRESH = "refresh"
CONF_ENABLED = "enabled"

DEFAULT_REFRESH = 60
DEFAULT_ENABLED = True

API_URL = (
    "https://github-contributions-api.jogruber.de/v4/"
    "{username}?y=last"
)

GITHUB_USER_API = (
    "https://api.github.com/users/{username}"
)

APP_NAME = "github_heatmap"

PANEL_W = 32
PANEL_H = 8

# Avatar is intentionally enabled permanently.
AVATAR_CACHE_HOURS = 24

API_RETRIES = 3
MQTT_RETRIES = 3
MQTT_RETRY_DELAY = 2

SERVICE_REFRESH = "refresh"
