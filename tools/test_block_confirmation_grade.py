import copy,json,unittest
from block_confirmation_grade import fixture,allocation_oracle,grade,code_envelope

class FrozenOracles(unittest.TestCase):
    def test_actual_isolated_python_positive_and_discriminating_negatives(self):
        correct='''def job_totals(events):
    latest = {}
    for event in events:
        if event['job'] not in latest or event['seq'] >= latest[event['job']]['seq']:
            latest[event['job']] = event
    teams = {}
    for event in latest.values():
        if event['state'] == 'cancel':
            continue
        count, minutes = teams.get(event['team'], (0, 0))
        teams[event['team']] = (count + 1, minutes + (event['minutes'] or 0))
    return [(team, *teams[team]) for team in sorted(teams)]
'''
        result=grade('confirm-code-job-totals',correct)
        self.assertEqual(result['status'],'PASS',result)
        mutants=[correct.replace(" >= latest", " > latest"),
                 correct.replace("if event['state'] == 'cancel':", "if False:"),
                 correct.replace("    latest = {}", "    events.reverse()\n    latest = {}")]
        for candidate in mutants:
            result=grade('confirm-code-job-totals',candidate)
            self.assertEqual(result['status'],'FAIL',result)
    def test_independent_oracles_positive_and_wrong_json_counterproofs(self):
        data=fixture();expected=data['bin_expected'];self.assertEqual(grade('confirm-json-bin-allocation',json.dumps(expected))['status'],'PASS')
        for kind in ('wrong_bin','missing_waiting','boolean','extra','duplicate_key'):
            value=copy.deepcopy(expected)
            if kind=='wrong_bin':value['assignments'][0]['bin']='A'
            if kind=='missing_waiting':value['waiting']=[]
            if kind=='boolean':value['remaining']['A']=False
            if kind=='extra':value['score']=1
            text=json.dumps(value)
            if kind=='duplicate_key':text=text[:-1]+',"remaining":{"A":0,"B":1,"C":1}}'
            self.assertEqual(grade('confirm-json-bin-allocation',text)['status'],'FAIL')
        self.assertEqual(grade('confirm-json-bin-allocation',json.dumps(expected),'length')['status'],'FAIL')
    def test_no_substring_extraction_or_reasoning_as_final(self):
        value=json.dumps(fixture()['bin_expected'])
        for text in ('```json\n'+value+'\n```','Explanation '+value,'',None):self.assertEqual(grade('confirm-json-bin-allocation',text)['status'],'FAIL')
        self.assertEqual(code_envelope('```python\ndef job_totals(events): pass\n```'),'def job_totals(events): pass')
        with self.assertRaises(ValueError):code_envelope('prose\n```python\ndef job_totals(events):pass\n```')

if __name__=='__main__':unittest.main()
