#!/usr/bin/env python3
import json,pathlib,shutil,tempfile,sys
R=pathlib.Path(__file__).resolve().parents[1]
from prepare_phase_handoff_diagnostic import admit,merge
from analyze_phase_handoff_diagnostic import analyze
from batch_runner import digest

def main():
 out=R/'build/phase-handoff-tools-local-v1';out.mkdir(exist_ok=False);b=R/'build/heldout-phase-diagnostic-v2';ready,corpus,cases,elf,ids=admit(b,digest(b/'ready.json'));assert len(cases)==32;controls=[]
 def reject(name,change):
  with tempfile.TemporaryDirectory(dir=out)as d:
   t=pathlib.Path(d);shutil.copyfile(b/'ready.json',t/'ready.json')
   for file in ['manifest.json','qualification.json','cases.json','golden.json']:shutil.copyfile(b/file,t/file)
   r=json.loads((t/'ready.json').read_text());change(t,r);(t/'ready.json').write_text(json.dumps(r)+'\n')
   try:admit(t,digest(t/'ready.json'))
   except(ValueError,KeyError):controls.append(dict(name=name,rejected=True));return
   raise ValueError('Accepted '+name)
 reject('wrong diagnostic schema',lambda t,r:r.update(schema='wrong'))
 reject('calibration permitted',lambda t,r:r.update(fitting_allowed=True))
 reject('missing forced-watchdog control',lambda t,r:r.update(forced_negative_watchdog_passed=False))
 reject('wrong watchdog hart',lambda t,r:r.update(watchdog_hart=2))
 reject('wrong phase geometry',lambda t,r:r.update(phases=8))
 try:admit(b,'0'*64)
 except ValueError:controls.append(dict(name='wrong readyhash',rejected=True))
 else:raise ValueError('Accepted wronghash')
 d={};merge(d,{'zephyr/heldout_phase_diagnostic_validate.py':digest(R/'zephyr/heldout_phase_diagnostic_validate.py')});assert all(pathlib.Path(x).is_absolute()for x in d)
 try:merge(d,{'zephyr/heldout_phase_diagnostic_validate.py':'0'*64})
 except ValueError:controls.append(dict(name='conflicting normalized source',rejected=True))
 else:raise ValueError('Conflicting source admitted')
 assert analyze(R/'runs/fpga-buffered-fit-v1-002',out/'wrong-role-archive')==1;controls.append(dict(name='actual wrong-role archive',rejected=True))
 paths=[pathlib.Path(__file__),R/'firesim/prepare_phase_handoff_diagnostic.py',R/'firesim/analyze_phase_handoff_diagnostic.py',R/'zephyr/heldout_phase_diagnostic_validate.py'];r=dict(schema='iris.phase_handoff_tools_local_controls.v1',**{'pass':True},positive_admission=True,cases=32,regions=32,negative_controls=controls,hardware_contacted=False,input_sha256={str(p):digest(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
