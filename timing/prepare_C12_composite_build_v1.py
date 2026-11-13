#!/usr/bin/env python3
from pathlib import Path
import shutil,json,hashlib,os
R=Path(__file__).resolve().parents[1];P=R/'build/spike-FADD-EG-v2';B=R/'build/spike-C12-composite-v1';S=R/'pipeline/riscv-isa-sim-C12-composite-v1';oldS=R/'pipeline/riscv-isa-sim-FADD-EG-v2';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
shutil.copytree(P,B,symlinks=True)
for p in [B/'Makefile',B/'config.status',*B.glob('*.d')]:
 if not p.is_file():continue
 stat=p.stat();s=p.read_text();s=s.replace(str(oldS),str(S)).replace(str(P),str(B));p.write_text(s);os.utime(p,ns=(stat.st_atime_ns,stat.st_mtime_ns))
for name in ('riscv','fesvr','fdt'):
 p=B/'sdk'/name
 if p.is_symlink():p.unlink();p.symlink_to(S/name)
(B/'parent-object-reuse.json').write_text(json.dumps(dict(parent_build=str(P),parent_manifest_sha256=sha(R/'build/FADD-EG-actor-corrective-frozen-v2/manifest.json'),object_sha256={str(p.relative_to(P)):sha(p)for p in P.glob('*.o')},new_clean_build=False),indent=2)+'\n')
print(json.dumps(dict(prepared=True,build=str(B))))
