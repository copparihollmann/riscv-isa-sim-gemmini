"""Analyze complete archived failing outputs; does not admit failed-run timing."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
sys.path.insert(0,'/scratch/copparihollmann/merlin-gather-compat-integration-v1/src')
from merlin.runtime.out_b64 import OutB64Decoder

A=Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')
W=A/'attention-recovery-20261111-v1'
J=Path('/scratch/copparihollmann/private-iris-runs/approved-operator-campaign-20261110-v1/attention_handoff42-20261111-v1')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('attention_archive',W/'managed-tools/archive_integrity.py')
    archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
    run=json.loads((J/'run.json').read_text());integrity,uart,_=archive.verify(J,run['elf_sha256'])
    (out/'archive-integrity.json').write_text(json.dumps(integrity,indent=2)+'\n')
    outputs={};decoder=OutB64Decoder()
    for line in uart.decode().splitlines():decoder.consume(line.split(),outputs)
    decoder.require_closed()
    metadata=json.loads((A/'attn/i8-only-next3-v1/build.json').read_text())
    pins={str(Path(__file__).resolve()):sha(__file__)};results=[]
    for name,words in outputs.items():
        case=int(name.split('_')[1][1:]);meta=metadata['cases_meta'][case]
        oracle_path=Path(meta['oracle_reports'][0]);oracle=json.loads(oracle_path.read_text());pins[str(oracle_path)]=sha(oracle_path)
        expected_path=Path(oracle['expected']['path']);assert sha(expected_path)==oracle['expected']['sha256'];pins[str(expected_path)]=sha(expected_path)
        shape=oracle['expected']['shape'];actual=np.array(words,dtype='<u4').reshape(shape);expected=np.frombuffer(expected_path.read_bytes(),dtype='<u4').reshape(shape)
        (out/(name+'.u32.bin')).write_bytes(actual.tobytes())
        coordinates=np.argwhere(actual!=expected);row=dict(name=name,shape=shape,mismatch_words=int(len(coordinates)),
                                                          actual_sha256=hashlib.sha256(actual.tobytes()).hexdigest(),mismatch_rows=[])
        for batch,head,query in sorted({tuple(map(int,c[:3]))for c in coordinates}):
            headmeta=next(x for x in oracle['heads']if x['batch']==batch and x['query_head']==head)
            def read(ref,dtype):
                p=Path(ref['path']);assert sha(p)==ref['sha256'];pins[str(p)]=sha(p);return np.frombuffer(p.read_bytes(),dtype=dtype).reshape(ref['shape'])
            qP=read(headmeta['arrays']['qP'],'i1');sP=read(headmeta['arrays']['sP'],'<f4')
            kv=headmeta['KV_head'];qvt_path=oracle_path.parent/f'b{batch}_kv{kv}_qVt.bin';sv_path=oracle_path.parent/f'b{batch}_kv{kv}_sV.bin'
            qvt=np.frombuffer(qvt_path.read_bytes(),dtype='i1').reshape(shape[-1],oracle['parameters']['Lkv']);sv=np.frombuffer(sv_path.read_bytes(),dtype='<f4')
            pins[str(qvt_path)]=sha(qvt_path);pins[str(sv_path)]=sha(sv_path)
            cp=(qP.astype(np.int64)@qvt.astype(np.int64).T).astype(np.int32)
            recomputed=(cp.astype(np.float32)*sP[:,None])*sv[None,:]
            assert np.array_equal(recomputed.view(np.uint32),expected[batch,head]),'Cached quantizedV/scales do not reproduce oracle PV'
            a=actual[batch,head,query].view(np.float32);e=expected[batch,head,query].view(np.float32)
            factor=float(np.dot(a.astype(float),e.astype(float))/np.dot(e.astype(float),e.astype(float)))
            scaling_residual=float(np.linalg.norm(a.astype(float)-factor*e.astype(float))/np.linalg.norm(a.astype(float)))
            estimated_cp=np.rint(a.astype(np.float64)/(np.float64(sP[query])*sv.astype(np.float64))).astype(np.int64)
            candidate=(estimated_cp.astype(np.float32)*sP[query])*sv
            exact_cp_matches=int(np.count_nonzero(candidate.view(np.uint32)==a.view(np.uint32)))
            delta=estimated_cp-cp[query].astype(np.int64);single=[]
            if exact_cp_matches==a.size:
                for position in range(qP.shape[1]):
                    basis=qvt[:,position].astype(np.int64);nonzero=np.flatnonzero(basis)
                    if len(nonzero):
                        idx=nonzero[0]
                        if delta[idx]%basis[idx]==0:
                            coefficient=int(delta[idx]//basis[idx])
                            if coefficient and np.array_equal(delta,coefficient*basis):
                                encoded=int(qP[query,position])+coefficient
                                single.append(dict(position=position,expected_qP=int(qP[query,position]),delta=coefficient,candidate_qP=encoded,within_int8=-128<=encoded<=127))
            copy_matches=[]
            flat=expected.reshape(-1,shape[-1]);same=np.flatnonzero(np.all(flat==actual[batch,head,query],axis=1))
            for i in same.tolist():copy_matches.append(list(map(int,np.unravel_index(i,shape[:-1]))))
            detail=dict(batch=batch,head=head,query=query,mismatching_channels=np.flatnonzero(actual[batch,head,query]!=expected[batch,head,query]).tolist(),
                        best_common_scale_factor=factor,relative_residual_after_common_scale=scaling_residual,
                        same_scale_integer_dot_forward_bit_matches=exact_cp_matches,
                        single_quantized_probability_byte_explanations=single,exact_other_output_row_copy_matches=copy_matches,
                        expected_probability_scale=float(sP[query]),estimated_integer_dot_delta=delta.tolist())
            row['mismatch_rows'].append(detail)
        results.append(row)
    report=dict(schema='iris.failed_attention_full_output_forensics.v1',archive_sha256=integrity['archive_sha256'],outputs=results,
                performance_admitted=False,root_cause_proven=False,hardware_actions=False,
                assumptions='Integer-dot reconstruction assumes original probability-row and value-channel scales. Exact forward bit matches test consistency, not uniqueness.',
                evidence_sha256=pins)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items()if k!='evidence_sha256'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
