"""Offline meter-source checks. Run: python3 -m unittest tools.test_meter_sources."""
import copy
import importlib
import json
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest import mock

from antelope import cli
from antelope import protocol
from antelope import transport


def load_server_without_web_or_hid_boundaries():
    class FakeFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda function: function

        post = get

        def mount(self, *args, **kwargs):
            return None

    fastapi = types.ModuleType('fastapi')
    fastapi.FastAPI = FakeFastAPI
    responses = types.ModuleType('fastapi.responses')
    responses.FileResponse = object
    responses.JSONResponse = object
    responses.StreamingResponse = object
    staticfiles = types.ModuleType('fastapi.staticfiles')
    class FakeStaticFiles:
        def __init__(self, *args, **kwargs):
            pass
    staticfiles.StaticFiles = FakeStaticFiles
    pydantic = types.ModuleType('pydantic')
    pydantic.BaseModel = object
    uvicorn = types.ModuleType('uvicorn')
    with mock.patch.dict(sys.modules, {
        'fastapi': fastapi,
        'fastapi.responses': responses,
        'fastapi.staticfiles': staticfiles,
        'pydantic': pydantic,
        'uvicorn': uvicorn,
    }), mock.patch.object(transport, 'list_connected_hid', return_value=set()):
        return importlib.import_module('webui.server')


class MeterSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'profiles/orion_studio_sc.json'
        cls.profile = json.loads(path.read_text())
        zen_path = Path(__file__).resolve().parents[1] / 'profiles/zen_go_sc.json'
        cls.zen_profile = json.loads(zen_path.read_text())
        cls.server = load_server_without_web_or_hid_boundaries()

    def test_orion_state_bank_preserves_raw_endpoints_without_meter_report_calibration(self):
        source, magic, base = protocol.channel_meter_source_details(self.profile)
        self.assertEqual((source, magic, base), ('state_report', 0x73, 221))

        report = bytearray(233)
        report[221] = 0
        report[232] = 96
        self.assertEqual(protocol.parse_channel_meter(self.profile, report, 0, base), 0)
        self.assertEqual(protocol.parse_channel_meter(self.profile, report, 11, base), 96)
        self.assertIsNone(protocol.raw_to_db(self.profile, 0, source))
        self.assertIsNone(protocol.meter_led(self.profile, None, source))
        self.assertEqual(cli._meter_bar(0, self.profile, source_frame=source), '########')
        self.assertEqual(cli._meter_bar(96, self.profile, source_frame=source), '........')

    def test_web_samples_keep_channel_one_activity_and_channel_twelve_silence_uncalibrated(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.profile
        device.n_ch = 12
        report = bytearray(233)
        report[221] = 0
        report[232] = 96

        samples = device._parse_meters(report)
        self.assertEqual(len(samples), 12)
        self.assertEqual(samples[0], {
            'raw': 0, 'db': None, 'clip': None, 'silence': False,
        })
        self.assertEqual(samples[11], {
            'raw': 96, 'db': None, 'clip': None, 'silence': True,
        })

    def test_orion_state_bank_truncation_does_not_invent_channel_twelve(self):
        _, _, base = protocol.channel_meter_source_details(self.profile)
        report = bytearray(232)
        report[221] = 48
        self.assertEqual(protocol.parse_channel_meter(self.profile, report, 0, base), 48)
        with self.assertRaisesRegex(ValueError, 'channel 11'):
            protocol.parse_channel_meter(self.profile, report, 11, base)

        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.profile
        device.n_ch = 12
        self.assertEqual(len(device._parse_meters(report)), 11)

    def test_webui_structured_readbacks_only_schedule_safe_outer_indices(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.profile
        device.structured = {
            (0x0b, 0): [{'record_index': 0, 'raw': b'\x01', 'linked': 1}],
            (0x16, 0): [{'record_index': 0, 'raw': b'\x00\x02\x00\x04',
                         'target': 0, 'emu_model': 2, 'ch_swap': 0,
                         'pattern': 4}],
        }
        device._lock = threading.Lock()
        payload = device.structured_readbacks_json()
        by_name = {layout['name']: layout for layout in payload['layouts']}
        self.assertEqual(by_name['preamps']['current']['0'][0]['linked'], 1)
        self.assertEqual(by_name['preamps']['current']['0'][0]['raw'], '01')
        self.assertFalse(by_name['available']['safe'])
        self.assertTrue(by_name['available']['capture_required'])
        targets = set(self.server._structured_readback_targets(self.profile))
        self.assertIn((0x0b, 0), targets)
        self.assertIn((0x19, 63), targets)
        self.assertNotIn((0x0c, 0), targets)

    def test_meter_report_source_keeps_existing_curve_and_clip_behavior(self):
        profile = copy.deepcopy(self.profile)
        profile['frame']['state_report'].pop('channel_meter_base_offset')
        source, magic, base = protocol.channel_meter_source_details(profile)
        self.assertEqual((source, magic, base), ('meter_report', 0x75, 32))
        self.assertEqual(protocol.raw_to_db(profile, 0, source), 0.0)
        self.assertEqual(protocol.raw_to_db(profile, 96, source), -60.0)
        self.assertIn('CLIP', cli._meter_bar(0, profile, source_frame=source))
        self.assertNotIn('CLIP', cli._meter_bar(96, profile, source_frame=source))

    def test_zen_go_surface_selected_mixer_strip_meters(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.zen_profile
        report = bytearray(320)
        report[122] = 0x0f              # Monitor / HP1 surface, Mix 1
        report[158] = 0
        report[159] = 24
        report[173] = 96

        meters = device._parse_mixer_meters(report)
        self.assertEqual(meters['mix'], 0)
        self.assertEqual(meters['selector'], 0x0f)
        self.assertEqual(meters['raw_range'], [0, 96])
        self.assertEqual(len(meters['strips']), 16)
        self.assertEqual(meters['strips'][0], {'ch': 0, 'raw': 0, 'silence': False})
        self.assertEqual(meters['strips'][1], {'ch': 1, 'raw': 24, 'silence': False})
        self.assertEqual(meters['strips'][-1], {'ch': 15, 'raw': 96, 'silence': True})

        report[122] = 0x0c              # HP2 surface, Mix 2
        self.assertEqual(device._parse_mixer_meters(report)['mix'], 1)

    def test_zen_go_surface_selector_uses_profile_command(self):
        packet, value, target = self.server._mixer_surface_packet(self.zen_profile, 1)
        self.assertEqual((value, target), (0x0c, 0))
        self.assertEqual(packet[0], 0x70)
        self.assertEqual(packet[4], 0x13)
        self.assertEqual(packet[16:19], bytes((0x49, 0, 0x0c)))
        self.assertIsNone(self.server._mixer_surface_packet(self.zen_profile, 2))


if __name__ == '__main__':
    unittest.main()
