#!/usr/bin/env python3
"""Independent finite IRQ phase coverage; no calibration data or model changes."""
from pathlib import Path
import json,subprocess,sys,hashlib
R=Path(__file__).resolve().parents[1];O=R/'build/C12-pending-base-IRQ-phase-controls-v1';O.mkdir();ref=json.loads((R/'build/C12-pending-base-guest-v1/build.json').read_text());original=R/'timing/C12_pending_base_guest_v1.c';reports=[];sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for phase in(1,2,3,5,6,7,8,9):
 b=O/f'phase{phase}';b.mkdir();src=b/'guest.c';s=original.read_text().replace('  for(unsigned i=0;i<512;++i){',f'  __asm__ volatile(".rept {phase}\\nnop\\n.endr":::"memory");\n  for(unsigned i=0;i<512;++i){{');src.write_text(s);cmd=[str(src)if x==str(original)else str(b/'guest.elf')if x.endswith('/guest.elf')else x for x in ref['argv']];p=subprocess.run(cmd,capture_output=True);(b/'compile.stderr').write_bytes(p.stderr);assert p.returncode==0
 (b/'build.json').write_text(json.dumps({'argv':cmd,'exit_status':p.returncode,'input_sha256':{str(Path(x)):sha(Path(x))for x in cmd if Path(x).is_file()}},indent=2)+'\n')
 d=b/'ON';p=subprocess.run([sys.executable,str(R/'timing/check_C12_pending_base_native_v3.py'),'--on','--elf',str(b/'guest.elf'),'--output',str(d),'--trace-first','134000','--trace-last','137000'],capture_output=True);(b/'control.stdout').write_bytes(p.stdout);(b/'control.stderr').write_bytes(p.stderr);assert p.returncode==0,p.stderr.decode()
 rows=[json.loads(x)for x in(d/'cpu.jsonl').read_text().splitlines()];wait=[x for x in rows if x['event']=='pending_base_retry'];exc=[x for x in rows if x['event']=='COM_enter'and x['raw']==0];matches=[{'retry':a,'precise_exception_COM':e}for a in wait for e in exc if a['pc']==e['pc']and 0<e['cycle']-a['cycle']<=4];reports.append({'phase_NOPs':phase,'normal_numeric_fault_IRQ_passed':True,'held_load_preempted_matches':matches,'run':str(d/'run.json')})
 (O/'report.json').write_text(json.dumps({'schema':'iris.pending_base_IRQ_phase_controls.v1','hardware_contacted':False,'reports':reports,'precise_IRQ_while_load_held_proven':any(x['held_load_preempted_matches']for x in reports)},indent=2)+'\n')
 print(phase,len(matches),flush=True)
 if matches:break
