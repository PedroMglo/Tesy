import unittest
from types import SimpleNamespace
from enum import IntEnum
import numpy as np
from block_eagle3_conversion_gate import rope_rows,compare


class Types(IntEnum):
    F32=0
    BF16=30
    F16=1


class IndependentHeadBytes(unittest.TestCase):
    def test_split_half_mapping_explicit_rows(self):
        self.assertEqual(rope_rows((8,2),2).tolist(),[0,2,1,3,4,6,5,7])
        with self.assertRaises(ValueError):rope_rows((7,2),2)

    def test_dtype_values_shapes_corruption_are_not_tolerated(self):
        values=np.array([0x3f80,0xc000,0x0001],dtype='<u2')
        t=SimpleNamespace(shape=np.array([3]),tensor_type=Types.BF16,data=values.view(np.uint8))
        self.assertTrue(compare(values,t,Types)['exact_source_values'])
        t.data=np.array([0x3f81,0xc000,0x0001],dtype='<u2').view(np.uint8)
        with self.assertRaises(ValueError):compare(values,t,Types)
        t.tensor_type=Types.F32;t.data=(values.astype('<u4')<<16).view('<f4')
        self.assertTrue(compare(values,t,Types)['exact_source_values'])
        t.tensor_type=Types.F16
        with self.assertRaises(ValueError):compare(values,t,Types)
        t.tensor_type=Types.BF16;t.shape=np.array([2])
        with self.assertRaises(ValueError):compare(values,t,Types)


if __name__=='__main__':unittest.main()
