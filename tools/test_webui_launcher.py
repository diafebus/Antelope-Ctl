"""Exercise the packaged launcher with fake USB detection and service startup."""
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ORION = (0x23e5, 0xa221)
ZEN_GO = (0x23e5, 0xa015)


class WebUILauncherTests(unittest.TestCase):
    def setUp(self):
        script = runpy.run_path(str(ROOT / 'packaging/antelope-webui-launch'))
        self.launcher = SimpleNamespace(**script)
        self.globals = self.launcher.connected_targets.__globals__
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.config = Path(temp)
        self.enterContext(patch.dict(self.globals, {'CONFIG_DIR': self.config}))
        self.enterContext(patch.object(self.launcher.transport, 'list_connected_hid',
                                       return_value={ORION, ZEN_GO}))

    def settings(self, name, profile, port):
        (self.config / f'{name}.env').write_text(
            f'ANTELOPE_PROFILE="{profile}"\nANTELOPE_PORT={port}\n', encoding='utf-8')

    def test_connected_configured_services_and_offline_devices(self):
        self.settings('webui', 'orion_studio_sc', 8720)
        self.settings('zen', 'zen_go_sc.json', 8721)
        self.settings('other', 'discrete_8_pro_sc', 8722)
        with patch.dict(self.globals, {'probe': lambda port: (False, None)}):
            self.assertEqual(self.launcher.connected_targets(), [
                ('antelope-webui', 8720, ORION), ('antelope-webui@zen', 8721, ZEN_GO)])
        self.assertEqual(self.launcher.service_target('antelope-webui@zen'),
                         ('antelope-webui@zen', 8721, ZEN_GO))

    def test_running_default_profile_prevents_duplicate_service(self):
        self.settings('orion', 'orion_studio_sc.json', 8720)
        self.settings('zen', 'zen_go_sc.json', 8721)
        with patch.dict(self.globals, {'probe': lambda port: (True, ORION)}):
            self.assertEqual(self.launcher.connected_targets(), [
                ('antelope-webui', 8714, ORION), ('antelope-webui@zen', 8721, ZEN_GO)])

    def test_default_autodetection_skips_incomplete_profile(self):
        self.settings('zen', 'zen_go_sc.json', 8721)
        connected = {(0x23e5, 0xa2be), ORION, ZEN_GO}
        with patch.object(self.launcher.transport, 'list_connected_hid', return_value=connected), \
                patch.dict(self.globals, {'probe': lambda port: (False, None)}):
            self.assertEqual(self.launcher.connected_targets(), [
                ('antelope-webui', 8714, ORION), ('antelope-webui@zen', 8721, ZEN_GO)])

    def test_duplicate_ports_refuse_before_starting_either_service(self):
        self.settings('webui', 'orion_studio_sc', 8720)
        self.settings('zen', 'zen_go_sc.json', 8720)
        with patch.dict(self.globals, {'probe': lambda port: (False, None)}):
            with self.assertRaisesRegex(ValueError, 'distinct ports'):
                self.launcher.connected_targets()

    def test_reuses_matching_webui_and_refuses_other_listeners(self):
        with patch.object(self.launcher.subprocess, 'run') as start:
            with patch.dict(self.globals, {'probe': lambda port: (True, ORION)}):
                self.launcher.ensure_webui('antelope-webui', 8714, ORION)
                with self.assertRaisesRegex(RuntimeError, 'already in use'):
                    self.launcher.ensure_webui('antelope-webui', 8714, ZEN_GO)
            with patch.dict(self.globals, {'probe': lambda port: (True, None)}):
                with self.assertRaisesRegex(RuntimeError, 'already in use'):
                    self.launcher.ensure_webui('antelope-webui', 8714, None)
            start.assert_not_called()

    def test_starts_service_on_free_port_and_waits_for_profile(self):
        observations = iter([(False, None), (False, None), (True, ZEN_GO)])
        with patch.dict(self.globals, {'probe': lambda port: next(observations)}), \
                patch.object(self.launcher.subprocess, 'run') as start, \
                patch.object(self.launcher.time, 'sleep'):
            self.launcher.ensure_webui('antelope-webui@zen', 8721, ZEN_GO)
        start.assert_called_once_with(
            ['systemctl', '--user', 'start', '--', 'antelope-webui@zen.service'], check=True)

    def test_probe_requires_the_webui_profile_shape(self):
        with patch.object(self.launcher.http.client, 'HTTPConnection') as constructor:
            http = constructor.return_value
            http.getresponse.return_value.status = 200
            http.getresponse.return_value.read.return_value = (
                b'{"device":{"vid":"0x23e5","pid":"0xa221"},"webui":{}}')
            self.assertEqual(self.launcher.probe(8714), (True, ORION))
            http.request.assert_called_with('GET', '/api/profile')
            http.getresponse.return_value.read.return_value = b'{"device":{}}'
            self.assertEqual(self.launcher.probe(8714), (True, None))
            http.connect.side_effect = ConnectionRefusedError
            self.assertEqual(self.launcher.probe(8714), (False, None))


if __name__ == '__main__':
    unittest.main()
