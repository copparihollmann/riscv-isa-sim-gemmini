#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,shutil,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/rvv-store-compactor-component-v1';o.mkdir(exist_ok=False);sdk=o/'sdk';sdk.mkdir();header=R/'timing/rvv_store_compactor_control.hpp';test=R/'timing/rvv_store_compactor_check.cpp';base=json.loads((R/'build/rvv-store-compactor-check-v1/argv.json').read_text());controls=[]
 # Recompile and execute exact final header, never retag an earlier binary.
 final=o/'positive';final.mkdir();cmd=base[:];cmd[-1]=str(final/'check')
 with(final/'compile.stdout').open('w')as so,(final/'compile.stderr').open('w')as se:subprocess.run(cmd,check=True,stdout=so,stderr=se)
 with(final/'stdout').open('w')as so,(final/'stderr').open('w')as se:r=subprocess.run([str(final/'check')],stdout=so,stderr=se);assert r.returncode==0
 for name,old,new in [('pipe-full-queue','q_.size()<2','(q_.size()<2||deq)'),('omit-forwarding','bytes_+front>=in.pop_bytes','bytes_>=in.pop_bytes'),('overfill-input-queue','q_.size()<2','q_.size()<=2'),('omit-pop-subtract','-(out_.pop_fire?in_.pop_bytes:0)','-0')]:
  d=o/name;d.mkdir();text=header.read_text();assert text.count(old)==1;(d/header.name).write_text(text.replace(old,new));shutil.copy2(test,d/test.name);cmd=[str(d/test.name)if x==str(test)else x for x in base];cmd[-1]=str(d/'check')
  with(d/'compile.stdout').open('w')as so,(d/'compile.stderr').open('w')as se:subprocess.run(cmd,check=True,stdout=so,stderr=se)
  with(d/'stdout').open('w')as so,(d/'stderr').open('w')as se:r=subprocess.run([str(d/'check')],stdout=so,stderr=se)
  if r.returncode==0:raise ValueError('Acceptedmutant '+name)
  controls.append(dict(name=name,rejected=True,exit_status=r.returncode))
 shutil.copy2(header,sdk/header.name);rows=[json.loads(x[5:])for x in(final/'stdout').read_text().splitlines()if x.startswith('CASE ')];assert len(rows)==6
 inputs=[Path(__file__),header,test,R/'timing/rvv_store_compactor_build.py',R/'build/rvv-store-compactor-source-v1/build.json',R/'third_party/saturn/src/main/scala/common/Compactor.scala',R/'third_party/saturn/src/main/scala/common/DCEQueue.scala',R/'third_party/saturn/src/main/scala/mem/StoreSegmenter.scala',R/'third_party/saturn/src/main/scala/mem/Mem.scala',Path('/usr/bin/g++').resolve()]
 inputs +=[p for p in(R/'build/rvv-store-compactor-source-v1').rglob('*')if p.is_file()]+[p for p in o.rglob('*')if p.is_file()]
 report=dict(schema='iris.configured_store_compactor_control.v1',status='passed',continuous_source_edges=sum(x['edges']for x in rows),qualified_output_fields=sum(x['qualified_fields']for x in rows),cases=rows,compiled_implementation_mutants=controls,SDK_header=str(sdk/header.name),source_scope='Exactconfigured forward=falseCompactor/control: depth-two nonflow/nonpipeinputqueue+one16/32Bregisterbank;alignednf1 zeroheads/partialtails; numericdatapathnotduplicated',reset_scope='Actualreset establishesqueue/count; inactiveunresetnumericdata ignored, no zeroRAMknownnessclaim',actual_RTL_numeric_data_qualified=False,source_state_or_ready_injected=False,hardware_contacted=False,reserved_hardware_timings_consumed=False,input_sha256={str(p):sha(p)for p in inputs});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(o/'report.json'),'edges':report['continuous_source_edges']}))
if __name__=='__main__':main()
