#!/usr/bin/env python3
"""New package refusal controls plus a bounded real fixed-ISA launcher smoke."""
import argparse,copy,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from timing.source_OPU_developer_v2 import verify
from benchmarks.validate_console import validate
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False);mp=a.package.resolve();m=verify(mp,sha(mp));controls=[]
 def bad(name,mutate=None,duplicate=False,wrongsha=False):
  p=o/(name+'.json');v=copy.deepcopy(m)
  if mutate:mutate(v)
  raw=json.dumps(v,indent=2)
  if duplicate:raw=raw[:-1]+',"ready":true}'
  p.write_text(raw);expected='0'*64 if wrongsha else sha(p)
  try:verify(p,expected)
  except(ValueError,KeyError,TypeError,OSError)as e:controls.append({'name':name,'refused':True,'reason':str(e)});return
  raise ValueError('malformed package accepted '+name)
 bad('wrong_manifest_SHA',wrongsha=True);bad('boolean_ready_is_not_integer',lambda x:x.update(ready=1));bad('duplicate_JSON_key',duplicate=True)
 bad('UART_native_pair_mismatch',lambda x:x['roles'].update(UART=copy.deepcopy(x['roles']['native'])))
 bad('launcher_receipt_mismatch',lambda x:x['roles'].update(launcher=copy.deepcopy(x['roles']['native'])))
 bad('ON_fixture_swapped_with_OFF',lambda x:x['fixtures'].update(tk124=copy.deepcopy(x['fixtures']['off'])))
 runner=ROOT/'timing/source_OPU_developer_v2.py';base=[sys.executable,str(runner),'--package',str(mp),'--expected-sha256',sha(mp)]
 r=subprocess.run(base+['--action','provider'],capture_output=True,text=True);(o/'provider.stdout').write_text(r.stdout);(o/'provider.stderr').write_text(r.stderr)
 if r.returncode!=1 or 'IRIS_SOURCE_OPU_CALIBRATED_PROVIDER_UNAVAILABLE'not in r.stderr:raise ValueError('Uncalibrated provider was not refused')
 controls.append({'name':'calibrated_provider_unavailable','refused':True,'reason':r.stderr.strip()})
 r=subprocess.run(base+['--action','run','--timeout','nan','--elf',str(ROOT/'benchmarks/build/smoke.elf'),'--output',str(o/'invalid-timeout')],capture_output=True,text=True)
 if r.returncode!=1 or (o/'invalid-timeout').exists()or 'Finite positive timeout'not in r.stderr:raise ValueError('Non-finite timeout did not refuse before output/exec')
 controls.append({'name':'nonfinite_timeout','refused':True,'reason':r.stderr.strip()})
 argv=base+['--action','run','--mode','off','--elf',str(ROOT/'benchmarks/build/smoke.elf'),'--output',str(o/'smoke'),'--timeout','90']
 r=subprocess.run(argv,capture_output=True,text=True,timeout=105);(o/'smoke-runner.stdout').write_text(r.stdout);(o/'smoke-runner.stderr').write_text(r.stderr);ex=json.loads((o/'smoke/execution.json').read_text())
 if r.returncode or ex.get('pass')is not True or ex.get('owned_process_cleanup_complete')is not True:raise ValueError('Fixed native experiment command failed '+r.stderr)
 checked=validate((o/'smoke/stdout').read_text(),json.loads((ROOT/'benchmarks/calibration-corpus.json').read_text()),3,True)
 # The fixed command itself claims only process exit. This separate independent
 # console validator supplies actual all-three-hart numerical/normal-exit proof.
 report={'schema':'iris.source_OPU_developer_package_controls.v1','pass':True,'manifest_sha256':sha(mp),'controls':controls,'controls_count':len(controls),'smoke':checked,'smoke_execution':str(o/'smoke/execution.json'),'calibrated_provider_available':False,'default_selection_changed':False,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in(mp,runner,Path(__file__).resolve(),ROOT/'benchmarks/validate_console.py',ROOT/'benchmarks/calibration-corpus.json',ROOT/'benchmarks/build/smoke.elf')},'output_sha256':{str(p):sha(p)for p in o.rglob('*')if p.is_file()}}
 (o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'controls':len(controls),'report':str(o/'report.json'),'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
