#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];O=R/'build/C12-source-composite-inputs-v1';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
zero=R/'build/rvv-compute-asm-C12-model-inputs-v1/ownzero.fixture';fixed=R/'build/rvv-compute-asm-C12-TRAIN-proposal-v1/runtime.fixture';assert sha(fixed)=='4ad56ce2879121703846a180a9d8337cc165fd85f41d74020eeaad6de63b7579'
flags=['empirical_pending_base_retry h0h1-live-XPR-base-RRD-retry-v1','empirical_async_rrd_wake h0h1-existing-live-head-eligibility-v1','empirical_opu_fence source-MM-only-FM0-busy-not-numeric-tail-v1','empirical_fadd_eg compute-HSD-fullVL-flags0-counterCSR-COMplus1-v2']
(O/'all-new-OFF.fixture').write_bytes(zero.read_bytes())
def make(parent,name,id,opu):
 lines=parent.read_text().splitlines();out=[]
 for l in lines:
  f=l.split()
  if f and f[0]=='empirical_profile':assert len(f)==4 and f[3]=='bounded';f[2]=id;l=' '.join(f)
  if not opu and f and f[0]=='empirical_opu_entry':continue
  out.append(l)
 out += [l for l in flags if opu or not l.startswith('empirical_opu_fence ')];p=O/name;p.write_text('\n'.join(out)+'\n')
 # Numeric resources/rules/counters/clocks exactly inherited. Mode/identity are explicit.
 remove={'empirical_profile','empirical_pending_base_retry','empirical_async_rrd_wake','empirical_opu_fence','empirical_fadd_eg'}
 if not opu:remove.add('empirical_opu_entry')
 filt=lambda text:[l for l in text.splitlines()if not(l.split()and l.split()[0]in remove)]
 assert filt(parent.read_text())==filt(p.read_text())
 return p
files=[make(zero,'ownzero-ON.fixture','iris-C12-source-composite-ownzero-v1',True),make(fixed,'fixed-costs-ON.fixture','iris-C12-source-composite-fixed-costs-v1',True),make(fixed,'fixed-costs-OPU-OFF.fixture','iris-C12-source-composite-fixed-costs-OPU-OFF-v1',False)]
(O/'provenance.json').write_text(json.dumps(dict(schema='iris.C12_source_composite_fixture_derivation.v1',numeric_costs_resources_clock_counter_policies_unchanged=True,parameters_fitted=False,hardware_contacted=False,inputs_sha256={str(p):sha(p)for p in [Path(__file__),zero,fixed]},output_sha256={p.name:sha(p)for p in [O/'all-new-OFF.fixture',*files]},flags=flags,OS_scope='FADD/pending-base/wake ON; source OPU-entry and specialized FENCE OFF for OS context; no OPU activeIRQ admission implied'),indent=2)+'\n')
print(json.dumps({p.name:sha(p)for p in files}))
