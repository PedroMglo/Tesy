import tempfile
from pathlib import Path
import unittest

from c55_inventory import ancestor_headroom

class AncestorTests(unittest.TestCase):
    def test_unbounded_root_but_bounded_child(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name); child=root/'user.slice';child.mkdir()
            (child/'memory.max').write_text(str(20*2**30))
            (child/'memory.current').write_text(str(2**30))
            remaining,rows=ancestor_headroom(32*2**30,root=root,rel='/user.slice')
            self.assertEqual(remaining,19*2**30)
            self.assertEqual(rows[-1]['memory_max'],'UNBOUNDED_ROOT')

if __name__=='__main__':unittest.main()
