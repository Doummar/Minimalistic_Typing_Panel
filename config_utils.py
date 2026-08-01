"""Config loading, validation, and coercion.

Anki hands back whatever is on disk in config.json with no guarantees about
shape -- a hand edit, a stale version from before an upgrade, or a corrupted
write can all leave keys missing or holding the wrong type. Every read goes
through get_config() so the rest of the addon can trust conf[key] is always
present and of the expected type, instead of every call site needing its own
defensive .get() / try-except.
"""
from copy import deepcopy

from aqt import mw

from .consts import ADDON_ID, DEFAULT_CONFIG

_EXPECTED_TYPES = {key: type(value) for key, value in DEFAULT_CONFIG.items()}


def get_config() -> dict:
    raw = mw.addonManager.getConfig(ADDON_ID) or {}
    conf = deepcopy(DEFAULT_CONFIG)

    for key, expected in _EXPECTED_TYPES.items():
        if key not in raw:
            continue
        value = raw[key]

        if expected is bool:
            if isinstance(value, bool):
                conf[key] = value
        elif expected in (int, float):
            # bool is a subclass of int; reject it explicitly so a stray
            # `true`/`false` doesn't get silently coerced into 1/0.
            if isinstance(value, bool):
                continue
            try:
                conf[key] = expected(value)
            except (TypeError, ValueError):
                pass
        elif expected is str:
            if isinstance(value, str):
                conf[key] = value
        elif expected is dict:
            if isinstance(value, dict):
                conf[key] = value
        elif expected is list:
            # e.g. passthrough_shortcuts: keep only string entries, so a
            # hand-edited or corrupted config.json can't hand the rest of
            # the addon a list containing non-string junk.
            if isinstance(value, list):
                conf[key] = [v for v in value if isinstance(v, str) and v]
        else:
            if isinstance(value, expected):
                conf[key] = value

    return conf


def write_config(conf: dict) -> None:
    mw.addonManager.writeConfig(ADDON_ID, conf)
