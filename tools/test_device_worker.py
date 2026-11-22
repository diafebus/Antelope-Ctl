"""Device worker and local-only web checks. No device is opened.

Run: python3 -m unittest tools.test_device_worker
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from unittest import mock

from tools.test_meter_sources import load_server_without_web_or_hid_boundaries

server = load_server_without_web_or_hid_boundaries()   # no web stack, no HID scan


class NoWait(threading.Event):
    """The worker's 2 s reconnect pause, without the pause."""

    def wait(self, timeout=None):
        return self.is_set()


class FakeTransport:
    def __init__(self):
        self.written = []
        self.reading = threading.Event()

    def write(self, packet):
        self.written.append(bytes(packet))

    def read_one(self, magic, timeout=None):
        self.reading.set()
        return None

    def read_reports(self, magic, timeout=None):
        return ()

    def query(self, request, match, timeout=None):
        return None

    def close(self):
        pass


class DeviceWorkerTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[1] / 'profiles/orion_studio_sc.json'
        self.device = server.Device(json.loads(path.read_text()))
        self.device._stop = NoWait()

    def test_writes_queued_while_offline_are_not_replayed_on_reconnect(self):
        device, transport = self.device, FakeTransport()
        device.submit(lambda t: t.write(b'before the first open'))

        def opening(*args):
            # Old transports exit, new ones raise OSError: both mean "offline, retry".
            device.submit(lambda t: t.write(b'while unplugged'))
            yield OSError('device not found')
            device.submit(lambda t: t.write(b'while still unplugged'))
            yield SystemExit('device not found')
            device.submit(lambda t: t.write(b'during the open'))
            yield transport

        attempts = opening()
        with mock.patch.object(server, 'open_transport',
                               side_effect=lambda *args: _raise_or_return(next(attempts))):
            device.start()
            self.assertTrue(transport.reading.wait(5), 'the worker never connected')
            ran = threading.Event()
            device.submit(lambda t: (t.write(b'after reconnect'), ran.set()))
            self.assertTrue(ran.wait(5), 'a command sent while online did not run')
            device.stop()
        self.assertFalse(device._t.is_alive())
        self.assertEqual(transport.written, [b'after reconnect'])

    def test_an_unexpected_error_does_not_end_the_worker(self):
        device, transport = self.device, FakeTransport()
        failed = threading.Event()

        def broken_read(magic, timeout=None):
            if not failed.is_set():
                failed.set()
                raise ValueError('short report')
            transport.reading.set()
            return None

        transport.read_one = broken_read
        with mock.patch.object(server, 'open_transport', return_value=transport), \
                mock.patch.object(server.traceback, 'print_exc'):
            device.start()
            self.assertTrue(transport.reading.wait(5), 'the worker did not come back after the error')
            ran = threading.Event()
            device.submit(lambda t: ran.set())
            self.assertTrue(ran.wait(5))
            device.stop()
        self.assertFalse(device._t.is_alive())

    def test_stop_ends_a_worker_that_cannot_open_the_device(self):
        device = self.device
        tried = threading.Event()

        def refuse(*args):
            tried.set()
            raise OSError('device not found')

        with mock.patch.object(server, 'open_transport', side_effect=refuse):
            device.start()
            self.assertTrue(tried.wait(5))
            device.submit(lambda t: t.write(b'never'))
            device.stop()
        self.assertFalse(device._t.is_alive())
        self.assertFalse(device.get()[0]['online'])


def _raise_or_return(result):
    if isinstance(result, BaseException):
        raise result
    return result


class LocalHostOnlyTests(unittest.TestCase):
    def test_the_app_only_trusts_local_host_names(self):
        middleware, options = server.app.middleware
        self.assertEqual(middleware, 'TrustedHostMiddleware')
        self.assertEqual(options, {'allowed_hosts': ['127.0.0.1', 'localhost']})

    @unittest.skipUnless(importlib.util.find_spec('starlette'), 'needs the WebUI venv')
    def test_a_foreign_host_header_is_refused(self):
        from starlette.middleware.trustedhost import TrustedHostMiddleware

        async def inner(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        guarded = TrustedHostMiddleware(inner, **server.app.middleware[1])

        def status(host):
            sent = []

            async def send(message):
                sent.append(message)
            asyncio.run(guarded({'type': 'http', 'method': 'GET', 'path': '/',
                                 'headers': [(b'host', host)]}, None, send))
            return sent[0]['status']

        for host in (b'127.0.0.1:8714', b'127.0.0.1:8715', b'localhost:8714', b'127.0.0.1'):
            self.assertEqual(status(host), 200, host)
        for host in (b'evil.example:8714', b'127.0.0.1.evil.example', b'[::1]:8714'):
            self.assertEqual(status(host), 400, host)


if __name__ == '__main__':
    unittest.main()
