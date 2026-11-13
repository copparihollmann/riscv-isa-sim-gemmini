#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=R/'build/saturn-timing-guests-v1';out.mkdir(parents=True,exist_ok=False);old=json.loads((R/'build/noc-full-router-guests/build.json').read_text());argv=old['argv'][:];argv[argv.index('-DPROBE_KIND=5')]='-DPROBE_KIND=8';argv[argv.index(str(R/'timing/noc_full_router_guest.c'))]=str(R/'timing/saturn_timing_guest.c');elf=out/'rvv-all-harts.elf';argv[argv.index('-o')+1]=str(elf);q=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('Saturn active guest build failed')
 inputs=[Path(p)for p in old['input_sha256']if not p.endswith('noc_full_router_guest.c')]+[Path(__file__),R/'timing/saturn_timing_guest.c'];report={'schema':'iris.saturn_runtime_guest.v1','argv':argv,'input_sha256':{str(p):sha(p)for p in inputs},'elf_sha256':sha(elf),'kind':8,'expected_checks':[33]*3,'expected_done':[1]*3,'explicit_init':'All32VRFs full VLEN256 through four e8/m8 zero moves; fcsr0 in compactCRT and app. No tile instruction in this guest.','independent_golden':'All3harts,16SEW8/16/32/64xLMUL1/2/4/8 shapes; chained2,3->5->8->13; every active stored byte independently OR-checked.','hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'elf_sha256':sha(elf)}))
if __name__=='__main__':main()
