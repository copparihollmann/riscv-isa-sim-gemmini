#!/usr/bin/env python3
"""Second parser/math audit of actual firstuse FPGA functional evidence."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'firesim'));sys.path.insert(0,str(ROOT/'timing'))
from analyze_campaign import read_archive,select_guest_uart
from batch_runner import digest
from fp8_format_functional_audit_v1 import Elf
from script_envelope_v3 import validate_envelope
ARCHIVE='39f1f857f49312d48e93089d974834b8d769b7883f0358233b932e2c7b9a23c8'
ELF='f5d722c41d53517416cb0314191851f30227fa63e25c93408d73361494bd33dd'
def need(ok,message):
 if not ok:raise ValueError(message)
def objects(text,prefix):return[json.loads(x[len(prefix)+1:])for x in text.splitlines()if x.startswith(prefix+' ')]
def audit(job,out):
 need(not out.exists(),'Fresh independent output');out.mkdir(parents=True);current=json.loads((job/'run.json').read_text());cap=current['capture'];need(cap['status']=='captured'and cap['returncode']==0 and cap['archive_sha256']==ARCHIVE and digest(cap['archive'])==ARCHIVE,'Exact archive identity')
 data,ids=read_archive(cap['archive'],cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);member,uart=select_guest_uart(data,ids);raw=data[member];text=raw.decode('utf-8','strict')
 need(current['status']==m['status']=='completed_uncertified'and current['cleanup_status']==m['cleanup_status']=='passed'and current.get('error')is None and current.get('cleanup_error')is None,'Normal managed result/cleanup')
 need([(r['task'],r['status'],r['returncode'],r['timed_out'])for r in m['commands']]==[(t,'passed',0,False)for t in ['kill','infrasetup','runworkload','kill']],'Full four-phase normal lifecycle')
 with tarfile.open(cap['archive'],'r:gz')as t:
  script_member=member.rsplit('/',1)[0]+'/sim-run.sh';script=t.extractfile(script_member).read();script_copy=t.extractfile('job/optional-observability/sim-run.sh').read();elf=t.extractfile('job/manager/workloads/iris-batch/batch.elf').read();post_raw=t.extractfile('job/postrun-memory-observation-v2/observation.json').read()
 need(script==script_copy and hashlib.sha256(script).hexdigest()==ids[script_member],'Both host wrapper copies identical')
 envelope=validate_envelope(text,script.decode());need(hashlib.sha256(elf).hexdigest()==m['elf_sha256']==ELF,'Actual exact ELF')
 # Literal independent arithmetic, without primary guest validator imports.
 expected={}
 for h in range(3):
  total=0
  for i in range(16):
   if i%3==h:
    for j in range(16):
     acc=0
     for k in range(16):acc+=1*1
     total+=acc
  expected['zephyr.gemm16',h]=total;total=0
  for y in range(6):
   if y%3==h:
    for x in range(6):
     acc=0
     for ky in range(3):
      for kx in range(3):acc+=1*1
     total+=acc
  expected['zephyr.conv2d8',h]=total
  total=0
  if h<2:
   for col in range(32):
    cell=0
    for op in range(32):cell=(cell+1*1)&0xffffffff
    total+=cell
  else:
   for iteration in range(32):
    for byte in range(32):total+=1
  expected['zephyr.vme.scalar-control',h]=total
 rows=objects(text,'IRIS_REGION');need(len(rows)==9,'All nine actual regions');seen=set();public=[]
 for r in rows:
  need(all(type(r.get(k))is int for k in ['hart','hart_mask','checksum','start_cycle','end_cycle','instret_delta']),'Typed real region')
  key=r['case_id'],r['hart'];need(key in expected and key not in seen and r['checksum']==expected[key]and r['hart_mask']==7 and r['region']=='kernel','Independent literal numerical/role identity');seen.add(key)
  role='scalar.compute'if key[0]!='zephyr.vme.scalar-control'else'vme.compute'if key[1]<2 else'scalar.control';need(r['role']==role,'Actual role')
  need(0<=r['start_cycle']<r['end_cycle']<2**64 and 0<r['instret_delta']<2**64,'Actual CSR values present, not calibrated here')
  public.append({k:r[k]for k in ['case_id','hart','role','hart_mask','checksum']})
 need(seen==set(expected)and objects(text,'IRIS_BATCH_DONE')==[{'failed':0}]and type(objects(text,'IRIS_BATCH_DONE')[0]['failed'])is int,'Exact full numerical/footer completion')
 ready=objects(text,'IRIS_FIRSTUSE_READY');need(len(ready)==1 and ready[0]==dict(physical_hart=2,logical_cpu=2,worker=2,pin=2,timeout_ms=5000,hart2_scalar_only=True),'Actual scalar observer armed first')
 snapshots=objects(text,'IRIS_FIRSTUSE_SNAPSHOT');need(len(snapshots)==3,'Three last records')
 for h,s in enumerate(snapshots):
  need(all(type(s.get(k))is int and s[k]==h for k in ['slot','physical_hart','logical_cpu','worker','pin']),'Actual physical/logical identities')
  need(type(s['begin'])is int and type(s['end'])is int and s['begin']==s['end']and s['begin']>0 and s['begin']%2==0 and s['stable_sequence_observed']is True and s['metadata_race_possible']is True and s['current_PC_or_state_claimed']is False,'Last-record consistency/scope')
  need(type(s['stage'])is int and s['stage']==([281,281,1001][h]),'Expected final source program point')
 need(objects(text,'IRIS_FIRSTUSE_OBSERVER_DONE')==[dict(physical_hart=2,done0=1,done1=1)]and not objects(text,'IRIS_FIRSTUSE_TIMEOUT'),'Observer completed normally')
 (out/'observed.elf').write_bytes(elf);e=Elf(out/'observed.elf');checks=[]
 for symbol in ['scalar_control_context','iris_probe_observe','iris_probe_stamp']:
  need(len(e.symbols[symbol])==1,'Unique actual scalar symbol');a,n=e.symbols[symbol][0];i=0;count=0
  while i<n:
   w=int.from_bytes(e.read(a+i,2),'little');size=4 if w&3==3 else 2;w=int.from_bytes(e.read(a+i,size),'little');need(not(size==4 and w&127 in[7,0x27,0x53,0x57,0x77])and not(size==2 and w&3 in[0,2]and w>>13 in[1,5]),'No app FP/vector in scalar role/progress')
   if symbol=='iris_probe_stamp':need(not(size==4 and w&127 in[15,0x2f]),'No hotFENCE/AMO')
   i+=size;count+=1
  checks.append(dict(symbol=symbol,instructions=count,FP_vector_instructions=0))
 post=json.loads(post_raw);need(hashlib.sha256(post_raw).hexdigest()==ids['job/postrun-memory-observation-v2/observation.json'],'Postdriver sidecar actual bytes')
 need(post['status']=='observed_postdriver_configuration_registers'and post['normal_driver_exit_verified']is True and post['hardware_writes']is False and post['physical_memory_latency_measured']is False and post['source_image_association_verified']is False,'Separate postdriver config scope')
 (out/'functional-identities.json').write_text(json.dumps(public,indent=2)+'\n');(out/'snapshots.json').write_text(json.dumps(snapshots,indent=2)+'\n')
 primary=ROOT/'build/zephyr-firstuse-h2scalar-FPGA-validated-v1/report.json';p=json.loads(primary.read_text());need(p['pass']is True and p['archive_sha256']==ARCHIVE,'Primary strict analyzer separately passed')
 inputs=[Path(__file__).resolve(),ROOT/'zephyr/script_envelope_v3.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',primary,ROOT/'build/zephyr-firstuse-context-buffer-layout-v1/report.json']
 report=dict(schema='iris.Zephyr_firstuse_FPGA_independent_review.v1',**{'pass':True},actual_hardware_functional_packet_passed=True,archive_sha256=ARCHIVE,ELF_sha256=ELF,actual_regions=9,independent_literal_math_checks=9,complete_roles=public,physical_harts=[0,1,2],hart2_application_scalar_only_machine_code=checks,driver_envelope=envelope,normal_driver_exit0=True,full_owned_lifecycle_cleanup_capture=True,last_source_stages=[s['stage']for s in snapshots],postdriver_selected_parameters=post['selected_parameters'],configuration_scope='Actual postdriver register readback, memory-model clock units; not physical latency',original93a_fix_or_cause_proven=False,hart2_RVV_qualified=False,VME_migration_or_competing_contexts_qualified=False,full_MRF_or_perword_numeric_claim=False,source_image_association_verified=False,timing_certified=False,hardware_contacted_by_review=False,protected_timing_labels_consumed=False,limits=['VME numeric check is tile0row0 sum32words for32unsignedINT8TK1 commands, not fullMRF/perword proof.','No kernel firstrestore or actualfailed93aPC trace was captured.','Source stages/CSRs are lastrecords, not coherent/current machine state or physicalcompletion.','No timing calibration, FP8 coverage transfer, h2 vector or migrating/competing-owner certificate.'],input_sha256={str(x):digest(x)for x in inputs})
 need(digest(cap['archive'])==ARCHIVE,'Archive unchanged');report['artifact_sha256']={x.name:digest(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=audit(a.job.resolve(),a.output.resolve());print(json.dumps(dict(status='passed',regions=r['actual_regions'],report_sha256=digest(a.output/'report.json'))))
