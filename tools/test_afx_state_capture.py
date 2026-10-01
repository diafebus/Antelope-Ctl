"""Offline checks for bounded API capture, privacy and connection changes."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.afx_state_capture import read_snapshot, record


class AfxStateCaptureTests(unittest.TestCase):
    def test_snapshot_uses_read_endpoint_and_excludes_identity_and_extra_channels(self):
        state = {'available':True, 'online':True, 'session':3, 'links':[True]*16,
            'serial':'PRIVATE', 'effects':[{'token':'PRIVATE'}],
            'channels':{'0':[{'type':73,'instance':0,'serial':'PRIVATE'}],
                        '1':[{'type':73,'instance':1}], '2':[{'type':73,'instance':2}]},
            'parameter_states':{'0':{'values':dict.fromkeys(
                ('blend','level','feedback','chrs_vibr','depth','delay','lpf_fc','size'),0),
                'bypassed':False, 'token':'PRIVATE'}}}
        with patch('tools.afx_state_capture.urlopen', return_value=io.BytesIO(json.dumps(state).encode())) as request:
            snapshot = read_snapshot('http://localhost:8714', 0)
        self.assertEqual(request.call_args.args, ('http://localhost:8714/api/afx/memorycat-test?channel=0&refresh=true',))
        self.assertEqual(set(snapshot['chains']), {'0','1'})
        self.assertNotIn('PRIVATE', json.dumps(snapshot))
        self.assertEqual(snapshot['memorycat_states']['0']['source'], 'readback')

    def test_connection_change_stops_recording_without_mixing_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'states.jsonl'
            with patch('tools.afx_state_capture.read_snapshot', side_effect=[{'session':1},{'session':2}]), patch('tools.afx_state_capture.time.sleep'):
                with self.assertRaisesRegex(RuntimeError, 'connection changed'):
                    record('http://localhost:8714',0,60,1,output)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertFalse(rows[0]['device_writes'])
            self.assertEqual([row['session'] for row in rows if row['kind']=='state'], [1])


if __name__ == '__main__':
    unittest.main()
