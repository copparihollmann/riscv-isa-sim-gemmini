#!/usr/bin/env python3
"""Additive archive reader repair; no changes to completed V2 job or guest."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from fpga_bringup_v2 import validate,host_cases,need
from script_envelope_v3 import validate_envelope
from batch_runner import digest
from analyze_campaign import read_archive,select_guest_uart
from analyze_zephyr_bringup_v2 import lifecycle
from prepare_zephyr_bringup_v2 import ROLE

def closure(m,ids):
 details=[]
 for name,want in m['input_sha256'].items():
  need(digest(name)==want,'Original V2 input no longer matches bound digest '+name)
  details.append(dict(path=name,sha256=want,standalone_bytes_in_archive=want in ids.values(),current_bytes_match_original_bound_digest=True))
 return dict(original_bound_inputs=len(details),standalone_archived_inputs=sum(x['standalone_bytes_in_archive']for x in details),postrun_added_inputs_without_standalone_archive_copy=sum(not x['standalone_bytes_in_archive']for x in details),all_current_bytes_verified_against_original_digests=True,retention_scope='Some postobserver transitive inputs were hash-bound after preparer snapshots; their current bytes match original digests, not falsely described as standalone archived copies.',inputs=details)

def analyze(job,out):
 need(not out.exists()and job!=out and job not in out.parents,'Fresh analysis outside immutable job');out.mkdir(parents=True)
 current=json.loads((job/'run.json').read_text());external=[Path(__file__).resolve(),ROOT/'zephyr/script_envelope_v3.py',ROOT/'firesim/test_zephyr_bringup_v3.py'];original=[ROOT/'firesim/analyze_zephyr_bringup_v2.py',ROOT/'zephyr/fpga_bringup_v2.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/prepare_zephyr_bringup_v2.py']
 report=dict(schema='iris.Zephyr_scalar6_bringup_archive_analysis.v3',**{'pass':False},functional_only=True,calibration_usable=False,timing_certified=False,source_image_association_verified=False,hardware_contacted=False,post_collection_reader_change_only=True,current_manifest_sha256=digest(job/'run.json'),external_analysis_input_sha256={str(p):digest(p)for p in external},preserved_v2_failure=str(ROOT/'build/zephyr-scalar6-FPGA-HARDWARE-validated-v2/report.json'))
 try:
  cap=current['capture'];archive=Path(cap['archive']);need(cap['status']=='captured'and type(cap['returncode'])is int and cap['returncode']==0 and digest(archive)==cap['archive_sha256'],'Exact completed archive')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_sha256=cap['archive_sha256'],archive_verified=True,archived_manifest_sha256=cap['captured_run_manifest_sha256'])
  need(m['campaign_role']==ROLE and m['require_regions']is True and m['require_goldens']is True and m['calibration_usable']is False and m['cases']==host_cases(),'Original V2 finite scalar6 contract')
  for p in original:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p));need(want==digest(p)and want in ids.values(),'Original archived V2 source mismatch '+str(p))
  report['original_v2_analysis_source_sha256']={str(p):digest(p)for p in original}
  original_closure=closure(m,ids);(out/'original-input-closure.json').write_text(json.dumps(original_closure,indent=2)+'\n');report['original_input_closure']={k:v for k,v in original_closure.items()if k!='inputs'}
  for name,want in [('ready.json',m['reviewed_ready_sha256']),('corpus.json',m['corpus_sha256']),('manager/workloads/iris-batch/batch.elf',m['elf_sha256'])]:need(ids.get('job/'+name)==want,'Original archived actual artifact '+name)
  member,report['guest_uart']=select_guest_uart(data,ids)
  script_members=[member.rsplit('/',1)[0]+'/sim-run.sh','job/optional-observability/sim-run.sh'];source_path='/scratch/eygao/iris-cy/sims/firesim/deploy/runtools/runtime_config.py';source_hash=m['input_sha256'][source_path]
  with tarfile.open(archive,'r:gz')as stream:
   def read(name):
    raw=stream.extractfile(name).read();need(hashlib.sha256(raw).hexdigest()==ids[name],'Inventory-bound actual bytes '+name);return raw
   wrappers=[read(n)for n in script_members];need(wrappers[0]==wrappers[1],'Managed and cleanup sim-run copies agree')
   elf=read('job/manager/workloads/iris-batch/batch.elf');ready=json.loads(read('job/ready.json'));q=json.loads(read('job/qualification.json'));runtime_source=read('job/prepared-inputs/'+source_hash);watchdog=read('job/manager/iris_workload_watchdog.py')
   need(ids['job/manager/iris_workload_watchdog.py']==m['prepared_file_sha256']['manager/iris_workload_watchdog.py'],'Exact prepared watchdog')
  need(hashlib.sha256(elf).hexdigest()==ready['ELF_sha256']==q['ELF_sha256']==m['elf_sha256'],'Original exact guest ELF')
  need(ids['job/qualification.json']==ready['qualification_sha256']and q['pass']is True,'Original qualification binding')
  need(all(h in ids.values()for h in q['input_sha256'].values()),'Original complete qualification/dependency bytes are archived')
  need(b'''script -f -c 'stty intr ^] && {driver_call} && stty intr ^c' uartlog'''in runtime_source and b'''screen -S {screen_name} -d -m bash -c "{base_command}"; sleep 1'''in runtime_source,'Bound source host script invocation')
  need(b'\nSECONDS=180\n'in watchdog and b'/usr/bin/timeout --foreground --signal=TERM --kill-after=30s 'in watchdog,'Bound foreground180s watchdog source')
  text=data[member].decode('utf-8','strict');report['driver_envelope']=validate_envelope(text,wrappers[0].decode('utf-8','strict'));report['guest_proof']=validate(text,False);report['guest_proof']['driver_exit_verified_by_v3_envelope']=True;report['lifecycle']=lifecycle(current,m)
  report['host_invocation_source']=dict(runtime_config_source=source_path,runtime_config_sha256=source_hash,sim_run_members=[dict(member=n,sha256=ids[n])for n in script_members],prepared_watchdog_sha256=ids['job/manager/iris_workload_watchdog.py'],remote_script_binary_or_version_captured=False)
  failed=Path(report['preserved_v2_failure']);old=json.loads(failed.read_text());need(old['pass']is False and old['archive_sha256']==cap['archive_sha256']and old['error']=='Unique exact [COMMAND_EXIT_CODE="0"] line required; DONE/PASSED alone is insufficient','Preserved V2 parser refusal, same successful archive');report['preserved_v2_failure_sha256']=digest(failed)
  for name,raw in [('uartlog',data[member]),('observed.elf',elf),('sim-run.sh',wrappers[0]),('runtime_config.py',runtime_source),('iris_workload_watchdog.py',watchdog)]: (out/name).write_bytes(raw)
  rows=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_REGION ')];(out/'regions.json').write_text(json.dumps(rows,indent=2)+'\n')
  need(digest(archive)==cap['archive_sha256']and digest(job/'run.json')==report['current_manifest_sha256'],'Archive/job unchanged during read-only analysis')
  report.update(**{'pass':True},regions=6,observed_harts=[0,1,2],actual_completion_footer=dict(failed=0),normal_driver_exit_status=0,qualification='Actual scalar Zephyr SMP all3 pinned worker/sleep/synchronization and independent six checksums passed, normal HTIF/driver exit0 and full managed cleanup/archive. Original25-region vector/context hang remains unresolved; no RVV/VME or explicit interrupt-count certification.')
 except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as e:report['error']=str(e)
 report['artifact_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.job.resolve(),a.output.resolve());print(json.dumps({k:r.get(k)for k in ('pass','archive_verified','regions','normal_driver_exit_status','error')}));raise SystemExit(0 if r['pass']else 1)
