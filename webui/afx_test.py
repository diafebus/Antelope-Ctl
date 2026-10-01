"""Captured Orion rack and Memory Cat parameter tests, serialized by the device."""
from concurrent.futures import Future, TimeoutError
import time

from antelope import afx, protocol


class MemoryCatTest:
    def __init__(self, device):
        self.device = device
        self.sent_parameters = {}  # instance -> (transport object, last sent values)
        self.failed_verification = False
        self.sent_links = {}  # pair -> (transport, requested state), not readback

    def state(self):
        device = self.device
        try:
            afx.test_contract(device.profile)
        except (ValueError, KeyError):
            return {'available': False}
        with device._lock:
            records = device.structured.get((0x19, 0))
            online = bool(device.snapshot.get('online'))
            slots = None if records is None else [
                {'type': record['type'], 'instance': record['inst']} for record in records]
            parameters = {str(instance): dict(values) for instance, (transport, values)
                          in self.sent_parameters.items() if transport is device._transport}
            links = [self.sent_links.get(pair) for pair in range(16)]
            links = [value[1] if value and value[0] is device._transport else None
                     for value in links]
        return {'available': True, 'experimental': True, 'channel': 0,
                'online': online, 'slots': slots, 'parameters': parameters,
                'session': device.connection_generation,
                'writes_enabled': not self.failed_verification,
                'parameter_readback': False, 'switch_polarity_confirmed': False,
                'links': links, 'link_state_source': 'last-sent',
                'link_readback': False}

    def _read_chain(self, transport):
        device = self.device
        request = protocol.build_readback_query(device.profile, 0x19, 0)
        response = transport.query(request, lambda data: protocol.is_readback_response(
            device.profile, data, 0x19, 0), timeout=1.5)
        if response is None:
            raise RuntimeError('No fresh Preamp 1 slot readback; nothing was changed')
        records = protocol.parse_afx_strip_order(device.profile,
            protocol.readback_body(device.profile, response), 0x19, 0)
        slots = afx.validate_slots([(row['type'], row['inst']) for row in records])
        with device._lock:
            device.structured[(0x19, 0)] = records
            device.rb_ver += 1
        return slots

    def _allocate_instance(self, transport, chain, spec):
        device = self.device
        count = protocol.readback_category_count(device.profile, 0x19)
        with device._lock:
            inventory = {index: list(device.structured.get((0x19, index), []))
                         for index in range(count or 0)}
        if count != 64 or any(len(records) != 8 for records in inventory.values()):
            raise RuntimeError('Wait for the complete AFX inventory before loading an effect')
        effect_type = spec['type_id']
        used = {instance for kind, instance in chain if kind == effect_type}
        used.update(row['inst'] for index, records in inventory.items() if index != 0
                    for row in records if row['type'] == effect_type)
        request = protocol.build_readback_query(device.profile, 0x15, 0)
        response = transport.query(request, lambda data: protocol.is_readback_response(
            device.profile, data, 0x15, 0), timeout=1.5)
        if response is None:
            raise RuntimeError('Effect availability could not be read; nothing was loaded')
        counters = protocol.parse_afx_instance_table(device.profile,
            protocol.readback_body(device.profile, response), 0x15, 0)
        remaining = next((row['inst_count'] for row in counters if row['type_id'] == effect_type), 0)
        if not remaining:
            raise RuntimeError('The device reports no remaining instances of this effect')
        return next((index for index in spec['instance_indices'] if index not in used), None)

    def _execute(self, work, *, allow_linked=False):
        device = self.device
        afx.test_contract(device.profile)
        if self.failed_verification:
            raise RuntimeError('AFX slot verification failed; testing is disabled for this server session')
        with device._lock:
            if not device.snapshot.get('online') or device._transport is None:
                raise RuntimeError('The Orion device is offline')
            expected_transport = device._transport
        future = Future()
        deadline = time.monotonic() + 10

        def queued(transport):
            if not future.set_running_or_notify_cancel():
                return
            def still_current():
                with device._lock:
                    current = device._transport
                if (transport is not expected_transport or transport is not current
                        or time.monotonic() > deadline):
                    raise RuntimeError('Device session changed or the test request expired')
            try:
                still_current()
                if self.failed_verification:
                    raise RuntimeError('AFX slot verification failed; testing is disabled for this server session')
                # Linked-effect parameter sharing is not decoded. Require an
                # entirely unlinked AFX table for this mono test, rather than
                # guessing which of its 32 flags belongs to the pilot channel.
                request = protocol.build_readback_query(device.profile, 0x0b, 4)
                response = transport.query(request, lambda data: protocol.is_readback_response(
                    device.profile, data, 0x0b, 4), timeout=1.5)
                if response is None:
                    raise RuntimeError('AFX link state is unavailable; nothing was changed')
                links = protocol.parse_link_table(device.profile,
                    protocol.readback_body(device.profile, response), 0x0b, 4)
                if len(links) != 32 or (not allow_linked and any(row['linked'] for row in links)):
                    raise RuntimeError('Turn AFX stereo links off before changing the mono AFX rack')
                if not allow_linked and any(owner is transport and enabled
                                            for owner, enabled in self.sent_links.values()):
                    raise RuntimeError('Turn AFX stereo links off before changing the mono rack')
                result = work(transport, still_current)
            except Exception as error:
                future.set_exception(error)
                if isinstance(error, OSError):
                    raise
            else:
                future.set_result(result)
        device.submit(queued)
        try:
            return future.result(timeout=12)
        except TimeoutError:
            future.cancel()
            raise RuntimeError('AFX test timed out; refresh the rack before trying again') from None

    def set_link(self, pair, enabled):
        afx.test_contract(self.device.profile)
        if type(pair) is not int or not 0 <= pair < 16 or type(enabled) is not bool:
            raise ValueError('AFX link requires a pair in 0..15 and a boolean state')
        def work(transport, still_current):
            packet = protocol.build_link_command(self.device.profile, pair, enabled, space=4)
            still_current()
            # The Launcher bug emits extra right-chain assignments here.
            # A link toggle must not silently create, clear, or reorder effects.
            transport.write(packet)
            with self.device._lock:
                self.sent_links[pair] = (transport, enabled)
            return {'sent': True, 'verified': False, 'pair': pair, 'enabled': enabled}
        return self._execute(work, allow_linked=True)

    def unlink_pilot(self):
        return self.set_link(0, False)

    def change_chain(self, operation, slot, source=None, effect_id='memory_brigade'):
        effects = afx.load_effects(self.device.profile)
        allocating = operation in ('load', 'replace')
        if allocating and effect_id not in effects:
            raise ValueError('Effect loading is not mapped for this Orion profile')
        def work(transport, still_current):
            before = self._read_chain(transport)
            instance = self._allocate_instance(transport, before, effects[effect_id]) if allocating else None
            if allocating and instance is None:
                raise RuntimeError('All captured instance indices for this effect are already used')
            after = afx.change_chain(self.device.profile, before, operation, slot,
                                     source=source, instance=instance, effect_id=effect_id)
            packet = afx.build_chain_test(self.device.profile, after, original_slots=before)
            still_current()
            transport.write(packet)
            try:
                actual = self._read_chain(transport)
            except Exception:
                self.failed_verification = True
                raise RuntimeError('Post-write slot readback failed; further AFX testing is disabled') from None
            if actual != after:
                # The new capture has no post-load slot reply. A failed mapping
                # must not trigger another unverified corrective write.
                self.failed_verification = True
                raise RuntimeError('Slot readback did not match the write; further AFX testing is disabled')
            with self.device._lock:
                if allocating and effects[effect_id]['type_id'] == 73:
                    self.sent_parameters.pop(instance, None)
                if operation in ('remove', 'replace') and before[slot][0] == 73:
                    self.sent_parameters.pop(before[slot][1], None)
            return self.state()
        return self._execute(work)

    def change_parameters(self, instance, values):
        values = afx.validate_parameters(self.device.profile, values)
        packet = afx.build_parameter_test(self.device.profile, instance, values)
        def work(transport, still_current):
            chain = self._read_chain(transport)
            if (73, instance) not in chain:
                raise RuntimeError('That Memory Cat instance is no longer on Preamp 1')
            still_current()
            transport.write(packet)
            with self.device._lock:
                self.sent_parameters[instance] = (transport, dict(values))
            return {'sent': True, 'verified': False, 'instance': instance,
                    'values': values, 'parameter_readback': False}
        return self._execute(work)
