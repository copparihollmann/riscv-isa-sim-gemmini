#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=R/'build/saturn-timing-fpu-guests-v1';out.mkdir(parents=True,exist_ok=False);old=json.loads((R/'build/saturn-timing-guests-v1/build.json').read_text());argv=old['argv'][:];argv[argv.index('-DPROBE_KIND=8')]='-DPROBE_KIND=9';argv[argv.index(str(R/'timing/saturn_timing_guest.c'))]=str(R/'timing/saturn_timing_fpu_guest.c');elf=out/'shared-fpu-all-harts.elf';argv[argv.index('-o')+1]=str(elf);q=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('Saturn shared-FPU guest build failed')
 inputs=[Path(p)for p in old['input_sha256']if not p.endswith(('saturn_timing_guest.c','saturn_timing_guest_build.py'))]+[Path(__file__),R/'timing/saturn_timing_fpu_guest.c'];report={'schema':'iris.saturn_shared_fpu_guest.v1','argv':argv,'input_sha256':{str(p):sha(p)for p in inputs},'elf_sha256':sha(elf),'kind':9,'expected_checks':[28]*3,'expected_done':[1]*3,'explicit_init':'All32VRFs via four full e8/m8 zero moves; fcsr0; every FMA active operand initialized through typed vmv.','independent_golden':'All3harts H/S/D timesLMUL1/4/8: vector1*1+1=2 exact bits; concurrent scalar double1+8*1=9 exact bits; every active stored byte checked.','hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'elf_sha256':sha(elf)}))
if __name__=='__main__':main()
