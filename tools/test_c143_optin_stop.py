import signal,tempfile,json,sys
from pathlib import Path
from unittest.mock import patch,MagicMock
import unittest

import c143_slots40_optin as launcher
import run_bounded
from c2_gate import GateError
class StopIdentity(unittest.TestCase):
 def exercise(self,changed):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'raw').mkdir();rid='tesy-optin-slots40-fixture'
   expected={'pid':432123,'start_ticks':100,'cgroup_path':'/user/'+rid+'.service','cgroup_inode':123}
   launch=root/'raw'/f'{rid}.launch.json';launch.write_text(json.dumps({'process_identity':expected}))
   preset={'run_id':rid,'server_command':['/bin/true']}
   actual={**expected,'start_ticks':101} if changed else expected
   kill=MagicMock()
   with patch.object(launcher,'verified',return_value=preset),patch.object(run_bounded,'process_identity',return_value=actual),patch.object(launcher.os.path,'realpath',return_value='/bin/true'),patch.object(launcher.os,'killpg',kill):
    if changed:
     with self.assertRaises(GateError):launcher.stop(root)
     kill.assert_not_called();self.assertFalse((root/'raw'/f'{rid}.owner-stop.json').exists())
    else:
     launcher.stop(root);kill.assert_called_once_with(expected['pid'],signal.SIGINT)
     self.assertEqual(json.loads((root/'raw'/f'{rid}.owner-stop.json').read_text())['status'],'INTERRUPTED_BY_OWNER')
 def test_reused_pid_cannot_be_stopped(self):self.exercise(True)
 def test_matching_own_identity_records_owner_stop(self):self.exercise(False)
if __name__=='__main__':unittest.main()
