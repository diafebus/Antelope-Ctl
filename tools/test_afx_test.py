"""Offline capture fixtures and failure paths for the Orion AFX pilot."""
import copy
import json
from pathlib import Path
import threading
import unittest

from antelope import afx, protocol
from webui.afx_test import MemoryCatTest

ROOT = Path(__file__).resolve().parents[1]


class FakeTransport:
    def __init__(self, slots, *, mismatch=False, linked=False):
        self.slots = list(slots)
        self.chains = {0: self.slots}
        self.link_flags = [int(linked)] + [0] * 31
        self.writes = []
        self.mismatch = mismatch
        self.linked = linked
        self.remaining = {73: 8, 75: 2, 27: 2, 70: 2, 78: 2}
        self.parameters = {instance: dict(blend=50, level=100, feedback=0, chrs_vibr=0,
                                         depth=0, delay=50, lpf_fc=100, size=0) for instance in range(8)}
        self.enabled = {instance: True for instance in range(8)}
        self.queries = []
        self.parameter_timeout = False

    def query(self, request, match, timeout, retries=2):
        self.queries.append(request)
        if request[4] == 0x11:
            if self.parameter_timeout:
                return None
            instance = request[16]
            response = bytearray.fromhex('75000000400100000700000049000080') + bytearray(304)
            response[16] = int(self.enabled[instance])
            for name, offset in dict(blend=17, level=18, feedback=19, chrs_vibr=20,
                                     depth=21, delay=22, lpf_fc=23, size=24).items():
                response[offset] = self.parameters[instance][name]
            assert match(bytes(response))
            return bytes(response)
        category, index = request[8], request[12]
        response = bytearray(320)
        response[0], response[8], response[12] = 0x75, category, index
        if category == 0x19:
            response[16:32] = bytes(value for slot in self.chains.get(index, [(0, 0)] * 8) for value in slot)
        elif category == 0x0b:
            self.assert_index = index
            response[16:48] = bytes(self.link_flags)
        elif category == 0x15:
            for i in range(91):
                response[16 + i * 2:18 + i * 2] = bytes([i, self.remaining.get(i, 0)])
        else:
            raise AssertionError(f'Unexpected query {category:#x}:{index}')
        assert match(bytes(response))
        return bytes(response)

    def write(self, packet):
        self.writes.append(packet)
        if packet[4] == 0x23 and not self.mismatch and packet[18] != getattr(self, 'mismatch_channel', None):
            self.chains[packet[18]] = list(zip(packet[19:35:2], packet[20:35:2]))
            self.slots = self.chains[0]
        elif packet[4] == 0x14 and packet[16:18] == bytes([0xa2, 4]):
            self.link_flags[packet[18]] = packet[19]
        elif packet[4] == 0x1c:
            self.parameters[packet[19]] = {name: packet[offset] for name, offset in
                dict(blend=20, level=21, feedback=22, chrs_vibr=23, depth=24, delay=25, lpf_fc=26, size=27).items()}


class FakeDevice:
    def __init__(self, profile, transport):
        self.profile = profile
        self._lock = threading.Lock()
        self._transport = transport
        self.connection_generation = 1
        self.snapshot = {'online': True}
        self.rb_ver = 0
        self.structured = {(0x19, index): [dict(type=0, inst=0) for _ in range(8)]
                           for index in range(64)}

    def submit(self, function):
        function(self._transport)


class AfxTestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = protocol.load_profile(ROOT / 'profiles/orion_studio_sc.json')

    def test_complete_chain_matches_eight_instance_and_reorder_capture(self):
        # New capture frames 44873 and 48043; every other report byte is zero.
        slots = [(73, i) for i in range(8)]
        packet = afx.build_chain_test(self.profile, slots)
        expected = bytes.fromhex('70000000230000000000000000000000d71100'
                                 '49004901490249034904490549064907')
        self.assertEqual(packet, expected.ljust(320, b'\x00'))
        moved = afx.change_chain(self.profile, slots, 'move', 0, source=4)
        self.assertEqual(moved, [(73, i) for i in [4, 0, 1, 2, 3, 5, 6, 7]])
        self.assertEqual(afx.build_chain_test(self.profile, moved)[19:35],
                         bytes.fromhex('49044900490149024903490549064907'))

    def test_instance_four_level_zero_matches_captured_parameter_frame(self):
        values = dict(blend=50, level=0, feedback=0, chrs_vibr=0,
                      depth=0, delay=0, lpf_fc=100, size=0)
        packet = afx.build_parameter_test(self.profile, 4, values)
        expected = bytes.fromhex('700000001c0000000000000000000000d50a49043200000000006400')
        self.assertEqual(packet, expected.ljust(320, b'\x00'))

    def test_parameter_readback_matches_reopen_capture_and_correlation_guard(self):
        query = afx.build_parameter_query(self.profile, 2)
        self.assertEqual(query, bytes.fromhex('7400000011000000070000004900008002000000').ljust(320, b'\x00'))
        reply = bytes.fromhex('75000000400100000700000049000080013232310031303100').ljust(320, b'\x00')
        state = afx.parse_parameter_response(self.profile, reply)
        self.assertEqual(state['values'], dict(blend=50, level=50, feedback=49,
            chrs_vibr=0, depth=49, delay=48, lpf_fc=49, size=0))
        self.assertFalse(state['bypassed'])
        for instance in (-1, 3, True):
            with self.assertRaises(ValueError):
                afx.build_parameter_query(self.profile, instance)
        bad = bytearray(reply)
        bad[12] = 75
        self.assertFalse(afx.is_parameter_response(self.profile, bytes(bad)))
        bad = bytearray(reply)
        bad[18] = 101
        with self.assertRaises(ValueError):
            afx.parse_parameter_response(self.profile, bytes(bad))

    def test_refresh_load_and_reconnect_read_real_values_without_parameter_writes(self):
        transport = FakeTransport([(73,0),(73,1)] + [(0,0)]*6)
        transport.parameters[0] = dict(blend=0, level=0, feedback=0, chrs_vibr=0, depth=0, delay=0, lpf_fc=0, size=1)
        transport.enabled[0] = False
        device = FakeDevice(self.profile, transport)
        service = MemoryCatTest(device)
        state = service.refresh()
        self.assertEqual(state['parameters']['0'], transport.parameters[0])
        self.assertTrue(state['parameter_states']['0']['bypassed'])
        self.assertTrue(state['switch_polarity_confirmed'])
        self.assertEqual(transport.writes, [])
        state = service.change_chain('load', 2)
        self.assertEqual(state['parameter_states']['2']['values'], transport.parameters[2])
        self.assertFalse(state['parameter_states']['2']['bypassed'])
        self.assertEqual(len(transport.writes), 1, 'Loading must not force bypass or settings')
        device._transport = FakeTransport(transport.slots)
        device.connection_generation += 1
        self.assertEqual(service.state()['parameter_states'], {})
        device._transport.parameters[0]['level'] = 23
        self.assertEqual(service.refresh()['parameters']['0']['level'], 23)
        self.assertEqual(device._transport.writes, [])

    def test_parameter_timeout_stops_untagged_instance_queries_until_reconnect(self):
        transport = FakeTransport([(73,0),(73,1)] + [(0,0)]*6)
        transport.parameter_timeout = True
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        state = service.refresh()
        self.assertEqual(state['parameter_states'], {})
        self.assertEqual(len([query for query in transport.queries if query[4] == 0x11]), 1)
        service.refresh()
        self.assertEqual(len([query for query in transport.queries if query[4] == 0x11]), 1)
        self.assertEqual(transport.writes, [])

    def test_parameter_write_verifies_readback_and_preserves_processing_state(self):
        transport = FakeTransport([(73,0)] + [(0,0)]*7)
        transport.enabled[0] = False
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        values = {**transport.parameters[0], 'level': 39}
        result = service.change_parameters(0, values)
        self.assertTrue(result['verified'])
        self.assertTrue(result['bypassed'])
        self.assertFalse(transport.enabled[0])

    def test_generic_guards_and_other_devices_remain_blocked(self):
        for opcode in (0x1c, 0x20, 0x23, 0x7c):
            with self.assertRaises(protocol.ConstraintError):
                protocol.check_opcode(self.profile, opcode)
        profile = copy.deepcopy(self.profile)
        profile['device']['pid'] = '0xa222'
        with self.assertRaises(protocol.ConstraintError):
            afx.build_chain_test(profile, [(0, 0)] * 8)
        with self.assertRaises(protocol.ConstraintError):
            afx.build_chain_test(self.profile, [(73, 8)] + [(0, 0)] * 7)

    def test_mutation_rejects_foreign_removal_and_duplicate_instances(self):
        chain = [(6, 0)] + [(0, 0)] * 7
        after = afx.change_chain(self.profile, chain, 'load', 1, instance=0)
        self.assertEqual(after[:2], [(6, 0), (73, 0)])
        with self.assertRaises(ValueError):
            afx.change_chain(self.profile, chain, 'remove', 0)
        with self.assertRaises(ValueError):
            afx.change_chain(self.profile, after, 'load', 2, instance=0)

    def test_fresh_slot_write_is_verified_and_failed_verification_latches(self):
        transport = FakeTransport([(0, 0)] * 8)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        state = service.change_chain('load', 0)
        self.assertEqual(state['slots'][0], {'type': 73, 'instance': 0})
        self.assertEqual(len(transport.writes), 1)
        transport.mismatch = True
        with self.assertRaisesRegex(RuntimeError, 'further AFX testing is disabled'):
            service.change_chain('move', 1, 0)
        self.assertFalse(service.state()['writes_enabled'])
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            service.change_chain('remove', 0)
        self.assertEqual(len(transport.writes), 2)

    def test_linked_chain_edits_write_both_chains_with_distinct_instances(self):
        transport = FakeTransport([(0, 0)] * 8, linked=True)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        state = service.change_chain('load', 0, channel=1)
        self.assertEqual([packet[18] for packet in transport.writes], [0, 1])
        self.assertEqual(transport.chains[0][0], (73, 0))
        self.assertEqual(transport.chains[1][0], (73, 1))
        self.assertEqual(state['channels']['1'][0], {'type':73, 'instance':1})
        service.change_chain('load', 1, effect_id='deesser')
        service.change_chain('move', 1, 0, channel=1)
        self.assertEqual(transport.chains[0][:2], [(27,0),(73,0)])
        self.assertEqual(transport.chains[1][:2], [(27,1),(73,1)])
        service.change_chain('remove', 1)
        self.assertEqual(transport.chains[0][:2], [(27,0),(0,0)])
        self.assertEqual(transport.chains[1][:2], [(27,1),(0,0)])
        service.change_chain('replace', 0, effect_id='instinct', channel=1)
        self.assertEqual(transport.chains[0][0], (75,0))
        self.assertEqual(transport.chains[1][0], (75,1))
        self.assertEqual(len(transport.writes), 10)
        self.assertTrue(all(packet[4] == 0x23 for packet in transport.writes))
        self.assertTrue(service.state()['links'][0])
        # Parameter sharing remains separately guarded.
        with self.assertRaisesRegex(RuntimeError, 'stereo links off'):
            service.change_parameters(0, transport.parameters[0])

    def test_linked_chain_preflight_preserves_both_on_capacity_or_slot_conflict(self):
        transport = FakeTransport([(0,0)]*8, linked=True)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        transport.remaining[73] = 1
        with self.assertRaisesRegex(RuntimeError, '2 remaining'):
            service.change_chain('load', 0)
        self.assertEqual(transport.writes, [])
        transport.remaining[73] = 8
        transport.chains[1] = [(6,0)] + [(0,0)]*7
        with self.assertRaises(ValueError):
            service.change_chain('load', 0)
        self.assertEqual(transport.writes, [])
        transport.chains[0] = [(73,0)] + [(0,0)]*7
        with self.assertRaisesRegex(RuntimeError, 'different effects'):
            service.change_chain('remove', 0)
        self.assertEqual(transport.writes, [])

    def test_linked_partner_verification_failure_stops_without_repair(self):
        transport = FakeTransport([(0,0)]*8, linked=True)
        transport.mismatch_channel = 1
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        with self.assertRaisesRegex(RuntimeError, 'verification failed'):
            service.change_chain('load', 0)
        self.assertEqual(len(transport.writes), 2)
        self.assertEqual(transport.chains[0][0], (73,0))
        self.assertFalse(service.state()['writes_enabled'])
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            service.change_chain('load', 1)
        self.assertEqual(len(transport.writes), 2)

    def test_already_queued_request_obeys_a_later_verification_failure(self):
        transport = FakeTransport([(73, 0)] + [(0, 0)] * 7)
        device = FakeDevice(self.profile, transport)
        service = MemoryCatTest(device)
        def submit(function):
            # Another operation failed after this request entered the queue.
            service.failed_verification = True
            function(transport)
        device.submit = submit
        with self.assertRaisesRegex(RuntimeError, 'disabled'):
            service.change_chain('remove', 0)
        self.assertEqual(transport.writes, [])

    def test_unlink_sends_only_the_flag_without_chain_cleanup(self):
        slots = [(73, 0), (70, 0)] + [(0, 0)] * 6
        transport = FakeTransport(slots, linked=True)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        result = service.unlink_pilot()
        self.assertTrue(result['verified'])
        self.assertEqual(transport.slots, slots)
        self.assertEqual(len(transport.writes), 1)
        self.assertEqual(transport.writes[0][4], 0x14)
        self.assertEqual(transport.writes[0][16:20], bytes([0xa2, 4, 0, 0]))

    def test_captured_effect_picker_load_replace_remove_and_instance_bounds(self):
        transport = FakeTransport([(73, 0)] + [(0, 0)] * 7)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        service.change_chain('load', 1, effect_id='instinct')
        self.assertEqual(transport.slots[:2], [(73, 0), (75, 0)])
        service.change_chain('replace', 1, effect_id='deesser')
        self.assertEqual(transport.slots[:2], [(73, 0), (27, 0)])
        service.change_chain('remove', 1)
        self.assertEqual(transport.slots[:2], [(73, 0), (0, 0)])
        count = len(transport.writes)
        with self.assertRaises(ValueError):
            service.change_chain('load', 1, effect_id='unmapped')
        transport.remaining[78] = 0
        with self.assertRaisesRegex(RuntimeError, 'no remaining'):
            service.change_chain('load', 1, effect_id='bbdchorus')
        self.assertEqual(len(transport.writes), count)
        with self.assertRaises(protocol.ConstraintError):
            afx.build_chain_test(self.profile, [(75, 2)] + [(0, 0)] * 7)

    def test_link_all_pairs_last_sent_and_reconnect_without_slot_writes(self):
        transport = FakeTransport([(0, 0)] * 8)
        device = FakeDevice(self.profile, transport)
        service = MemoryCatTest(device)
        self.assertEqual(service.state()['links'], [None] * 16)
        for pair in (0, 1, 15):
            service.set_link(pair, True)
            self.assertEqual(transport.writes[-1][16:20], bytes([0xa2, 4, pair, 1]))
            self.assertTrue(service.state()['links'][pair])
        with self.assertRaisesRegex(RuntimeError, 'stereo links off'):
            service.change_parameters(0, transport.parameters[0])
        for bad_pair, enabled in ((16, True), (-1, False), (True, True), (0, 1)):
            with self.assertRaises(ValueError):
                service.set_link(bad_pair, enabled)
        self.assertEqual(len(transport.writes), 3)
        self.assertTrue(service.state()['link_readback'])
        device._transport = FakeTransport(transport.slots)
        device.structured.pop((0x0b, 4), None)
        self.assertEqual(service.state()['links'], [None] * 16)

    def test_refresh_is_read_only_and_preserves_failure_latch(self):
        transport = FakeTransport([(0, 0)] * 8)
        transport.chains[31] = [(73, 4)] + [(0, 0)] * 7
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        service.failed_verification = True
        result = service.refresh(31)
        self.assertEqual(result['channels']['31'][0], {'type':73, 'instance':4})
        self.assertTrue(result['link_readback'])
        self.assertFalse(result['writes_enabled'])
        self.assertEqual(transport.writes, [])

    def test_selected_channels_preserve_other_chains_and_instances(self):
        transport = FakeTransport([(73, 0)] + [(0, 0)] * 7)
        device = FakeDevice(self.profile, transport)
        device.structured[(0x19, 0)][0] = dict(type=73, inst=0)
        service = MemoryCatTest(device)
        for channel, instance in ((2, 1), (31, 2)):
            result = service.change_chain('load', 7, channel=channel)
            self.assertEqual(result['channels'][str(channel)][7], {'type': 73, 'instance': instance})
            self.assertEqual(transport.writes[-1][18], channel)
            self.assertEqual(transport.chains[0][0], (73, 0))
            service.change_chain('move', 0, 7, channel=channel)
            values = dict(blend=1, level=90, feedback=0, chrs_vibr=0,
                          depth=0, delay=20, lpf_fc=100, size=1)
            service.change_parameters(instance, values, channel=channel)
            self.assertEqual(transport.writes[-1][19], instance)
            with self.assertRaisesRegex(RuntimeError, 'no longer'):
                service.change_parameters(0, values, channel=channel)
        writes = len(transport.writes)
        for channel in (-1, 32, True, 1.5):
            with self.assertRaises(ValueError):
                service.change_chain('load', 0, channel=channel)
        self.assertEqual(len(transport.writes), writes)
        transport.mismatch = True
        with self.assertRaisesRegex(RuntimeError, 'further AFX testing is disabled'):
            service.change_chain('remove', 0, channel=31)

    def test_link_readback_overrides_last_sent_and_only_guards_selected_pair(self):
        profile = copy.deepcopy(self.profile)
        profile['runtime_contracts']['afx_rack_test']['link_pair_records'] = [[pair] for pair in range(16)]
        transport = FakeTransport([(0, 0)] * 8)
        device = FakeDevice(profile, transport)
        service = MemoryCatTest(device)
        self.assertTrue(service.set_link(15, True)['verified'])
        self.assertTrue(service.state()['link_readback'])
        self.assertTrue(service.state()['links'][15])
        service.change_chain('load', 0, channel=2)
        service.change_chain('load', 0, channel=30)
        self.assertEqual(transport.chains[30][0], (73,1))
        self.assertEqual(transport.chains[31][0], (73,2))
        with self.assertRaisesRegex(RuntimeError, 'stereo links off'):
            service.change_parameters(1, transport.parameters[1], channel=30)
        # External change must supersede the session's last command.
        transport.link_flags[15] = 0
        service._read_links(transport)
        self.assertFalse(service.state()['links'][15])
        # A new transport never inherits old cached flags.
        device.snapshot['online'] = False
        device._transport = None
        self.assertFalse(service.state()['link_readback'])

    def test_parameters_require_full_state_and_a_current_loaded_instance(self):
        values = dict(blend=50, level=0, feedback=0, chrs_vibr=0,
                      depth=0, delay=0, lpf_fc=100, size=0)
        transport = FakeTransport([(73, 4)] + [(0, 0)] * 7)
        device = FakeDevice(self.profile, transport)
        service = MemoryCatTest(device)
        result = service.change_parameters(4, values)
        self.assertTrue(result['sent'])
        self.assertFalse(result['verified'])
        self.assertEqual(service.state()['parameters']['4'], values)
        with self.assertRaisesRegex(RuntimeError, 'no longer'):
            service.change_parameters(3, values)
        with self.assertRaises(ValueError):
            service.change_parameters(4, {'level': 0})
        with self.assertRaises(ValueError):
            service.change_parameters(4, {**values, 'size': 2})
        self.assertEqual(len(transport.writes), 1)
        device._transport = FakeTransport(transport.slots)
        self.assertEqual(service.state()['parameters'], {}, 'Reconnect must clear last-sent assumptions')


if __name__ == '__main__':
    unittest.main()
