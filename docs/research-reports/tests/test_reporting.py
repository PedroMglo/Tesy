"""Model-free documentary fault tests. No inference validation is implied."""
import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(ROOT.parents[1]/'tools'))
import reportlib as r
import build_report as b
import new_campaign as n
import release_candidates as rc
C2='C02-correctness-usability'

class Primitives(unittest.TestCase):
    def test_duplicate_json(self):
        with self.assertRaisesRegex(r.EvidenceError,'DUPLICATE'):r.strict_json(b'{"a":1,"a":2}')
    def test_nested_duplicate(self):
        with self.assertRaises(r.EvidenceError):r.strict_json(b'{"x":{"a":1,"a":2}}')
    def test_nonfinite(self):
        for text in [b'NaN',b'Infinity',b'-Infinity',b'1e999']:
            with self.subTest(text=text),self.assertRaises(r.EvidenceError):r.strict_json(text)
    def test_bad_json_utf8(self):
        for text in [b'\xff',b'{',b'{"x":1,}']:
            with self.subTest(text=text),self.assertRaises(r.EvidenceError):r.strict_json(text)
    def test_pointer_escape(self):
        x={'a/b':{'~':3},'':4};self.assertEqual(r.pointer(x,'/a~1b/~0'),3);self.assertEqual(r.pointer(x,'/'),4);self.assertEqual(r.pointer(x,''),x)
    def test_pointer_refuses_alias(self):
        for p in ['x','/absent','/a/~2','/a/00','/a/-','/a/9']:
            with self.subTest(p=p),self.assertRaises(r.EvidenceError):r.pointer({'a':[2]},p)
    def test_units(self):
        self.assertEqual(r.convert(2**30,'B','GiB'),1);self.assertEqual(r.convert(10**9,'B','GB'),1)
        self.assertEqual(r.convert(7000,'MiB','GiB'),6.8359375);self.assertEqual(r.convert(60,'s','min'),1)
    def test_invalid_units(self):
        for raw,u in [('B','s'),('token/s','GiB')]:
            with self.subTest(raw=raw),self.assertRaises(r.EvidenceError):r.convert(1,raw,u)
    def test_paths(self):
        with tempfile.TemporaryDirectory() as td:
            for p in ['.','../x','/tmp/x','a/../b','a//b','a/./b','a\\b','a:b']:
                with self.subTest(p=p),self.assertRaises(r.EvidenceError):r.safe(Path(td),p)
    def test_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'link').symlink_to('/tmp',target_is_directory=True)
            with self.assertRaisesRegex(r.EvidenceError,'SYMLINK'):r.safe(root,'link/x')
    def test_atomic_no_replace(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);a=root/'a';z=root/'z';a.mkdir();(a/'x').write_text('original');r.publish_no_replace(a,z)
            a.mkdir();(a/'x').write_text('new')
            with self.assertRaises(r.EvidenceError):r.publish_no_replace(a,z)
            self.assertEqual((z/'x').read_text(),'original');self.assertEqual((a/'x').read_text(),'new')
    def test_canonical(self):self.assertEqual(r.canonical({'b':2,'a':1}),r.canonical({'a':1,'b':2}))
    def test_escape(self):
        x=r.escape('a_b%&$#{}'+chr(92));self.assertIn(r'\_',x);self.assertIn(r'\%',x);self.assertIn(r'\textbackslash{}',x)

class Pipeline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'reports'
        shutil.copytree(ROOT,self.root,ignore=shutil.ignore_patterns('_build','published','__pycache__','*.pyc'))
        self.d=self.root/'campaigns'/C2
    def tearDown(self):self.temp.cleanup()
    def result(self):return r.verify(self.root,C2)
    def edit(self,file,fn):
        p=self.d/file;v=r.read(p);fn(v);p.write_bytes(r.canonical(v))
    def med(self,fn):self.edit('evidence-spec.json',lambda s:fn(s['metrics'][0]))
    def audit(self,digest,pdf=b'PDF-FIXTURE'):
        a={'schema_version':'tesy-audit-v1','inputs_sha256':digest,'reviewed_pdf_sha256':r.sha(pdf),'status':'REVIEWED',
           'reviewer':'SYNTHETIC TEST FIXTURE','scientific_endorsement':False,'claims_reviewed':True,
           'all_pages_visually_reviewed':True,'open_blockers':[],'notes':['Not a real visual audit.']}
        (self.d/'audit.json').write_bytes(r.canonical(a))
    def test_c2_blocked_valid(self):
        v=self.result();self.assertEqual(v['meta']['scientific_state'],'CORRECTNESS_BLOCKED')
        self.assertEqual(v['lock']['experimental_reproduction'],'NOT_RUN');self.assertEqual(v['lock']['raw_data_availability'],'NOT_ACCESSED')
        self.assertEqual(v['lock']['checks_passed'],7);self.assertEqual(v['values']['M-C2-CASES']['value'],12)
        self.assertEqual(v['values']['M-C2-HOST-PEAK']['value'],15344664576/2**30)
    def test_c1_original(self):
        v=r.verify(self.root,'C01-scale-lab');self.assertEqual(v['meta']['scientific_state'],'SUCCESS')
        self.assertEqual(v['lock']['sources'][0]['commit'],'c67529e290844bb3d9033615072d5878014a46bc')
        self.assertEqual(v['values']['M-C1-UTILITY-PASS']['value'],8)
    def test_automatic_release_candidate_is_reviewed_and_versioned(self):
        self.assertEqual(rc.candidates(self.root),[
            ('C03-boundary-prefill','1.0.0','reports-C03-boundary-prefill-v1.0.0'),
            ('C02-correctness-usability','1.0.0','reports-C02-correctness-usability-v1.0.0'),
            ('C01-scale-lab','1.0.0','reports-C01-scale-lab-v1.0.0'),
            ('R00-foundations','1.0.0','reports-R00-foundations-v1.0.0'),
            ('D00-research-dossier','1.0.0','reports-D00-research-dossier-v1.0.0'),
        ])
    def test_automatic_release_candidate_requires_reviewed_audit(self):
        p=self.root/'campaigns'/'C03-boundary-prefill'/'audit.json';a=r.read(p);a['status']='DRAFT';p.write_bytes(r.canonical(a))
        with self.assertRaisesRegex(r.EvidenceError,'AUTO_RELEASE_REQUIRES_REVIEWED_AUDIT'):rc.candidates(self.root)
    def test_extra_field(self):
        self.edit('campaign.json',lambda m:m.update(unknown=True))
        with self.assertRaisesRegex(r.EvidenceError,'SCHEMA'):self.result()
    def test_invalid_date(self):
        self.edit('campaign.json',lambda m:m.update(date='2026-02-30'))
        with self.assertRaisesRegex(r.EvidenceError,'INVALID_REPORT_DATE'):self.result()
    def test_promoted_state(self):
        self.edit('campaign.json',lambda m:m.update(scientific_state='PASS'))
        with self.assertRaisesRegex(r.EvidenceError,'SCIENTIFIC_STATE_MISMATCH'):self.result()
    def test_duplicate_metric(self):
        self.edit('evidence-spec.json',lambda s:s['metrics'].append(copy.deepcopy(s['metrics'][0])))
        with self.assertRaisesRegex(r.EvidenceError,'DUPLICATE_ID'):self.result()
    def test_duplicate_source_alias(self):
        p=self.root/'sources/catalog.json';s=r.read(p);x=copy.deepcopy(s['sources'][0]);x['id']='E-ALIAS';s['sources'].append(x);p.write_bytes(r.canonical(s))
        with self.assertRaisesRegex(r.EvidenceError,'DUPLICATE_SOURCE_ALIAS'):self.result()
    def test_corrupt_byte(self):
        s=self.result()['catalog']['E-C2-GATE'];p=self.root/'sources/objects'/(s['sha256']+'.source');data=p.read_bytes();p.write_bytes(b'X'+data[1:])
        with self.assertRaisesRegex(r.EvidenceError,'SHA256_MISMATCH'):self.result()
    def test_source_missing(self):
        s=self.result()['catalog']['E-C2-GATE'];(self.root/'sources/objects'/(s['sha256']+'.source')).unlink()
        with self.assertRaisesRegex(r.EvidenceError,'SOURCE_UNAVAILABLE'):self.result()
    def test_source_truncated(self):
        s=self.result()['catalog']['E-C2-GATE'];p=self.root/'sources/objects'/(s['sha256']+'.source');p.write_bytes(p.read_bytes()[:-1])
        with self.assertRaisesRegex(r.EvidenceError,'SIZE_MISMATCH'):self.result()
    def test_blob_sha(self):
        p=self.root/'sources/catalog.json';s=r.read(p);s['sources'][0]['git_blob_sha1']='0'*40;p.write_bytes(r.canonical(s))
        with self.assertRaisesRegex(r.EvidenceError,'GIT_BLOB_MISMATCH'):self.result()
    def test_old_summary_wrong_path(self):
        self.edit('evidence-spec.json',lambda s:s['source_contracts'][0].update(path='results/campaign-summary.json'))
        with self.assertRaisesRegex(r.EvidenceError,'AUTHORITY_PATH_MISMATCH'):self.result()
    def test_unpinned_commit(self):
        self.edit('campaign.json',lambda m:m.update(evidence_snapshot_commits=['0'*40]))
        with self.assertRaisesRegex(r.EvidenceError,'UNPINNED_COMMIT'):self.result()
    def test_identity_condition(self):
        def change(s):next(x for x in s['source_contracts'] if x['json_values'])['json_values'][0]['expected']='WRONG'
        self.edit('evidence-spec.json',change)
        with self.assertRaisesRegex(r.EvidenceError,'AUTHORITY_IDENTITY_MISMATCH'):self.result()
    def test_missing_pointer(self):
        self.med(lambda m:m.update(extract={'type':'json','source':'E-C2-GATE','pointer':'/absent'}))
        with self.assertRaisesRegex(r.EvidenceError,'MISSING_POINTER'):self.result()
    def test_boolean_not_number(self):
        def change(s):
            x=next(m for m in s['metrics'] if m['extract'].get('source')=='E-C2-SUMMARY');x['extract']['pointer']='/performance/goal_4_tok_s_met'
        self.edit('evidence-spec.json',change)
        with self.assertRaisesRegex(r.EvidenceError,'NOT_FINITE_NUMERIC'):self.result()
    def test_wrong_conversion(self):
        self.med(lambda m:m.update(unit='GiB'))
        with self.assertRaisesRegex(r.EvidenceError,'INVALID_UNIT_CONVERSION'):self.result()
    def test_wrong_dataset_unit(self):
        self.edit('evidence-spec.json',lambda s:s['datasets'][0]['columns'][0].update(unit='GiB'))
        with self.assertRaisesRegex(r.EvidenceError,'DATASET_UNIT_MISMATCH'):self.result()
    def test_duplicate_dataset_label(self):
        self.edit('evidence-spec.json',lambda s:s['datasets'][0]['rows'].append(copy.deepcopy(s['datasets'][0]['rows'][0])))
        with self.assertRaisesRegex(r.EvidenceError,'DUPLICATE_ID'):self.result()
    def test_crosscheck_conflict(self):
        self.edit('evidence-spec.json',lambda s:s['checks'].append({'type':'equal','left':'M-C2-DECODE','right':'M-C2-SECOND-HALF','atol':0}))
        with self.assertRaisesRegex(r.EvidenceError,'CROSSCHECK_CONFLICT'):self.result()
    def test_hash_link_conflict(self):
        def change(s):next(x for x in s['checks'] if x['type']=='hash-link')['target']='E-C2-SUMMARY'
        self.edit('evidence-spec.json',change)
        with self.assertRaisesRegex(r.EvidenceError,'HASH_LINK_CONFLICT'):self.result()
    def test_cycle(self):
        self.med(lambda m:m.update(extract={'type':'ratio','inputs':[m['id'],m['id']]}))
        with self.assertRaisesRegex(r.EvidenceError,'METRIC_CYCLE'):self.result()
    def test_wrong_authority(self):
        self.med(lambda m:m.update(family='wrong'))
        with self.assertRaisesRegex(r.EvidenceError,'SOURCE_NOT_AUTHORITATIVE'):self.result()
    def test_withdrawn_promoted(self):
        self.edit('evidence-spec.json',lambda s:[x.update(status='WITHDRAWN') for x in s['claims']])
        with self.assertRaisesRegex(r.EvidenceError,'NONCURRENT_CLAIM_PROMOTED'):self.result()
    def test_missing_claim(self):
        p=self.d/'sections/01-summary.tex';p.write_text(p.read_text()+r'\claim{CL-MISSING}{x}')
        with self.assertRaisesRegex(r.EvidenceError,'UNKNOWN_TEX_CLAIM'):self.result()
    def test_missing_section(self):
        (self.d/'sections/07-failures.tex').unlink()
        with self.assertRaisesRegex(r.EvidenceError,'MISSING_SECTION'):self.result()
    def test_unsafe_tex_primitive(self):
        p=self.d/'sections/01-summary.tex';p.write_text(p.read_text()+r'\write18{foo}')
        with self.assertRaisesRegex(r.EvidenceError,'UNSAFE_TEX'):self.result()
    def test_roundtrip_derive(self):
        v=self.result();r.derive(v);r.check_derived(v);before=(self.d/'generated/values.json').read_bytes();r.derive(self.result());self.assertEqual(before,(self.d/'generated/values.json').read_bytes())
    def test_stale_derived(self):
        v=self.result();r.derive(v);p=self.d/'generated/metrics.tex';p.write_text(p.read_text()+'% changed\n')
        with self.assertRaisesRegex(r.EvidenceError,'DERIVED_STALE'):r.check_derived(v)
    def test_extra_generated(self):
        v=self.result();r.derive(v);(self.d/'generated/rogue').write_text('x')
        with self.assertRaisesRegex(r.EvidenceError,'DERIVED_FILE_SET_MISMATCH'):r.check_derived(v)
        with self.assertRaisesRegex(r.EvidenceError,'UNEXPECTED_GENERATED_FILES'):r.derive(v)
    def test_missing_lock(self):
        v=self.result();r.derive(v);(self.d/'evidence-lock.json').unlink()
        with self.assertRaisesRegex(r.EvidenceError,'MISSING_JSON'):r.check_derived(v)
    def test_changed_prose_invalidates(self):
        v=self.result();r.derive(v);p=self.d/'sections/01-summary.tex';p.write_text(p.read_text()+'\nEditorial change.\n');v2=self.result()
        self.assertNotEqual(v['lock']['inputs_sha256'],v2['lock']['inputs_sha256'])
        with self.assertRaises(r.EvidenceError):r.check_derived(v2)
    def test_release_needs_audit(self):
        r.derive(self.result());p=self.d/'audit.json'
        if p.exists():p.unlink()
        with self.assertRaisesRegex(r.EvidenceError,'MISSING_JSON'):b.build(self.root,C2,'release')
    def test_stale_audit(self):
        r.derive(self.result());self.audit('0'*64)
        with self.assertRaisesRegex(r.EvidenceError,'AUDIT_STALE'):b.build(self.root,C2,'release')
    def test_mock_release_preserves_blocked(self):
        v=self.result();r.derive(v);self.audit(v['lock']['inputs_sha256']);fake=(b'PDF-FIXTURE',b'log',[],self.root)
        with patch.object(b,'version',return_value='TEST'),patch.object(b,'compile_one',return_value=fake):
            dest=b.build(self.root,C2,'release',check_reproducible=True);m=r.read(dest/'release.json');self.assertEqual(m['scientific_state'],'CORRECTNESS_BLOCKED');self.assertEqual(m['experimental_reproduction'],'NOT_RUN')
            with self.assertRaisesRegex(r.EvidenceError,'PUBLICATION_EXISTS'):b.build(self.root,C2,'release')
    def test_reviewed_pdf_required(self):
        v=self.result();r.derive(v);self.audit(v['lock']['inputs_sha256']);fake=(b'UNREVIEWED',b'log',[],self.root)
        with patch.object(b,'version',return_value='TEST'),patch.object(b,'compile_one',return_value=fake):
            with self.assertRaisesRegex(r.EvidenceError,'PDF_DIFFERS_FROM_REVIEWED_ARTIFACT'):b.build(self.root,C2,'release')
    def test_concurrent_input_change(self):
        r.derive(self.result())
        def compile_changed(*args):
            p=self.d/'sections/01-summary.tex';p.write_text(p.read_text()+'\nChanged during build.\n');return b'PDF-FIXTURE',b'log',[],self.root
        with patch.object(b,'version',return_value='TEST'),patch.object(b,'compile_one',side_effect=compile_changed):
            with self.assertRaisesRegex(r.EvidenceError,'INPUTS_CHANGED_DURING_BUILD'):b.build(self.root,C2)
    def test_pdf_repro_mismatch(self):
        r.derive(self.result())
        with patch.object(b,'version',return_value='TEST'),patch.object(b,'compile_one',side_effect=[(b'A',b'log',[],self.root),(b'B',b'log',[],self.root)]):
            with self.assertRaisesRegex(r.EvidenceError,'PDF_BYTE_DIFFERENT'):b.build(self.root,C2,check_reproducible=True)
    def test_dossier_pin(self):
        d=self.root/'dossier/D00-research-dossier';p=d/'campaign.json';m=r.read(p);m['included_reports']=[{'id':C2,'version':'1.0.0','inputs_sha256':'0'*64}];p.write_bytes(r.canonical(m))
        with self.assertRaisesRegex(r.EvidenceError,'DOSSIER_INPUTS_STALE'):r.verify(self.root,m['id'])
    def test_new_skeleton_no_fake_result(self):
        p=n.create(self.root,'TEST-FUTURE','0'*40,'2026-09-26');self.assertEqual(r.read(p/'campaign.json')['scientific_state'],'NOT_RUN');self.assertEqual(r.read(p/'evidence-spec.json')['metrics'],[])
        with self.assertRaisesRegex(r.EvidenceError,'CAMPAIGN_EXISTS'):n.create(self.root,'TEST-FUTURE','0'*40,'2026-09-26')
    def test_git_missing_no_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(['git','init','-q',td],check=True)
            with self.assertRaisesRegex(r.EvidenceError,'GIT_SOURCE_UNAVAILABLE'):r.source_bytes(self.root,self.result()['catalog']['E-C2-GATE'],'git',Path(td))
    def test_partial_clone_refused(self):
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(['git','init','-q',td],check=True);subprocess.run(['git','-C',td,'config','remote.origin.promisor','true'],check=True)
            with self.assertRaisesRegex(r.EvidenceError,'PARTIAL_OR_UNREADABLE'):r.source_bytes(self.root,self.result()['catalog']['E-C2-GATE'],'git',Path(td))

if __name__=='__main__':unittest.main()
