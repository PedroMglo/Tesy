import copy,json,unittest
from pathlib import Path
from expert_compressibility_gate import evaluate

class CodecBoundary(unittest.TestCase):
    def data(self):
        index=json.loads(Path('results/c287-lossless-sample-producer-20261006/raw/sample-index.json').read_text());rows=[]
        for e in index['experts']:
            for c in e['components']:
                n=c['size_bytes'];r={k:e[k] for k in ('layer','tier','expert')};r.update({'name':c['name'],'source_offset':c['source_offset'],'source_sha256':c['sha256'],'logical_bytes':n,'exact_bytes':True,'encoded_bytes':n,'aligned_encoded_bytes':(n+4095)//4096*4096,'read_s':.001,'compress_s':.001,'decompress_to_ready_s':[.001]*4})
                if n==4406400:r['substreams']={'scale_bytes':259200,'qs_bytes':4147200,'scale_histogram':[259200]+[0]*255}
                rows.append(r)
        value={'schema':'tesy-fixed-zstd-characterization-v1','status':'PASS_CANONICAL_LOSSLESS_CHARACTERIZATION','zstd_version':'1.5.7','compression_level':1,'checksum':True,'codec_workers':0,'component_count':384,'source_fd_direct':True,'mapped_codec_libraries_sha256':{'zstd':'pinned','crypto':'pinned'},'components':rows,'offset_alignment':4096,'logical_bytes':sum(r['logical_bytes'] for r in rows),'elapsed_s':1}
        return value,index,value['mapped_codec_libraries_sha256']
    def test_complete_sample_has_no_false_savings(self):
        v,i,p=self.data();r=evaluate(v,i,p);self.assertEqual(r['status'],'PASS_FIXED_CANONICAL_CODEC_CHARACTERIZATION');self.assertLessEqual(r['conditional_zero_reconstruction_all_work_byte_service_upper_percent'],0)
    def test_missing_wrong_order_byte_identity_fails(self):
        for mutation in ('omitted','order','hash','exact'):
            v,i,p=self.data()
            if mutation=='omitted':v['components'].pop()
            elif mutation=='order':v['components'][0],v['components'][1]=v['components'][1],v['components'][0]
            elif mutation=='hash':v['components'][0]['source_sha256']='invented'
            else:v['components'][0]['exact_bytes']=False
            with self.assertRaises(ValueError):evaluate(v,i,p)
    def test_missing_nan_or_zero_timing_rejected(self):
        for times in ([.001]*3,[float('nan')]*4,[0]*4):
            v,i,p=self.data();v['components'][0]['decompress_to_ready_s']=times
            with self.assertRaises(ValueError):evaluate(v,i,p)
    def test_codec_mapping_and_direct_contract_required(self):
        for mutation in ('maps','direct','level','padding'):
            v,i,p=self.data()
            if mutation=='maps':v['mapped_codec_libraries_sha256']={}
            elif mutation=='direct':v['source_fd_direct']=False
            elif mutation=='level':v['compression_level']=3
            else:v['components'][0]['aligned_encoded_bytes']+=1
            with self.assertRaises(ValueError):evaluate(v,i,p)
if __name__=='__main__':unittest.main()
