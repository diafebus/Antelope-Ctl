"""Offline meter-source checks. Run: python3 -m unittest tools.test_meter_sources."""
import copy
import importlib
import json
from pathlib import Path
import signal
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

    def test_orion_bus_silent_endpoint_marker_is_not_reported_as_definite_mute(self):
        report = bytearray(320)
        report[28] = 96
        report[29] = 0x04

        state = protocol.parse_bus_state(self.profile, report, 0)

        self.assertEqual(state['level'], 96)
        self.assertEqual(state['status_raw'], 0x04)
        self.assertFalse(state['mute'])
        self.assertTrue(state['mute_ambiguous'])

        report[28] = 95
        state = protocol.parse_bus_state(self.profile, report, 0)
        self.assertTrue(state['mute'])
        self.assertFalse(state['mute_ambiguous'])

    def test_orion_bus_level_endpoint_contract_is_attenuation(self):
        self.assertIn('level_encoding', self.profile['buses'])
        encoding = self.profile['buses']['level_encoding']
        self.assertIn('raw 0 = 0 dB maximum/unity', encoding)
        self.assertIn('raw 96 (0x60) = -inf/silent', encoding)
        self.assertIn('0x47', encoding)

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

    def test_surround_eq_reset_uses_the_profile_preset(self):
        frequencies, q_raw, gain_raw = self.server._surround_eq_reset_values(
            self.profile)
        self.assertEqual(frequencies, [30, 45, 90, 160, 350, 650, 1100, 1700,
                                       2500, 3500, 4750, 6250, 8250, 10750,
                                       13000, 15000])
        self.assertEqual(q_raw, 71)
        self.assertEqual(gain_raw, 0)

    def test_surround_json_enables_20_bass_and_speaker_head_writes(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.profile
        device.surround_contract = self.server._surround_global_contract(
            self.profile)
        device.surround_available = True
        device.surround_speaker_count = 16
        device._lock = threading.Lock()
        global_body = bytearray(151)
        global_body[0] = 0x02             # 2.0, no bass-management flag
        global_body[1] = 0x9F             # no-LFE sentinel
        global_body[4:6] = (600).to_bytes(2, 'little')
        global_body[13:23] = protocol.pack_surround_channel_order(
            [1, 3], 10)
        device.surround_global_raw = bytes(global_body)
        device.surround_global = protocol.parse_surround_global_record(
            self.profile, global_body)
        speaker_body = bytearray(116)
        speaker_body[0:2] = (100).to_bytes(2, 'little')
        speaker_body[2:4] = (0x8000 | 635).to_bytes(2, 'little')
        speaker = protocol.parse_surround_speaker_eq_record(
            self.profile, speaker_body)
        device.surround_speakers = {0: speaker, 1: speaker}

        payload = device.surround_json()

        self.assertTrue(payload['write']['bass']['enabled'])
        self.assertEqual(payload['write']['bass']['formats'], ['2.0', '2.1'])
        self.assertEqual(payload['write']['bass']['filter_types'], {
            'hp': 'Butterworth', 'lp': 'Butterworth'})
        self.assertEqual(
            [item['label'] for item in payload['write']['bass']
             ['filter_type_values']['hp_filter_type']],
            ['Butterworth', 'Linkwitz-Riley'])
        self.assertTrue(payload['write']['speaker_head']['enabled'])
        self.assertEqual(payload['write']['speaker_head']['fields'],
                         ['delay_ms', 'level_db', 'phase_invert'])
        self.assertEqual(
            payload['write']['speaker_head']['controls']['delay_ms']['range'],
            [0.6, 100.6])
        self.assertEqual(
            payload['speakers'][0]['head']['level_db'], 3.5)
        self.assertTrue(payload['speakers'][0]['head']['phase_invert'])
        self.assertTrue(payload['write']['speaker_bypass']['enabled'])
        self.assertEqual(payload['write']['speaker_bypass']['fields'], ['bypass'])
        self.assertTrue(payload['speakers'][0]['bypass'])

    def test_terminal_shutdown_stops_device_before_uvicorn_exit(self):
        class FakeServer:
            def __init__(self):
                self.should_exit = False
                self.calls = []

            def handle_exit(self, sig, frame):
                self.calls.append((sig, frame))
                self.should_exit = True

        fake_server = FakeServer()
        device = mock.Mock()
        wrapped = self.server._install_terminal_shutdown(fake_server, device)

        wrapped.handle_exit(signal.SIGINT, None)

        device.request_stop.assert_called_once_with()
        self.assertEqual(fake_server.calls, [(signal.SIGINT, None)])
        self.assertTrue(fake_server.should_exit)

        # A repeated Ctrl+C keeps Uvicorn's force-exit behavior but does not
        # enqueue a second device shutdown request.
        wrapped.handle_exit(signal.SIGINT, None)
        device.request_stop.assert_called_once_with()
        self.assertEqual(len(fake_server.calls), 2)

    def test_orion_selected_mixer_strip_meters_follow_the_window_selector(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.profile
        report = bytearray(320)
        report[122] = 2                 # Mix 3, target-1 selector
        report[157] = 0                 # strip 1
        report[188] = 96                # strip 32

        meters = device._parse_mixer_meters(report)
        self.assertEqual(meters['mix'], 2)
        self.assertEqual(meters['raw_range'], [0, 96])
        self.assertEqual(len(meters['strips']), 32)
        self.assertEqual(meters['strips'][0],
                         {'ch': 1, 'raw': 0, 'silence': False})
        self.assertEqual(meters['strips'][-1],
                         {'ch': 32, 'raw': 96, 'silence': True})

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

    def test_zen_go_preamp_candidates_are_exposed_as_raw_only_input_meters(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.zen_profile
        device.n_ch = 2
        report = bytearray(320)
        report[0xce + 0x10] = 12
        report[0xcf + 0x10] = 96

        samples = device._parse_meters(report)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0], {
            'raw': 12, 'db': None, 'clip': None, 'silence': False,
        })
        self.assertEqual(samples[1], {
            'raw': 96, 'db': None, 'clip': None, 'silence': True,
        })

    def test_zen_go_mixer_idle_floor_suppresses_first_strip_stub(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.zen_profile
        report = bytearray(320)
        report[122] = 0x0f
        report[158] = 84       # captured idle/noise floor
        report[159] = 83       # just below the declared floor

        meters = device._parse_mixer_meters(report)
        self.assertEqual(meters['noise_floor_raw'], 84)
        self.assertTrue(meters['strips'][0]['silence'])
        self.assertFalse(meters['strips'][1]['silence'])

    def test_zen_go_provisional_output_lanes_are_profile_driven(self):
        device = self.server.Device.__new__(self.server.Device)
        device.profile = self.zen_profile
        report = bytearray(320)
        report[234:240] = bytes((20, 96, 30, 40, 50, 96))

        meters = device._parse_output_meters(report)
        self.assertTrue(meters['provisional'])
        self.assertEqual(meters['raw_range'], [0, 96])
        self.assertEqual([item['bus'] for item in meters['outputs']], [0, 1, 2])
        self.assertEqual(meters['outputs'][0]['name'], 'Monitor')
        self.assertEqual(meters['outputs'][0]['lanes'][0]['raw'], 20)
        self.assertTrue(meters['outputs'][0]['lanes'][1]['silence'])
        self.assertEqual(meters['outputs'][2]['lanes'][0]['raw'], 50)

    def test_zen_go_routing_is_one_logical_sixteen_strip_destination(self):
        path = Path(__file__).resolve().parents[1] / 'profiles/zen_go_sc.json'
        features = self.server.features_for(str(path), self.zen_profile)
        routing = features['routing']
        self.assertTrue(routing['writable'])
        self.assertEqual(len(routing['destinations']), 1)
        self.assertEqual(routing['destinations'][0]['id'], 6)
        self.assertEqual(routing['destinations'][0]['channels'], 16)
        self.assertEqual(routing['destinations'][0]['write_destinations'],
                         [6, 7, 8, 9])

    def test_zen_go_routing_api_hides_mirrored_and_unrelated_records(self):
        path = Path(__file__).resolve().parents[1] / 'profiles/zen_go_sc.json'
        features = self.server.features_for(str(path), self.zen_profile)
        fake_device = mock.Mock()
        fake_device.routing_json.return_value = {
            str(dest): [] for dest in (3, 5, 6, 7, 8, 9)
        }
        with mock.patch.object(self.server, 'PROFILE', self.zen_profile), \
                mock.patch.object(self.server, 'UI_FEATURES', features), \
                mock.patch.object(self.server, 'DEV', fake_device):
            payload = self.server.api_routing()
        self.assertEqual([item['id'] for item in payload['dests']], [6])
        self.assertEqual(set(payload['current']), {'6'})

    def test_zen_go_logical_route_writes_all_four_mirrors(self):
        class FakeTransport:
            def __init__(self):
                self.writes = []

            def write(self, packet):
                self.writes.append(packet)

        path = Path(__file__).resolve().parents[1] / 'profiles/zen_go_sc.json'
        features = self.server.features_for(str(path), self.zen_profile)
        device = self.server.Device(self.zen_profile)
        for dest in (6, 7, 8, 9):
            device.routing[dest] = [(0x03, index) for index in range(32)]
        transport_obj = FakeTransport()
        with mock.patch.object(self.server, 'UI_FEATURES', features):
            device._set_routing_source(transport_obj, 6, 0, (0x00, 0))

        self.assertEqual([packet[18] for packet in transport_obj.writes],
                         [6, 7, 8, 9])
        self.assertEqual([packet[19:21] for packet in transport_obj.writes],
                         [bytes((0x00, 0))] * 4)

    def test_device_stop_closes_transport_and_wakes_worker(self):
        class FakeTransport:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        device = self.server.Device(self.zen_profile)
        transport_obj = FakeTransport()
        device._transport = transport_obj
        worker_done = threading.Event()

        def worker():
            device.cmds.get(timeout=1.0)
            worker_done.set()

        device._t = threading.Thread(target=worker)
        device._t.start()
        device.stop(timeout=1.0)
        self.assertTrue(device._stop.is_set())
        self.assertTrue(transport_obj.closed)
        self.assertTrue(worker_done.is_set())
        self.assertFalse(device._t.is_alive())

    def test_zen_go_surface_selector_uses_profile_command(self):
        packet, value, target = self.server._mixer_surface_packet(self.zen_profile, 1)
        self.assertEqual((value, target), (0x0c, 0))
        self.assertEqual(packet[0], 0x70)
        self.assertEqual(packet[4], 0x13)
        self.assertEqual(packet[16:19], bytes((0x49, 0, 0x0c)))
        self.assertIsNone(self.server._mixer_surface_packet(self.zen_profile, 2))


if __name__ == '__main__':
    unittest.main()
