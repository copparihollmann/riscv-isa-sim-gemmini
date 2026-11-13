#!/usr/bin/env python3
"""Full byte-reconstructable companion on frozen C12, including optional CPU trace."""
from pathlib import Path
import json,hashlib,difflib,tarfile,tempfile,subprocess
R=Path(__file__).resolve().parents[1];P=R/'build/warm-OPU-TK124-frozen-c12a08f7-v1';C=R/'build/C12-pending-base-frozen-2c40dca7-v1';S=R/'pipeline/riscv-isa-sim-C12-pending-base-v1';O=R/'build/C12-pending-base-on-C12-companion-v1';O.mkdir();sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();old=json.loads((P/'native-inventory.json').read_text());new=json.loads((C/'native-inventory.json').read_text());changed=[n for n in new if old[n]!=new[n]]
with tempfile.TemporaryDirectory(prefix='pending-base-C12-',dir=R/'build')as tmp:
 d=Path(tmp)
 with tarfile.open(P/'native-source.tar.gz')as t:
  for m in t.getmembers():
   assert m.name in old and '..'not in Path(m.name).parts and not Path(m.name).is_absolute();p=d/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read());assert sha(p)==old[m.name]
 patch=O/'pending-base-on-C12.patch';patch.write_text(''.join(''.join(difflib.unified_diff((d/n).read_text().splitlines(True),(S/n).read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))for n in changed))
 p=subprocess.run(['patch','--batch','-p1','-i',str(patch)],cwd=d,capture_output=True);(O/'patch.stdout').write_bytes(p.stdout);(O/'patch.stderr').write_bytes(p.stderr);assert p.returncode==0
 for n,h in new.items():assert sha(d/n)==h,n
r={'schema':'iris.C12_pending_base_companion.v1','pass':True,'base_C12_manifest_sha256':sha(P/'manifest.json'),'candidate_manifest_sha256':sha(C/'manifest.json'),'patch_sha256':sha(patch),'all_source_bytes_reconstructed':len(new),'changed_source_files':changed,'includes_default_OFF_observability':True,'behavior_selector_default_OFF':True,'native_binary_sha256':sha(C/'spike'),'UART_sha256':sha(C/'libsifive_uart.so'),'hardware_contacted':False};(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'patch_sha256':sha(patch),'report_sha256':sha(O/'report.json')}))
