"""The model child must not outlive an abruptly lost runner."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


class ParentDeathTests(unittest.TestCase):
    def test_child_exits_when_runner_is_killed(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file=Path(directory)/'child.pid'
            code=("import os,subprocess,sys,time; "
                  "from c2_server_run import parent_death_guard; "
                  "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
                  "start_new_session=True,preexec_fn=parent_death_guard(os.getpid())); "
                  "open(sys.argv[1],'w').write(str(p.pid)); time.sleep(30)")
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='tools')
            parent=subprocess.Popen([sys.executable,'-c',code,str(pid_file)],env=env,
                                    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            child_pid=None
            try:
                deadline=time.monotonic()+5
                while not pid_file.exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertTrue(pid_file.exists(),'test runner did not launch child')
                child_pid=int(pid_file.read_text())
                self.assertTrue(Path(f'/proc/{child_pid}').exists())
                parent.kill();parent.wait(timeout=3)
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    status=Path(f'/proc/{child_pid}/stat')
                    try:
                        state=status.read_text().split()[2]
                    except (FileNotFoundError,ProcessLookupError):
                        break  # exit may remove /proc after the preceding poll
                    if state=='Z':
                        break
                    time.sleep(.02)
                else:
                    self.fail('guarded model child survived runner death')
            finally:
                if parent.poll() is None:
                    parent.kill();parent.wait(timeout=3)
                parent.stderr.close()
                if child_pid is not None:
                    try: os.kill(child_pid,signal.SIGKILL)
                    except ProcessLookupError: pass


if __name__=='__main__':
    unittest.main()
