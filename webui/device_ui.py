"""Profile-declared launcher features.

Profiles own labels and feature declarations so another client (including a
future Rust launcher) can use the same device vocabulary.  This module only
derives runtime-safe presentation data, such as whether a declared feature's
readback bounds are currently usable.  The small legacy registry remains as a
compatibility fallback for third-party profiles that predate the manifest.
"""
from copy import deepcopy
from pathlib import Path

from antelope import protocol as proto


def _source_options(profile):
    """Build mixer-source options from the active profile.

    The values in these options are the actual (source bank, source index)
    tuples written by SET_ROUTE.  Both the mapping and the display label come
    from the selected profile; no product-specific source-name table belongs
    here.
    """
    options = []

    for group in proto.route_source_options(profile):
        kind = group["kind"]
        label = group.get("label", kind)
        if kind == "mute":
            bank, index = proto.resolve_route_source(profile, kind, None)
            options.append({"key": "mute:0", "label": label,
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


_LEGACY_FEATURES = {
    "zen_go_sc": {
        "routing": {
            "enabled": True,
            "destinations": [
                {
                    "id": 6,
                    "name": "mixer_input_assignments",
                    "channels": 16,
                    "write_destinations": [6, 7, 8, 9],
                    "note": (
                        "The four Zen Go routing records are mirrored views of "
                        "one 16-strip mixer input map."
                    ),
                },
            ],
        },
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
    if stem in _LEGACY_FEATURES:
        return stem
    name = str(profile.get("device", {}).get("name", "")).lower()
    if "zen go" in name:
        return "zen_go_sc"
    if "orion studio" in name:
        return "orion_studio_sc"
    return stem


def features_for(profile_path, profile):
    """Return profile-declared features with safe runtime availability added."""
    key = _profile_key(profile_path, profile)
    declared = profile.get("features")
    features = deepcopy(declared if isinstance(declared, dict)
                        else _LEGACY_FEATURES.get(key, {}))
    frame = profile.get("frame", {})
    if "routing" in features and isinstance(features["routing"], dict):
        feature = features["routing"]
        routing = frame.get("routing_command", {})
        destination_channels = routing.get("destination_channels", {})
        visible = []
        for item in feature.get("destinations", []) or []:
            try:
                dest = int(item["id"])
                channels = int(item.get("channels", item.get("channel_count")))
                writes = [int(value) for value in item.get(
                    "write_destinations", [dest])]
            except (KeyError, TypeError, ValueError):
                continue
            if str(dest) not in destination_channels or channels <= 0:
                continue
            if channels > int(destination_channels[str(dest)]):
                continue
            if any(str(value) not in destination_channels for value in writes):
                continue
            visible.append({**item, "id": dest, "channels": channels,
                            "write_destinations": writes})
        feature["destinations"] = visible
        if feature.get("enabled", True) and visible:
            feature["writable"] = all(
                proto.readback_indices_available(
                    profile, proto.ROUTING_READBACK_CATEGORY,
                    item["write_destinations"])
                for item in visible)
        else:
            feature["writable"] = False
        if not feature["writable"] and visible:
            feature.setdefault("note", (
                "Routing assignments are displayed read-only until their "
                "safe readback is confirmed."))
    if "mixer_sources" in features and isinstance(features["mixer_sources"], dict):
        feature = features["mixer_sources"]
        feature["options"] = _source_options(profile)
        routing = frame.get("routing_command", {})
        try:
            destinations = [int(d) for d in feature.get(
                "routing_destinations", []) or []]
            channel_count = int(feature.get(
                "channels", feature.get("channel_count")))
        except (TypeError, ValueError):
            destinations = []
            channel_count = 0
        destination_channels = routing.get("destination_channels", {})
        feature["writable"] = bool(
            feature.get("enabled", True)
            and destinations
            and channel_count > 0
            and proto.readback_indices_available(
                profile, proto.ROUTING_READBACK_CATEGORY, destinations)
            and all(str(d) in destination_channels
                    and int(destination_channels[str(d)]) >= channel_count
                    for d in destinations))
        if not feature["writable"]:
            feature.setdefault("note", (
                "Mixer source routing is displayed read-only until its safe "
                "routing readback is confirmed."))
    auraverb = features.get("auraverb")
    if (proto.auraverb_readback_available(profile)
            and (not isinstance(auraverb, dict)
                 or auraverb.get("enabled", True))):
        command = frame.get("auraverb_command", {})
        contract = command.get("contract", {})
        feature = auraverb if isinstance(auraverb, dict) else {}
        features["auraverb"] = feature
        feature.update({
            "enabled": True,
            "kind": feature.get("kind", "bundled_effect"),
            "mix": proto._as_int(contract.get("target", 0)),
            "label": feature.get("label", "Gazelle Reverb"),
        })
    elif isinstance(features.get("auraverb"), dict):
        features["auraverb"]["enabled"] = False
    if "mixer_sources" in features and not frame.get("routing_command"):
        features["mixer_sources"]["enabled"] = False
        features["mixer_sources"]["writable"] = False
    return {"profile": key, **features}
