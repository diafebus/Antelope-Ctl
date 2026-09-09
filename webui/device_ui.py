"""Presentation-only device UI features.

Protocol profiles remain the source of truth for wire layouts and safety
constraints. This small registry describes panels that belong to a product's
interface rather than to its protocol, so a device-specific panel can be
added without changing another device's layout.
"""
from copy import deepcopy
from pathlib import Path

from antelope import protocol as proto


def _zen_source_options(profile):
    """Build Zen Go mixer-source options from the active profile.

    The values in these options are the actual (source bank, source index)
    tuples written by SET_ROUTE.  Keeping the mapping here profile-driven is
    important: the Zen Go uses different bank numbers from the Orion.
    """
    options = []

    labels = {
        "preamp": "PREAMP",
        "compplay": "COMPUTER PLAY",
        "spdif": "S/PDIF",
        "osc": "OSCILLATOR",
        "emumic": "EMUMIC",
    }
    for group in proto.route_source_options(profile):
        kind = group["kind"]
        label = labels.get(kind, group.get("label", kind))
        if kind == "mute":
            bank, index = proto.resolve_route_source(profile, kind, None)
            options.append({"key": "mute:0", "label": "MUTE",
                            "bank": bank, "index": index})
        elif group.get("stereo"):
            for side in ("L", "R"):
                bank, index = proto.resolve_route_source(profile, kind, side)
                options.append({"key": f"{kind}:{side}",
                                "label": f"{label} {side}",
                                "bank": bank, "index": index})
        else:
            base = int(group.get("base") or 0)
            for number in range(base, base + int(group["count"])):
                bank, index = proto.resolve_route_source(profile, kind, number)
                options.append({"key": f"{kind}:{number}",
                                "label": f"{label} {number}",
                                "bank": bank, "index": index})
    return options


_FEATURES = {
    "zen_go_sc": {
        "mixer_sources": {
            "enabled": True,
            "mixes": [0, 1],
            "channels": 16,
            "options": [],
            "writable": False,
            "routing_destinations": [6, 7, 8, 9],
            "note": "Zen Go source changes update the shared mixer input map.",
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
    if key == "zen_go_sc" and "mixer_sources" in features:
        feature = features["mixer_sources"]
        feature["options"] = _zen_source_options(profile)
        routing = frame.get("routing_command", {})
        destinations = [int(d) for d in feature.get("routing_destinations", [])]
        destination_channels = routing.get("destination_channels", {})
        feature["writable"] = bool(
            destinations
            and proto.readback_indices_available(
                profile, proto.ROUTING_READBACK_CATEGORY, destinations)
            and all(str(d) in destination_channels
                    and int(destination_channels[str(d)]) >= feature["channels"]
                    for d in destinations))
        if not feature["writable"]:
            feature["note"] = (
                "Zen Go source routing is displayed read-only until its "
                "safe routing readback is confirmed.")
    if proto.auraverb_readback_available(profile):
        command = frame.get("auraverb_command", {})
        contract = command.get("contract", {})
        features["auraverb"] = {
            "enabled": True,
            "mix": proto._as_int(contract.get("target", 0)),
            "label": "Gazelle Reverb",
        }
    else:
        features.pop("auraverb", None)
    if "mixer_sources" in features and not frame.get("routing_command"):
        features.pop("mixer_sources")
    return {"profile": key, **features}
