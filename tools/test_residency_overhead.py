import unittest
from residency_overhead_analyze import paired
class PairedOverhead(unittest.TestCase):
 def test_pair_percentages_and_phase_protection(self):
  a={'prefix-warmup':100,'warm-prefill':10,'decode':10};b={'prefix-warmup':102,'warm-prefill':10.4,'decode':10.4}
  c={'prefix-warmup':200,'warm-prefill':20,'decode':20};d={'prefix-warmup':206,'warm-prefill':21.2,'decode':20.8}
  r=paired([(a,b),(c,d)]);self.assertAlmostEqual(r['median_overhead_percent']['warm-prefill'],5);self.assertEqual(r['status'],'TEMPORAL_OVERHEAD_GATE_PASS')
  d['decode']=24;r=paired([(a,b),(c,d)]);self.assertEqual(r['status'],'STATE_COUNTS_ONLY_OVERHEAD_GATE_NO_GO')
 def test_incomplete_pairs_rejected(self):
  with self.assertRaises(ValueError):paired([])
if __name__=='__main__':unittest.main()
