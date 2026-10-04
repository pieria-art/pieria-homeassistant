"""Constants for the Pieria integration."""

from __future__ import annotations

DOMAIN = "pieria"

CONF_TOKEN = "token"

DEFAULT_PORT = 8000
DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
CONF_SCAN_INTERVAL = "scan_interval"

PLAYLIST_REFRESH_SECONDS = 300

RENDER_MODES = ["ken-burns", "static-crop", "contain-matte"]
KIND_CANVAS = "canvas"

KIND_EINK = "eink"
KIND_FRAME = "frame"
NON_NAVIGABLE_KINDS = (KIND_EINK, KIND_FRAME)

QUIET_MODES = ["auto", "on", "off"]
FEATURE_PAUSE = "pause"
FEATURE_SHOW = "show"
FEATURE_QUIET = "quiet"
OPTIMISTIC_TTL = 10
