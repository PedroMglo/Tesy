import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from run_bounded import backend_library_hashes,mapped_libraries_match,sha256
class LibraryIdentityTests(unittest.TestCase):
 def test_foreign_linked_ggml_is_frozen_and_extra_mapping_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'backend';root.mkdir();local=root/'libggml-base.so';local.write_bytes(b'local')
   foreign=Path(d)/'other';foreign.mkdir();cuda=foreign/'libggml-cuda.so';cuda.write_bytes(b'cuda');libc=foreign/'libc.so';libc.write_bytes(b'libc')
   listing='\n'.join(f'{f.name} => {f} (0x0)' for f in (local,cuda,libc))
   with patch('run_bounded.subprocess.check_output',return_value=listing):expected=backend_library_hashes('fixture',root)
   self.assertEqual(expected,{'libggml-base.so':sha256(local),str(cuda):sha256(cuda)})
   self.assertTrue(mapped_libraries_match(expected,dict(expected)))
   self.assertFalse(mapped_libraries_match(expected,{'libggml-base.so':sha256(local)}))
   self.assertFalse(mapped_libraries_match(expected,{**expected,'/unknown/libggml.so':'bad'}))
 def test_plain_dummy_cannot_satisfy_backend_identity(self):
  self.assertFalse(mapped_libraries_match({},{}))
if __name__=='__main__':unittest.main()
