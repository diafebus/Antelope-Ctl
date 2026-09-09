"""Presentation-only device UI features.

Protocol profiles remain the source of truth for wire layouts and safety
constraints. This small registry describes panels that belong to a product's
interface rather than to its protocol, so a device-specific panel can be
added without changing another device's layout.
"""
from copy import deepcopy
from pathlib import Path


def _zen_source_options():
    """Build the source labels shown by the Zen Go mixer selectors.

    The Zen Go routing command is a whole-group write and its readback is not
    safely mapped yet, so the WebUI exposes these selectors read-only for now.
    """
    options = []

    def numbered(key, label, bank, count):
        for index in range(count):
            number = index + 1
            options.append({
                "key": f"{key}:{number}",
                "label": f"{label} {number}",
                "bank": bank,
                "index": index,
            })

    numbered("preamp", "PREAMP", 0x00, 2)
    numbered("compplay", "COMPUTER PLAY", 0x01, 8)
    options.extend([
        {"key": "spdif:L", "label": "S/PDIF L", "bank": 0x02, "index": 0},
        {"key": "spdif:R", "label": "S/PDIF R", "bank": 0x02, "index": 1},
    ])
    numbered("osc", "OSCILLATOR", 0x09, 2)
    numbered("emumic", "EMUMIC", 0x0a, 2)
    options.append({"key": "mute:0", "label": "MUTE", "bank": 0x08, "index": 0})
    return options


_FEATURES = {
    "zen_go_sc": {
        "mixer_sources": {
            "enabled": True,
            "mixes": [0, 1],
            "channels": 16,
            "options": _zen_source_options(),
            "writable": False,
            "note": "Zen Go source routing is displayed read-only until its safe routing readback is confirmed.",
        },
    },
    "orion_studio_sc": {
        "auraverb": {
            "enabled": True,
            "mix": 0,
            "label": "AuraVerb",
        },
    },
}


def _profile_key(profile_path, profile):
    stem = Path(profile_path).stem.lower()
    if stem in _FEATURES:
        return stem
    name = str(profile.get("device", {}).get("name", "")).lower()
    if "zen go" in name:
        return "zen_go_sc"
    if "orion studio" in name:
        return "orion_studio_sc"
    return stem


def features_for(profile_path, profile):
    """Return a copy of presentation features for the active profile."""
    key = _profile_key(profile_path, profile)
    features = deepcopy(_FEATURES.get(key, {}))
    frame = profile.get("frame", {})
    if "auraverb" in features and not frame.get("auraverb_command"):
        features.pop("auraverb")
    if "mixer_sources" in features and not frame.get("routing_command"):
        features.pop("mixer_sources")
    return {"profile": key, **features}
