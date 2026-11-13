#!/usr/bin/env python3
"""Require independent frontend proof to reject corrupted source observations."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import analyze

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    run=ROOT/'build/frontend-phase-clock512-v3';probe=ROOT/'build/scalar-component-validation-plan-v2/alu512/build.json'
    reference=ROOT/'build/scalar-component-validation-e060-v1/alu512';data=json.loads(probe.read_text());ranges=[r['counter_pcs'] for r in data['compiled_body_validation']]
    original=Path.open;results=[];target=run/'phase.jsonl'
    for kind,expected in [('lfsr','source LFSR step mismatch'),('tag','refill did not install actual physical tag'),
                          ('valid','refill did not install actual physical tag'),('body','retired body instruction differs'),
                          ('queue','fetch-buffer pointer is not onehot7'),('counter','source counter edge rule disagrees')]:
        mutated=[False]
        class Corrupt:
            def __init__(self,stream):self.stream=stream
            def __iter__(self):return self
            def __next__(self):
                line=next(self.stream)
                if mutated[0]:return line
                r=json.loads(line);b=r['before'];a=r['after'];selected=False
                if kind=='lfsr' and not b['cache_refill_valid'] and a['cache_refill_valid'] and r['time_ps']>1000:
                    a['cache_replacement_state']^=1;selected=True
                elif kind in ('tag','valid') and b['cache_refill_done'] and r['time_ps']>1000:
                    key='cache_index_'+('tag' if kind=='tag' else 'valid')+str(b['cache_replacement_way']);a[key]=a[key]^1 if kind=='tag' else 0;selected=True
                elif kind=='body' and r['kind']>=0 and b['retire0'] and ranges[r['kind']][1]<b['com0_pc']<ranges[r['kind']][2]:
                    b['com0_raw']^=0x10000;selected=True
                elif kind=='queue' and r['kind']>=0:b['fb_deq_ptr']=0;selected=True
                elif kind=='counter' and r['kind']>=0:a['mc']^=1;selected=True
                if selected:mutated[0]=True;return json.dumps(r)+'\n'
                return line
            def __del__(self):self.stream.close()
        def opening(path,*a,**k):
            stream=original(path,*a,**k)
            return Corrupt(stream) if path.resolve()==target else stream
        with patch.object(Path,'open',opening):
            try:analyze.audit(run,probe,reference,None)
            except ValueError as error:
                if expected not in str(error) or not mutated[0]:raise
                results.append(dict(name=kind,rejected=True,error=str(error)))
            else:raise RuntimeError('corrupted source witness accepted: '+kind)
    original_sha=analyze.sha
    def bad_signature(path):return '0'*64 if Path(path).resolve()==run/'signature' else original_sha(path)
    with patch.object(analyze,'sha',bad_signature):
        try:analyze.audit(run,probe,reference,None)
        except ValueError as error:
            if 'changed coherent output' not in str(error):raise
            results.append(dict(name='coherent_signature',rejected=True,error=str(error)))
        else:raise RuntimeError('corrupt coherent signature accepted')
    out=ROOT/'build/frontend-phase-rejections-v1';out.mkdir(exist_ok=True,parents=True)
    report=dict(schema='iris.frontend_observer.rejections.v1',status='passed_adversarial_frontend_proof_controls',results=results,
                input_sha256={str(p):sha(p) for p in [Path(__file__).resolve(),Path(analyze.__file__).resolve(),run/'results.json',probe,reference/'results.json']},
                original_target_files_modified=False,hardware_contacted=False,rtl_design_changed=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rejected=len(results))))


if __name__=='__main__':main()
