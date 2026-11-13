#!/usr/bin/env python3
"""Compose private source changes; every source parent remains immutable."""
import hashlib,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-C12-composite-v1';O=R/'build/C12-composite-preparation-v1'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
O.mkdir();wake=R/'build/C12-async-RRD-wake-frozen-8fcf4e98-v2';wp=R/'pipeline/riscv-isa-sim-C12-async-RRD-wake-v2';inv=json.loads((wake/'native-inventory.json').read_text())
subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(wp),str(S)],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(wp/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(wp/n,p)
parents=[('pending-base',R/'pipeline/riscv-isa-sim-C12-cpu-diagnostic-v1',R/'pipeline/riscv-isa-sim-C12-pending-base-v1',R/'build/C12-pending-base-frozen-2c40dca7-v1'),('FADD-EG',R/'pipeline/riscv-isa-sim-warm-opu-tk124-v1',R/'pipeline/riscv-isa-sim-FADD-EG-v2',R/'build/FADD-EG-actor-corrective-frozen-v2'),('MM-FENCE',R/'pipeline/riscv-isa-sim-warm-opu-tk124-v1',R/'pipeline/riscv-isa-sim-opu-fence-v1',R/'build/opu-fence-frozen-ee65eee0-v1')]
report=[]
for tag,base,new,cap in parents:
 ni=json.loads((cap/'native-inventory.json').read_text());changed=[]
 for n,h in ni.items():
  assert sha(new/n)==h,(tag,n)
  if (base/n).exists() and sha(base/n)==h:continue
  changed.append(n);p=S/n
  if not (base/n).exists():
   assert not p.exists(),(tag,n,'new collision');p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(new/n,p)
  else:
   assert p.exists();q=subprocess.run(['git','merge-file','-p','--diff3',str(p),str(base/n),str(new/n)],capture_output=True)
   assert q.returncode in (0,1,2,3,4,5,6,7),(tag,n,q.stderr)
   if q.returncode:
    (O/(tag+'-'+Path(n).name+'.conflict')).write_bytes(q.stdout)
   p.write_bytes(q.stdout)
  inv[n]=sha(p)
 report.append(dict(component=tag,source=str(new),capsule=str(cap),manifest_sha256=sha(cap/'manifest.json'),changed_files=changed))
conflicts=[str(p.relative_to(S))for p in S.joinpath('riscv').glob('*')if p.is_file()and b'<<<<<<< 'in p.read_bytes()]
(O/'composition.json').write_text(json.dumps(dict(schema='iris.C12_composite_preparation.v1',source=str(S),components=report,unresolved_files=conflicts,hardware_contacted=False,late_ALU_included=False),indent=2)+'\n')
print(json.dumps(dict(source=str(S),unresolved_files=conflicts)))
