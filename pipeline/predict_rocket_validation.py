#!/usr/bin/env python3
"""Freeze component predictions from an immutable model before RTL observations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions
from iris_model.counter_regions import observations
from spike.run_functional import symbols
MASK=(1<<64)-1
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_contract(elf,count,build):
    table=symbols(elf);image=Instructions(elf);contracts=[]
    for kind,label in enumerate(('scalar_dep_body','scalar_ind_body')):
        registers={0:0};reads=[];body=[];pc=table[label]
        for _ in range(count+128):
            word=image.read(pc);rd=(word>>7)&31;rs=(word>>15)&31
            if word&3!=3:raise ValueError('component probe has compressed control/body')
            if word&127==0x73:
                if word&0xfffff07f not in (0xb0002073,0xb0202073):raise ValueError('component counter encoding changed')
                reads.append(dict(pc=pc,raw=word,csr=word>>20))
                if len(reads)==4:break
            else:
                if word&0x707f!=0x13 or rs not in registers:raise ValueError('component arithmetic depends on unknown state')
                imm=word>>20;imm-=4096 if imm&2048 else 0
                if len(reads)==2:
                    if rd==0 or rd!=rs or imm!=1:raise ValueError('component body is not independent increment chains')
                    body.append(rd)
                if rd:registers[rd]=(registers[rs]+imm)&MASK
            pc+=4
        if len(reads)!=4 or [r['csr'] for r in reads]!=[0xb00,0xb02,0xb02,0xb00] or len(body)!=count:
            raise ValueError('component body/bracket mismatch')
        if len(set(body))!=(min(count,8) if kind else int(count>0)):raise ValueError('component chain count mismatch')
        checksum=registers[5] if kind==0 else sum(registers[r] for r in (5,6,7,28,12,13,14,15))&MASK
        if checksum!=build['expected_checksums'][kind] or [r['pc'] for r in reads]!=build['compiled_body_validation'][kind]['counter_pcs']:
            raise ValueError('independent compiled-body checksum disagrees with frozen plan')
        contracts.append(dict(kind=kind,label=label,reads=reads,checksum=checksum,body_operations=len(body)))
    return contracts


def signature(path,count,contracts):
    lines=path.read_text().splitlines()
    if len(lines)!=56 or any(not re.fullmatch('[0-9a-f]{16}',s) for s in lines):raise ValueError('component signature is not exact448bytes')
    words=[int(s,16) for s in lines]
    if words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('component mailbox failed/incomplete')
    rows=[]
    for hart in range(3):
        for kind in range(2):
            begin,end,ibegin,iend,checksum,ops,pad0,pad1=words[8+hart*16+kind*8:16+hart*16+kind*8]
            expected_ir=count+int(hart==2)
            if end<=begin or (iend-ibegin)&MASK!=expected_ir or checksum!=contracts[kind]['checksum'] or ops!=count or pad0 or pad1:
                raise ValueError('component predicted signature/counter/checksum contract failed')
            rows.append(dict(hart=hart,kind=kind,kernel='dependent' if kind==0 else 'eight_chains',operations=count,
                             start_cycle=begin,end_cycle=end,cycles=end-begin,instret_delta=(iend-ibegin)&MASK,checksum=checksum))
    return rows


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--plan',type=Path,default=ROOT/'build/scalar-component-validation-plan-v2/plan.json')
    p.add_argument('--model',type=Path,default=ROOT/'build/rocket-pipeline-frozen-91c40461')
    p.add_argument('--fixture',type=Path)
    p.add_argument('--reference-results-blinded',action='store_true',help='Other agents may already have measurements; predicting agent has not received/viewed them')
    p.add_argument('--output',type=Path,default=ROOT/'build/scalar-component-predictions-rocket-v1');a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);(out/'inputs').mkdir();started=datetime.now(timezone.utc).isoformat()
    plan=json.loads(a.plan.read_text());model=json.loads((a.model/'manifest.json').read_text())
    if plan['reference_timings_observed'] or plan['model_predictions_frozen']:raise ValueError('component plan is no longer blinded/unpredicted')
    if model['binary_sha256']!=sha(a.model/'spike') or model['uart_sha256']!=sha(a.model/'libsifive_uart.so'):raise ValueError('closed model bytes changed')
    inputs={};results=[]
    def retain(path,digest=None):
        path=Path(path).resolve();actual=sha(path)
        if digest is not None and digest!=actual:raise ValueError('frozen component input changed: '+str(path))
        target=out/'inputs'/actual
        if not target.exists():shutil.copy2(path,target)
        inputs[str(path)]=actual
    for path in (Path(__file__),a.plan,a.model/'manifest.json',a.model/'spike',a.model/'libsifive_uart.so',ROOT/'iris_model/guest_regions.py',ROOT/'iris_model/counter_regions.py',ROOT/'spike/run_functional.py'):
        retain(path)
    fixture=out/'source-clock.fixture';original=a.fixture.resolve() if a.fixture else ROOT/'build/rocket-pipeline-source-clock.fixture'
    expected=model['input_sha256'][str(original.relative_to(ROOT))];retain(original,expected);shutil.copy2(original,fixture);retain(fixture)
    launch=ROOT/'build/scalar-rtl-pipeline-v2/results.json';retain(launch);base=list(json.loads(launch.read_text())['argv'])
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    for case in plan['cases']:
        buildpath=Path(case['build_receipt']);retain(buildpath,case['build_receipt_sha256']);build=json.loads(buildpath.read_text());elf=Path(build['elf']);retain(elf,case['elf_sha256'])
        if build['reference_timing_observed_before_freeze'] or build['alu_operations']!=case['operations']:raise ValueError('frozen component role/shape changed')
        for path,digest in build['input_sha256'].items():retain(path,digest)
        count=case['operations'];contracts=source_contract(elf,count,build);directory=out/('alu'+str(count));directory.mkdir()
        argv=[str((a.model/'spike').resolve())]+base[1:]
        argv=['--extlib='+str((a.model/'libsifive_uart.so').resolve()) if x.startswith('--extlib=') else
              '--iris-timing-fixture='+str(fixture) if x.startswith('--iris-timing-fixture=') else
              '--iris-timing-trace='+str(directory/'graph.json') if x.startswith('--iris-timing-trace=') else
              '+signature='+str(directory/'signature') if x.startswith('+signature=') else x for x in argv];argv[-1]=str(elf)
        run=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=90);(directory/'stdout').write_text(run.stdout);(directory/'stderr').write_text(run.stderr)
        if run.returncode:raise RuntimeError('component model execution failed: '+run.stderr)
        rows=signature(directory/'signature',count,contracts);graph=json.loads((directory/'graph.json').read_text());reads=observations(graph,Instructions(elf,ROOT/'board/evidence/bootrom.rv64.img'))
        for row in rows:
            pair=[]
            for index,key in ((0,'start_cycle'),(3,'end_cycle')):
                selected=[r for r in reads if r['hart']==row['hart'] and r['pc']==contracts[row['kind']]['reads'][index]['pc'] and r['value']==row[key]]
                if len(selected)!=1:raise ValueError('component prediction boundary read ambiguous')
                pair.append(selected[0])
            span=(pair[1]['read_cycle']-pair[0]['read_cycle'])//graph['hart_cycle_dividers'][row['hart']]
            if row['cycles']!=span-int(row['hart']<2):raise ValueError('component visible/source edge span mismatch')
            row['physical_read_span']=span
        result=dict(case_id=case['case_id'],operations=count,build_receipt_sha256=sha(buildpath),elf_sha256=sha(elf),argv=argv,rows=rows,
                    signature_sha256=sha(directory/'signature'),graph_sha256=sha(directory/'graph.json'),stdout_sha256=sha(directory/'stdout'),stderr_sha256=sha(directory/'stderr'))
        (directory/'results.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
    if len(results)!=10 or sha(a.model/'spike')!=model['binary_sha256'] or sha(a.model/'libsifive_uart.so')!=model['uart_sha256']:raise ValueError('prediction/model scope changed')
    report=dict(schema='iris.scalar_component_predictions.v1',status='frozen_blinded_component_predictions',started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),
                model_manifest_sha256=sha(a.model/'manifest.json'),binary_sha256=model['binary_sha256'],uart_sha256=model['uart_sha256'],plan_sha256=sha(a.plan),
                input_sha256=inputs,cases=results,reference_timings_observed=False,predictions_frozen_before_reference=not a.reference_results_blinded,
                predicting_agent_has_viewed_reference_results=False,reference_measurements_may_exist_elsewhere_blinded=a.reference_results_blinded,final_workload_holdout=False,
                timing_calibrated=False,held_out_2pct=False)
    (out/'predictions.json').write_text(json.dumps(report,indent=2)+'\n')
    artifacts={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out/'inputs')}
    (out/'manifest.json').write_text(json.dumps(dict(schema='iris.scalar_component_prediction_closure.v1',prediction_sha256=sha(out/'predictions.json'),artifact_sha256=artifacts,input_sha256=inputs),indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],manifest_sha256=sha(out/'manifest.json'),cases=len(results),rows=sum(len(c['rows']) for c in results))))


if __name__=='__main__':main()
