"""Freeze this one-case diagnostic only after actual functional and omission runs."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'firesim'))
from rvv_hart2_probe_review import validator,inspect,inspect_clint_window,flatten,progress_prefix,parent_proof
from batch_runner import digest
from validate import validate
b=ROOT/'build/rvv-hart2-256-probe-v3';n=ROOT/'build/rvv-hart2-256-probe-skip-v3';raw=(b/'guest.elf').read_bytes();c=json.loads((b/'corpus.json').read_text());layout=json.loads((b/'layout.json').read_text());built=json.loads((b/'build.json').read_text());binary=inspect(raw,c,layout);phase=inspect_clint_window(raw);ids=dict(built['input_sha256']);functional=[]
for seed in(0,17):
 p=b/f'seed{seed}/run.json';r=json.loads(p.read_text());assert r['pass']is True and r['normal_exit']is True and r['exit_status']==0 and not r['timed_out'];validator().validate((p.parent/'stdout').read_text(),c);ids.update(r['input_sha256']);ids.update({str(x):digest(x)for x in(p,p.parent/'stdout',p.parent/'stderr')});functional.append(dict(seed=seed,report=str(p),report_sha256=digest(p),host_seconds=r['host_seconds']))
p=n/'seed0/run.json';r=json.loads(p.read_text());assert r['pass']is True and r['expect_negative']is True and r['exit_status']!=0 and not r['timed_out'];validate((p.parent/'stdout').read_text(),True);ids.update(r['input_sha256']);ids.update({str(x):digest(x)for x in(p,p.parent/'stdout',p.parent/'stderr')});negative=dict(report=str(p),report_sha256=digest(p),failed_regions=1)
text=(b/'seed0/stdout').read_text();controls=[]
def reject(name,fn):
 try:fn()
 except(Exception):controls.append(dict(name=name,rejected=True))
 else:raise ValueError('Admitted corruption '+name)
reject('active-role',lambda:validator().validate(text.replace('"hart":2,"case_index":0,"stage":"START"','"hart":1,"case_index":0,"stage":"START"'),c))
reject('stage-reorder',lambda:progress_prefix(text.replace('"stage":"ACK"','"stage":"SETUP"'),c))
reject('stage-truncate',lambda:validator().validate(text[:text.index('IRIS_BATCH_DONE')],c))
reject('duplicate-stage',lambda:progress_prefix(text+next(x for x in text.splitlines()if '"stage":"DONE"'in x),c))
case=copy.deepcopy(c);case['cases'][0]['hart']=0;reject('wrong-compiled-role',lambda:inspect(raw,case,layout))
case=copy.deepcopy(c);case['cases'][0]['expected_checksum']^=1;reject('changed-independent-golden',lambda:validator().validate_corpus(case))
e=parent_proof.Elf(raw);changed=bytearray(raw);changed[e.offset(e.syms['experiments'][0]+8,1)]^=1;reject('compiled-kind',lambda:inspect(bytes(changed),c,layout))
changed=bytearray(raw);changed[e.offset(phase['fence_between_issue_and_drain_pc'],1)]^=1;reject('compiled-fence',lambda:inspect_clint_window(bytes(changed)))
protocol=json.loads((ROOT/'build/pow2-memory-isolated-v3/protocol-proof.json').read_text());assert protocol['pass_']is True and protocol['states']==51
for name,value in [('protocol-proof.json',protocol),('phase-proof.json',dict(phase,ROI_progress_present=True,calibration_usable=False)),('review.json',dict(pass_=True,compiled_and_layout_proof=binary)),('host-cases.json',flatten(c)),('diagnostic-proof.json',dict(progress_prefix(text,c),full_stage_order=__import__('validate').STAGES))]:(b/name).write_text(json.dumps(value,indent=2)+'\n')
paths=[Path(__file__).resolve(),ROOT/'firesim/rvv_hart2_probe_review.py',ROOT/'firesim/rvv_identify_tk_review.py',ROOT/'benchmarks/rvv_identify_tk_v3/qualify.py',b/'phase-proof.json',b/'host-cases.json'];ids.update({str(p):digest(p)for p in paths});assert all(digest(p)==h for p,h in ids.items())
q=dict(schema='iris.hart2_256B_diagnostic_qualification.v1',**{'pass':True},ELF_sha256=digest(b/'guest.elf'),functional=functional,actual_omitted_kernel=negative,corruption_controls=controls,compiled_and_layout_proof=binary,compiled_counter_phase_proof=phase,per_element_words_checked_per_schedule=64,quiet_hart_protocol=protocol,diagnostic_only=True,calibration_usable=False,normal_guest_exit_verified=True,input_sha256=ids);(b/'qualification.json').write_text(json.dumps(q,indent=2)+'\n')
names=['guest.elf','build.json','qualification.json','review.json','corpus.json','layout.json','host-cases.json','protocol-proof.json','phase-proof.json','diagnostic-proof.json'];ready=dict(schema='iris.hart2_256B_diagnostic_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,ELF_sha256=digest(b/'guest.elf'),required_cases=1,required_regions=1,trials=1,record_bytes=192,checked_words_per_schedule=64,fitting_only=False,diagnostic_only=True,calibration_usable=False,all_output_after_measurements=False,ROI_contains_progress_and_is_not_calibration=True,new_exact_reference_required=True,source_image_association_verified=False,artifact_sha256={name:digest(b/name)for name in names});(b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(ready_sha256=digest(b/'ready.json'),ELF_sha256=ready['ELF_sha256'],controls=len(controls))))
