#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=R/'build/opu-sequencer-guests-v1';out.mkdir(parents=True,exist_ok=False);old=json.loads((R/'build/noc-full-router-guests/build.json').read_text());argv=old['argv'][:];argv[argv.index('-DPROBE_KIND=5')]='-DPROBE_KIND=7';argv[argv.index(str(R/'timing/noc_full_router_guest.c'))]=str(R/'timing/opu_sequencer_guest.c');elf=out/'all-harts-vme.elf';argv[argv.index('-o')+1]=str(elf);argv.insert(1,'-I'+str(R/'third_party/saturn/benchmarks/common'));q=subprocess.run(argv,capture_output=True,text=True);(out/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('OPU guest build failed')
 inputs=[Path(p)for p in old['input_sha256']if not p.endswith('noc_full_router_guest.c')]+[Path(__file__),R/'timing/opu_sequencer_guest.c',R/'third_party/saturn/benchmarks/common/vme.h'];report={'schema':'iris.opu_sequencer_guest.v1','argv':argv,'input_sha256':{str(p):sha(p)for p in inputs},'elf_sha256':sha(elf),'kind':7,'expected_checks':[1472,1472,2],'expected_done':[1,1,1],'scope':['INT8/FP8 four tiles, partial17x31 geometry and tk2','all four FP8 format combinations, exact representable2.0 output','row and column move-in; implemented row readout only','concurrent h2 scalar traffic + actual OPU illegal trap'],'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'elf_sha256':sha(elf)}))
if __name__=='__main__':main()
