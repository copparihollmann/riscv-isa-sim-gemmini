#!/usr/bin/env python3
import hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/noc-network-guests-v1'
 if o.exists():raise ValueError('Fresh guest output required')
 o.mkdir();prior=json.loads((R/'build/noc-full-router-guests/build.json').read_text());argv=prior['argv'][:];argv[argv.index('-DPROBE_KIND=5')]='-DPROBE_KIND=6';argv[argv.index(str(R/'timing/noc_full_router_guest.c'))]=str(R/'timing/noc_network_guest.c');elf=o/'all-harts-coherent.elf';argv[argv.index('-o')+1]=str(elf);q=subprocess.run(argv,text=True,capture_output=True);(o/'build.log').write_text(q.stdout+q.stderr)
 if q.returncode:raise RuntimeError('Guest compilation failed')
 inputs=[Path(x)for x in prior['input_sha256']if not x.endswith('noc_full_router_guest.c')]+[Path(__file__),R/'timing/noc_network_guest.c'];report={'argv':argv,'input_sha256':{str(p):sha(p)for p in inputs},'elf_sha256':sha(elf),'kind':6,'expected_checks':[84,84,84],'expected_done':[1,1,1],'memory_paths':['private DRAM dirty eviction on all three harts','shared coherent line publication and all-owner readback','cross-tile TCM0/1','system scratchpad'],'hardware_contacted':False};(o/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'elf':str(elf),'sha256':sha(elf)}))
if __name__=='__main__':main()
