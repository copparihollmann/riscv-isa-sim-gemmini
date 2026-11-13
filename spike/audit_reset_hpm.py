#!/usr/bin/env python3
"""Audit exact saved CSR elaboration and pinned reset/HPM source, not RTL execution."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(__file__).resolve().parent
FIR=Path('/scratch/eygao/iris-cy/sims/firesim-staging/generated-src/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig.fir')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 expected=json.loads((ROOT/'hardware/manifest.json').read_text())['sources']['firesim-fir']['sha256'];assert sha(FIR)==expected
 wanted={'CSRFile':0,'CSRFile_1':1,'CSRFile_2':2};modules={};active=None
 for no,line in enumerate(FIR.open(),1):
  match=re.match(r'  module ([A-Za-z0-9_]+) ',line)
  if match:
   active=match[1] if match[1] in wanted else None
   if active:modules[active]={'first_line':no,'lines':[]}
  if active:modules[active]['lines'].append(line)
 evidence=OUT/'reset-hpm-evidence';evidence.mkdir(exist_ok=True);rows=[]
 for name,hart in wanted.items():
  module=modules[name];text=''.join(module['lines']);p=evidence/(name+'.fir');p.write_text(text)
  counters=re.search(r'counters : \{ eventSel : UInt<64>, flip inc : UInt<\d+>\}\[(\d+)\]',text)
  assert counters and counters[1]=='0'
  for reg,width in [('reg_fflags',5),('reg_frm',3)]:assert re.search(r'    reg '+reg+r' : UInt<'+str(width)+r'>, clock ',text)
  assert not re.search(r'    (?:reg|regreset) reg_hpmcounter',text)
  inhibit=re.search(r'    regreset reg_mcountinhibit : UInt<(\d+)>',text);assert inhibit and inhibit[1]=='3'
  rows.append({'hart':hart,'module':name,'first_line':module['first_line'],'snapshot_sha256':sha(p),'perf_counter_ports':0,'hpm_register_count':0,'mcountinhibit_width':3,'fflags_reset':'uninitialized register','frm_reset':'uninitialized register'})
 sources={}
 for name in ['third_party/rocket-chip/src/main/scala/rocket/CSR.scala','third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala','third_party/rocket-chip/src/main/scala/tile/FPU.scala','third_party/shuttle/src/main/scala/common/Parameters.scala','third_party/shuttle/src/main/scala/exu/Core.scala','third_party/saturn/src/main/scala/backend/RegisterFile.scala']:
  p=ROOT/name;repo=ROOT/'third_party'/Path(name).parts[1];sources[name]={'sha256':sha(p),'git_sha':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()}
 result={'schema_version':1,'fir_sha256':expected,'harts':rows,'source_inputs':sources,'rtl_executed':False,'deployed_image_association_verified':False,'claims':{'HPM':'All3 elaborated CSRFiles have zero performance counter ports/regs. Source pads all29 HPM/event slots with0; writes loop empty.','counteren':'Read masks0x7; user/supervisor HPM access always illegal. Counteren internal registers themselves are unreset.','mcountinhibit':'3bit reset0; bit1 tied0; only CY/IR writable.','time':'No CSRs.time or timeh mapping in pinned CSR read_mapping. Independent selected saved-RTL probes are recorded separately; CLINT mtime is separate MMIO.','reset':'fflags/frm, scalar FPR storage and VRF/v0 storage have no reset initialization; model must not certify zero reset bits.'}}
 (OUT/'reset-hpm-policy.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'harts':rows,'fir_sha256':expected}))
if __name__=='__main__':main()
