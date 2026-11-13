#!/usr/bin/env python3
"""Apply exact small source replacements, preserving all composite additions."""
from pathlib import Path
import difflib,json,hashlib,shutil
R=Path(__file__).resolve().parents[1];S=R/'pipeline/riscv-isa-sim-C12-composite-v1';B=R/'pipeline/riscv-isa-sim-FADD-EG-v2';N=R/'pipeline/riscv-isa-sim-FADD-EG-counterCSR-v1';C=R/'build/FADD-EG-counterCSR-frozen-cb668b7f-v1';O=R/'build/C12-composite-preparation-v1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
# Preserve accidental pre-CSR build: no test or qualification attached to it.
prototype=O/'pre-counterCSR-prototype';prototype.mkdir()
for n in('spike','libsifive_uart.so','pipeline-build.json'):shutil.copy2(R/'build/spike-C12-composite-v1'/n,prototype/n)
for n in('build.stdout','build.stderr'):shutil.copy2(O/n,prototype/n)
(prototype/'status.json').write_text(json.dumps(dict(schema='iris.C12_composite_preCSR_prototype.v1',qualification_performed=False,reason='initial three-way CSR merger refused adjacent parser additions; shell continued to produce prototype; never executed or frozen as selected candidate',input_sha256={n:sha(prototype/n)for n in ('spike','libsifive_uart.so','pipeline-build.json')}),indent=2)+'\n')
changes=[]
for n in ('riscv/iris_timing_adapter.cc','riscv/iris_shuttle_issue.cc','riscv/iris_fadd_eg_actor.inc'):
 base=(B/n).read_text().splitlines(True);new=(N/n).read_text().splitlines(True);s=(S/n).read_text()
 for tag,a,b,c,d in difflib.SequenceMatcher(None,base,new,autojunk=False).get_opcodes():
  if tag=='equal':continue
  old=''.join(base[a:b]);replacement=''.join(new[c:d])
  if not old:
   assert b<len(base);old=base[b];replacement+=old
  assert s.count(old)==1,(n,tag,s.count(old),old[:80]);s=s.replace(old,replacement);changes.append(dict(file=n,kind=tag,old_sha256=hashlib.sha256(old.encode()).hexdigest(),new_sha256=hashlib.sha256(replacement.encode()).hexdigest()))
 (S/n).write_text(s)
h=(S/'riscv/iris_timing_adapter.h').read_text();assert h.count('empirical_fadd_eg_counter_csr=false')==1
(O/'counterCSR-merge-v2.json').write_text(json.dumps(dict(schema='iris.C12_composite_counterCSR_merge.v2',**{'pass':True},parent_manifest_sha256=sha(C/'manifest.json'),patch_sha256=sha(C/'FADD-EG-counterCSR-on-6849.patch'),exact_replacements=changes,legacy_whole_owner_counter_predicate_unchanged=True,FENCE_join_retained=True,hardware_contacted=False,component_runtime_qualification_pending=True),indent=2)+'\n')
print(json.dumps({'pass':True,'exact_replacements':len(changes)}))
