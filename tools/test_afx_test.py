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
        self.writes = []
        self.mismatch = mismatch
        self.linked = linked
        self.remaining = {73: 8, 75: 2, 27: 2, 70: 2, 78: 2}

    def query(self, request, match, timeout):
        category, index = request[8], request[12]
        response = bytearray(320)
        response[0], response[8], response[12] = 0x75, category, index
        if category == 0x19:
            response[16:32] = bytes(value for slot in self.slots for value in slot)
        elif category == 0x0b:
            self.assert_index = index
            response[16] = int(self.linked)
        elif category == 0x15:
            for i in range(91):
                response[16 + i * 2:18 + i * 2] = bytes([i, self.remaining.get(i, 0)])
        else:
            raise AssertionError(f'Unexpected query {category:#x}:{index}')
        assert match(bytes(response))
        return bytes(response)

    def write(self, packet):
        self.writes.append(packet)
        if packet[4] == 0x23 and not self.mismatch:
            self.slots = list(zip(packet[19:35:2], packet[20:35:2]))


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

    def test_linked_mono_test_does_not_write(self):
        transport = FakeTransport([(0, 0)] * 8, linked=True)
        service = MemoryCatTest(FakeDevice(self.profile, transport))
        with self.assertRaisesRegex(RuntimeError, 'stereo links off'):
            service.change_chain('load', 0)
        self.assertEqual(transport.writes, [])

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
        self.assertFalse(result['verified'])
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
            service.change_chain('load', 0)
        for bad_pair, enabled in ((16, True), (-1, False), (True, True), (0, 1)):
            with self.assertRaises(ValueError):
                service.set_link(bad_pair, enabled)
        self.assertEqual(len(transport.writes), 3)
        self.assertFalse(service.state()['link_readback'])
        device._transport = FakeTransport(transport.slots)
        self.assertEqual(service.state()['links'], [None] * 16)

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
