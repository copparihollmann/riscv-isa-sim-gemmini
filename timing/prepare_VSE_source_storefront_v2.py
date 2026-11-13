#!/usr/bin/env python3
"""Create a disjoint exacte24 child; no frozen source/build is modified."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
R=Path(__file__).resolve().parents[1]
P=R/'pipeline/riscv-isa-sim-VSE-live-boundary-v1'
C=R/'build/VSE-live-boundary-frozen-e24c891b-v1'
S=R/'pipeline/riscv-isa-sim-VSE-source-storefront-v2'
PB=R/'build/spike-VSE-live-boundary-v1'
B=R/'build/spike-VSE-source-storefront-v2'
O=R/'build/VSE-source-storefront-preparation-v2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 assert sha(C/'manifest.json')=='ea32fc63c403d25306cefba2d2d5aeae67dd93cf6d458a40818c9374aa8f0f8b'
 inv=json.loads((C/'native-inventory.json').read_text())
 for n,h in inv.items():assert sha(P/n)==h,n
 O.mkdir(exist_ok=True)
 if S.exists():
  for n,h in inv.items():assert sha(S/n)==h,n
 else:
  subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True)
  subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True)
  for n in inv:
   p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,p)
 subprocess.run(['git','-C',str(S),'add','-N','--',*sorted(inv)],check=True)
 shutil.copytree(PB,B,symlinks=True)
 for p in [B/'Makefile',B/'config.status',*B.glob('*.d')]:
  if p.is_file():
   st=p.stat();p.write_text(p.read_text().replace(str(P),str(S)).replace(str(PB),str(B)));os.utime(p,ns=(st.st_atime_ns,st.st_mtime_ns))
 for n in ('riscv','fesvr','fdt'):
  p=B/'sdk'/n
  if p.is_symlink():p.unlink();p.symlink_to(S/n)
 (B/'parent-object-reuse.json').write_text(json.dumps(dict(parent_build=str(PB),parent_manifest_sha256=sha(C/'manifest.json'),object_sha256={p.name:sha(p)for p in PB.glob('*.o')},new_clean_build=False,header_dependency_rebuild_required=True),indent=2)+'\n')
 (O/'preparation.json').write_text(json.dumps(dict(schema='iris.VSE_live_boundary_preparation.v1',parent_manifest_sha256=sha(C/'manifest.json'),native_files_exact_before_edits=len(inv),source=str(S),build=str(B),hardware_contacted=False,protected_labels_read=False),indent=2)+'\n')
 print(S)
if __name__=='__main__':main()
