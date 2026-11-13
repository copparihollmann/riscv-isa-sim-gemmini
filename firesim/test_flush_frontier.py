#!/usr/bin/env python3
import copy,json,pathlib,shutil,tempfile
from batch_runner import digest
from prepare_flush_frontier import admit,merge
from analyze_flush_frontier import analyze
from flush_frontier_qualify import verify_pair
R=pathlib.Path(__file__).resolve().parents[1]
def main():
 out=R/'build/flush-frontier-tools-local-v1';out.mkdir(exist_ok=False);b=R/'build/flush-frontier-one-shot-v2';controls=[]
 for v in['enabled','disabled']:
  ready,corpus,cases,elf,ids=admit(b,digest(b/'ready.json'),v);assert len(cases)==32 and corpus['watchdog_enabled']==(v=='enabled')
 def reject(name,edit):
  with tempfile.TemporaryDirectory(dir=out)as d:
   t=pathlib.Path(d)
   for f in['ready.json','manifest.json','qualification.json','cases.json','golden.json','pair-proof.json','no-drain-proof.json']:shutil.copyfile(b/f,t/f)
   (t/'build').mkdir();shutil.copyfile(b/'build/build.json',t/'build/build.json')
   r=json.loads((t/'ready.json').read_text());edit(t,r);(t/'ready.json').write_text(json.dumps(r)+'\n')
   try:admit(t,digest(t/'ready.json'),'enabled')
   except(ValueError,KeyError,AssertionError):controls.append(dict(name=name,rejected=True));return
   raise ValueError('Admitted '+name)
 reject('commonarmerrequired',lambda t,r:r.update(both_variants_same_armer_thread=False))
 reject('no-hot-fences-required',lambda t,r:r.update(hot_hooks_hardware_fences=True))
 reject('exact-one-shotdelay',lambda t,r:r.update(one_shot_delay_ms=25))
 reject('fitting_allowed',lambda t,r:r.update(fitting_allowed=True))
 reject('all4seeded proof removed',lambda t,r:r.update(all4seeded_positives_pass=False))
 reject('forcedcounterfactuals removed',lambda t,r:r.update(both_forced_counterfactuals_pass=False))
 reject('wrongROIgeometry',lambda t,r:r.update(regions=188))
 try:admit(b,'0'*64,'disabled')
 except ValueError:controls.append(dict(name='wrongreadyhash',rejected=True))
 else:raise ValueError('Wronghash accepted')
 with tempfile.TemporaryDirectory(dir=out)as d:
  t=pathlib.Path(d);m=json.loads((b/'manifest.json').read_text());bad=t/'bad.elf';raw=bytearray(pathlib.Path(m['variants']['disabled']['path']).read_bytes());raw[0]^=1;bad.write_bytes(raw);m['variants']['disabled']=dict(path=str(bad),sha256=digest(bad))
  try:verify_pair(m)
  except(AssertionError,ValueError):controls.append(dict(name='secondELFbytechange',rejected=True))
  else:raise ValueError('Two-bytepair accepted')
 values={};merge(values,{'zephyr/flush_frontier_validate.py':digest(R/'zephyr/flush_frontier_validate.py')});assert all(pathlib.Path(p).is_absolute()for p in values)
 try:merge(values,{'zephyr/flush_frontier_validate.py':'0'*64})
 except ValueError:controls.append(dict(name='conflictingnormalizedsource',rejected=True))
 else:raise ValueError('Sourceconflictaccepted')
 assert analyze(R/'runs/fpga-phase-handoff-diagnostic-v1-001',out/'wrong-unpaired-archive')==1;controls.append(dict(name='actualunpairedarchivewrongrole',rejected=True))
 sources=[pathlib.Path(__file__),R/'firesim/prepare_flush_frontier.py',R/'firesim/analyze_flush_frontier.py',R/'zephyr/flush_frontier_qualify.py',R/'zephyr/flush_frontier_validate.py'];r=dict(schema='iris.phase_watch_pair_local_controls.v1',**{'pass':True},both_actual_positive_admissions_pass=True,negative_controls=controls,input_sha256={str(p):digest(p)for p in sources},hardware_contacted=False);(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
