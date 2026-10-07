import unittest
from expert_primary_state_replay import PrimaryState

class Replay(unittest.TestCase):
    def initial(self):return {'layers':[{'layer':l,'slot_expert':list(range(40)),'slot_state':[2]*40,'slot_generation':[1]*40} for l in range(36)]}
    def event(self,kind=4,gen=2):return {'kind':kind,'us':kind,'layer':2,'slot':0,'expert':42,'gen':gen}
    def test_reserve_evict_loading_commit(self):
        s=PrimaryState(self.initial(),[self.event(),self.event(10)]);s.advance(4)
        self.assertEqual(s.selected(2,[0,42]),[{'expert':0,'slot':-1,'state':0,'generation':0},{'expert':42,'slot':0,'state':1,'generation':2}]);s.advance(10);self.assertEqual(s.selected(2,[42])[0]['state'],2)
    def test_wrong_generation_missing_reserve_or_time(self):
        for rows in ([self.event(10)],[self.event(),self.event(10,3)],[self.event(4,1)]):
            with self.assertRaises(ValueError):PrimaryState(self.initial(),rows).advance(20)
        s=PrimaryState(self.initial(),[]);s.advance(10)
        with self.assertRaises(ValueError):s.advance(9)
    def test_final_not_silently_assumed(self):
        s=PrimaryState(self.initial(),[self.event(),self.event(10)])
        with self.assertRaises(ValueError):s.final(self.initial())
if __name__=='__main__':unittest.main()
