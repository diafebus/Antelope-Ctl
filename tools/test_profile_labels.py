"""Offline profile-label contract checks.

Run with: ``python3 -m unittest tools.test_profile_labels``
"""
import copy
import json
from pathlib import Path
import unittest

from antelope import protocol
from webui import device_ui


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATHS = sorted((ROOT / "profiles").glob("*_sc.json"))

SHARED_PARAM_LABELS = {
    "gain": "Gain",
    "input_mode": "Input Mode",
    "phantom": "48V Phantom",
    "phase_invert": "Phase Invert",
    "channel_link": "Input Link",
    "bus_level": "Output Level",
    "bus_mute": "Mute",
    "bus_dim": "Dim",
    "bus_mono": "Mono",
    "mix_channel_link": "Mixer Link",
}


class ProfileLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = {
            path.stem: (path, json.loads(path.read_text()))
            for path in PROFILE_PATHS
        }

    def test_every_device_profile_has_the_versioned_label_contract(self):
        self.assertGreaterEqual(len(self.profiles), 1)
        for name, (_path, profile) in self.profiles.items():
            with self.subTest(profile=name):
                schema = profile.get("profile_schema")
                self.assertEqual(schema, {
                    "id": "antelope-device-profile",
                    "version": 1,
                })
                labels = profile.get("labels")
                self.assertIsInstance(labels, dict)
                for namespace in ("sections", "spaces", "params"):
                    self.assertIsInstance(labels.get(namespace), dict)
                features = profile.get("features")
                self.assertIsInstance(features, dict)
                for feature_id, feature in features.items():
                    with self.subTest(feature=feature_id):
                        self.assertIsInstance(feature, dict)
                        self.assertIsInstance(feature.get("kind"), str)
                        self.assertIsInstance(feature.get("label"), str)
                        self.assertIsInstance(feature.get("enabled"), bool)
                        if "controls" in feature:
                            self.assertIsInstance(feature["controls"], list)

    def test_shared_parameter_labels_do_not_drift(self):
        for name, (_path, profile) in self.profiles.items():
            params = profile.get("params", {})
            labels = profile["labels"]["params"]
            for param, expected in SHARED_PARAM_LABELS.items():
                if param in params:
                    with self.subTest(profile=name, param=param):
                        self.assertEqual(labels.get(param), expected)

    def test_entity_labels_are_present_when_the_entity_is_declared(self):
        for name, (_path, profile) in self.profiles.items():
            for bus_id, bus in (profile.get("buses", {}).get("known", {}) or {}).items():
                with self.subTest(profile=name, bus=bus_id):
                    self.assertIsInstance(bus, dict)
                    self.assertTrue(bus.get("name"))
                    self.assertTrue(bus.get("label"))

            routing = profile.get("frame", {}).get("routing_command", {}) or {}
            semantics = routing.get("source_semantics", {}) or {}
            for bank, source in semantics.items():
                with self.subTest(profile=name, source_bank=bank):
                    self.assertIsInstance(source, dict)
                    self.assertTrue(source.get("key"))
                    self.assertTrue(source.get("label"))

            destinations = routing.get("addressable_destinations", {}) or {}
            if destinations:
                labels = routing.get("destination_labels", {}) or {}
                for dest_id in destinations:
                    with self.subTest(profile=name, destination=dest_id):
                        self.assertTrue(labels.get(str(dest_id)))

    def test_protocol_helpers_prefer_profile_labels(self):
        orion = self.profiles["orion_studio_sc"][1]
        self.assertEqual(protocol.bus_key(orion, 0), "monitor_a")
        self.assertEqual(protocol.bus_name(orion, 0), "Monitor A")
        self.assertEqual(protocol.resolve_bus_id(orion, "Monitor A"), 0)
        self.assertEqual(protocol.route_source_key(orion, 0, 2), "preamp:3")
        self.assertEqual(protocol.route_source_label(orion, 0, 2), "PREAMP 3")
        self.assertEqual(protocol.route_destination_label(orion, 0), "Line Out")
        self.assertEqual(protocol.resolve_route_dest(orion, "Monitor A"), 3)

        zen = self.profiles["zen_go_sc"][1]
        options = protocol.route_source_options(zen)
        labels = {option["kind"]: option["label"] for option in options}
        self.assertEqual(labels["compplay"], "COMPUTER PLAY")
        self.assertEqual(protocol.route_destination_label(zen, 6), "Mixer Input Map 1")

    def test_runtime_feature_derivation_preserves_profile_labels(self):
        path, zen = self.profiles["zen_go_sc"]
        profile = copy.deepcopy(zen)
        profile["features"]["routing"]["label"] = "Custom Routing"
        features = device_ui.features_for(str(path), profile)
        self.assertEqual(features["routing"]["label"], "Custom Routing")
        self.assertEqual(features["routing"]["destinations"][0]["label"],
                         "Mixer Input Assignments")
        self.assertEqual(features["mixer_sources"]["options"][0]["label"],
                         "PREAMP 1")


if __name__ == "__main__":
    unittest.main()
