#!/usr/bin/env python3
"""Freeze a new finite FADD-EG epoch against immutable C12 source bytes."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 a=argparse.ArgumentParser(__doc__);a.add_argument('--build',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args()
 build,out=args.build.resolve(),args.output.resolve();out.mkdir(parents=True,exist_ok=False)
 b=json.loads((build/'pipeline-build.json').read_text());source=Path(b['source']);parent=ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1'
 pm=json.loads((parent/'manifest.json').read_text());old=json.loads((parent/'native-inventory.json').read_text());ps=Path(pm['source'])
 names=set(old)|{'riscv/iris_fadd_eg_actor.inc'};inv={n:sha(source/n)for n in names}
 changed=sorted(n for n in inv if inv[n]!=old.get(n));patch=''
 for name in changed:
  previous=(ps/name).read_text().splitlines(True)if name in old else[]
  patch+='diff --git a/'+name+' b/'+name+'\n'+('new file mode 100644\n'if name not in old else'')
  patch+=''.join(difflib.unified_diff(previous,(source/name).read_text().splitlines(True),fromfile='a/'+name if name in old else'/dev/null',tofile='b/'+name))
 (out/'FADD-EG-on-C12.patch').write_text(patch)
 overlay=subprocess.check_output(['git','diff','--binary','HEAD'],cwd=source)
 assert hashlib.sha256(overlay).hexdigest()==b['source_overlay_sha256']
 (out/'source-overlay.patch').write_bytes(overlay)
 (out/'native-inventory.json').write_text(json.dumps(inv,indent=2,sort_keys=True)+'\n')
 with tarfile.open(out/'native-source.tar.gz','w:gz')as t:
  for name in sorted(inv):t.add(source/name,arcname=name,recursive=False)
 external={}
 for dep in build.glob('*.d'):
  text=dep.read_text().replace('\\\n',' ')
  for token in shlex.split(text.split(':',1)[1]):
   if token.endswith(':'):continue
   p=Path(token);p=p if p.is_absolute()else build/p;p=p.resolve()
   if p.is_file()and p.is_relative_to(ROOT)and not p.is_relative_to(source)and not p.is_relative_to(build):external[str(p)]=sha(p)
 for p in [Path(__file__).resolve(),ROOT/'timing/rvv_fadd_eg_source_v1.hpp',ROOT/'build/rvv-fadd-EG-source-closure-v1/report.json',parent/'manifest.json']:external[str(p)]=sha(p)
 (out/'compiled-inputs.json').write_text(json.dumps(external,indent=2,sort_keys=True)+'\n')
 for n in ['spike','libsifive_uart.so','pipeline-build.json']:shutil.copy2(build/n,out/n)
 assert sha(out/'spike')==b['binary_sha256']and sha(out/'libsifive_uart.so')==b['uart_sha256']
 with tempfile.TemporaryDirectory(prefix='FADD-EG-source-reconstruction-')as tmp:
  d=Path(tmp)
  with(d/'base.tar').open('wb')as f:subprocess.run(['git','archive',b['base_commit']],cwd=source,stdout=f,check=True)
  with tarfile.open(d/'base.tar')as t:t.extractall(d/'source')
  subprocess.run(['git','apply','--unsafe-paths',str(out/'source-overlay.patch')],cwd=d/'source',check=True)
  for n,h in inv.items():assert sha(d/'source'/n)==h,n
 for n,h in old.items():assert sha(ps/n)==h,n
 manifest=dict(schema='iris.finite_FADD_EG_native_capsule.v2',**{'pass':True},source_frozen=True,source=str(source),
  base_commit=b['base_commit'],binary_sha256=b['binary_sha256'],uart_sha256=b['uart_sha256'],native_device_abi=4,
  parent_manifest_sha256=sha(parent/'manifest.json'),native_changed_files=changed,native_sources_reconstructed=len(inv),
  external_compiled_inputs=len(external),preCOM_opaque_tokens_never_enqueue=True,strict_geometry_and_context_validation_at_architectural_COM=True,guest_scope_errors_include_execution_context=True,selector_default='OFF',selector='compute-HSD-fullVL-flags0-COMplus1-v1',
  scope='harts0/1 VFADD.VV fullVLmax unmasked HSD RNE Mmode definedoperands; FS alreadydirty; newflags0; perEGsourcecontroller; COMplus1 conservative unqualifiedCPUbridge; otherCSR/memory/vector consumersdrain; activeIRQrefused; wrongpathopaque tokens cancel beforeCOM and neverenter sourcecontroller',
  source_control_report_sha256=sha(ROOT/'build/rvv-fadd-EG-source-closure-v1/report.json'),
  source_image_association=False,timing_2pct_certified=False,hardware_contacted=False,parameters_fitted=False,
  artifact_sha256={n:sha(out/n)for n in ['spike','libsifive_uart.so','pipeline-build.json','FADD-EG-on-C12.patch','source-overlay.patch','native-inventory.json','native-source.tar.gz','compiled-inputs.json']})
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (out/'verification.json').write_text(json.dumps(dict(schema='iris.finite_FADD_EG_source_reconstruction.v1',**{'pass':True},manifest_sha256=sha(out/'manifest.json'),native_sources_reconstructed=len(inv),frozen_C12_unchanged=True,numeric_or_timing_qualification=False),indent=2)+'\n')
 print(json.dumps({'pass':True,'manifest_sha256':sha(out/'manifest.json'),'native':b['binary_sha256']}))
if __name__=='__main__':main()
