"""Small per-user preferences (USER_DIR/preferences.json): remembered UI state, active colour profile."""
import json
import logging

from PathManager import USER_DIR

log = logging.getLogger(__name__)

PREFERENCES_FILE = USER_DIR / "preferences.json"


def get(key, default=None):
    try:
        return json.loads(PREFERENCES_FILE.read_text(encoding="utf-8")).get(key, default)
    except (OSError, ValueError):
        return default


def put(key, value):
    try:
        prefs = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prefs = {}
    prefs[key] = value
    try:
        PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("Could not save preferences: %s", e)
