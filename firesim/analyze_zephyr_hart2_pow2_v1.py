#!/usr/bin/env python3
"""Root-invoked strict full-word analyzer; target timing rows remain sealed."""
import argparse,hashlib,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'zephyr'))
from hart2_pow2_managed_protocol_v1 import validate_console,cases as host_cases,need
from script_envelope_v3 import validate_envelope
from batch_runner import digest
from analyze_campaign import read_archive,select_guest_uart
from prepare_zephyr_hart2_pow2_v1 import ROLE,ELF

def lifecycle(current,m):
 need(current['status']==m['status']=='completed_uncertified'and current['cleanup_status']==m['cleanup_status']=='passed','Normal managed completion+cleanup')
 need(current.get('error')is None and current.get('cleanup_error')is None,'No managed errors')
 rows=m['commands'];need([(r['task'],r['status'])for r in rows]==[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')],'All four owned phases')
 need(all(type(r['returncode'])is int and r['returncode']==0 and r['timed_out']is False for r in rows),'Normal zero exits of all phases')
 return [{k:r.get(k)for k in ['task','status','returncode','timed_out','host_elapsed_seconds','cleanup_phase']}for r in rows]

def analyze(job,out):
 need(not out.exists()and job!=out and job not in out.parents,'Fresh analysis outside immutable job');out.mkdir(parents=True,mode=0o700)
 current=json.loads((job/'run.json').read_text());original=[Path(__file__).resolve(),ROOT/'zephyr/hart2_pow2_managed_protocol_v1.py',ROOT/'zephyr/hart2_pow2_validate_v4.py',ROOT/'firesim/analyze_campaign.py',ROOT/'firesim/batch_runner.py',ROOT/'firesim/prepare_zephyr_hart2_pow2_v1.py',ROOT/'zephyr/script_envelope_v3.py'];report=dict(schema='iris.Zephyr_hart2_pow2_archive_analysis.v1',**{'pass':False},functional_only=True,calibration_usable=False,timing_certified=False,source_image_association_verified=False,hardware_contacted=False,performance_labels_sealed=True,current_manifest_sha256=digest(job/'run.json'),external_analysis_input_sha256={str(p):digest(p)for p in original})
 try:
  cap=current['capture'];archive=Path(cap['archive']);need(cap['status']=='captured'and type(cap['returncode'])is int and cap['returncode']==0 and digest(archive)==cap['archive_sha256'],'Exact completed archive')
  data,ids=read_archive(archive,cap['captured_run_manifest_sha256']);m=json.loads(data['job/run.json']);report.update(archive_sha256=cap['archive_sha256'],archive_verified=True,archived_manifest_sha256=cap['captured_run_manifest_sha256'])
  need(m['campaign_role']==ROLE and m['require_regions']is True and m['require_goldens']is True and m['calibration_usable']is False and m['cases']==host_cases()and m['elf_sha256']==ELF,'Original functional-only exact contract')
  need(m['training_eligible']==456 and m['protected_validation']==192 and m['seal_timing_labels']is True,'Predeclared sealed split')
  for p in original:
   want=m['runner_sha256']if p.name=='batch_runner.py'else m['input_sha256'].get(str(p));need(want==digest(p)and want in ids.values(),'Original archived source mismatch '+str(p))
  details=[]
  for name,want in m['input_sha256'].items():
   need(digest(name)==want and want in ids.values(),'Original current+standalone input '+name);details.append(dict(path=name,sha256=want,standalone_bytes_in_archive=True))
  (out/'input-closure.json').write_text(json.dumps(details,indent=2)+'\n');report['input_closure']=dict(inputs=len(details),standalone_archived_inputs=len(details),all_current_bytes_match=True)
  need(m.get('input_snapshot_completion',{}).get('all_final_inputs_have_standalone_bytes')is True,'LAST posthook input snapshot completion')
  for name,want in [('ready.json',m['reviewed_ready_sha256']),('corpus.json',m['corpus_sha256']),('manager/workloads/iris-batch/batch.elf',ELF)]:need(ids.get('job/'+name)==want,'Original archived artifact '+name)
  member,report['guest_uart']=select_guest_uart(data,ids);script_members=[member.rsplit('/',1)[0]+'/sim-run.sh','job/optional-observability/sim-run.sh'];source_path='/scratch/eygao/iris-cy/sims/firesim/deploy/runtools/runtime_config.py';source_hash=m['input_sha256'][source_path]
  with tarfile.open(archive,'r:gz')as stream:
   def raw(name):
    value=stream.extractfile(name).read();need(hashlib.sha256(value).hexdigest()==ids[name],'Inventory-bound actual bytes '+name);return value
   wrappers=[raw(n)for n in script_members];need(wrappers[0]==wrappers[1],'Driver wrapper copies match');elf=raw('job/manager/workloads/iris-batch/batch.elf');ready=json.loads(raw('job/ready.json'));q=json.loads(raw('job/qualification.json'));runtime_source=raw('job/prepared-inputs/'+source_hash);watchdog=raw('job/manager/iris_workload_watchdog.py');corpus=json.loads(raw('job/corpus.json'))
  need(hashlib.sha256(elf).hexdigest()==ELF==ready['elf_sha256']==q['ELF_sha256'],'Exact guest ELF');need(ids['job/qualification.json']==ready['qualification_sha256']and q['pass']is True and q['calibration_authorized']is False,'Original bound qualification')
  need(all(h in ids.values()for h in q['input_sha256'].values()),'All qualified bytes archived');need(ids['job/manager/iris_workload_watchdog.py']==m['prepared_file_sha256']['manager/iris_workload_watchdog.py'],'Exact prepared watchdog')
  need(b'''script -f -c 'stty intr ^] && {driver_call} && stty intr ^c' uartlog'''in runtime_source and b'''screen -S {screen_name} -d -m bash -c "{base_command}"; sleep 1'''in runtime_source,'Source-bound exact script framing')
  need(b'\nSECONDS=180\n'in watchdog and b'/usr/bin/timeout --foreground --signal=TERM --kill-after=30s 'in watchdog,'Bound foreground180s watchdog')
  text=data[member].decode('utf-8','strict');report['driver_envelope']=validate_envelope(text,wrappers[0].decode('utf-8','strict'));report['guest_proof']=validate_console(text);report['lifecycle']=lifecycle(current,m)
  for name,value in [('uartlog.sealed',data[member]),('observed.elf',elf),('sim-run.sh',wrappers[0]),('runtime_config.py',runtime_source),('iris_workload_watchdog.py',watchdog)]:p=out/name;p.write_bytes(value);p.chmod(0o600)
  rows=[json.loads(line.partition(' ')[2])for line in text.splitlines()if line.startswith('IRIS_REGION ')];p=out/'regions.sealed.json';p.write_text(json.dumps(rows,indent=2)+'\n');p.chmod(0o600)
  need(digest(archive)==cap['archive_sha256']and digest(job/'run.json')==report['current_manifest_sha256'],'Archive/job unchanged during read-only analysis')
  report.update(**{'pass':True},regions=648,independent_elements=181440,output_guard_regions=648,observed_compute_harts=[0,1],actual_controller_hart=2,normal_driver_exit_status=0,actual_completion_footer=dict(failed=0,cases=486,regions=648,elements=181440,trials=3),protected_regions=192,training_eligible=456,source_image_attestation=False,scope='New exactSMP program/history; onepersistentowner percompute, h2scalarorchestration. FullactiveRVV and INT8/FP8matrixcells/guards only; no migration/competingowners, wholeMRFpadding, pureunit, globaltime, FENCEabsolutecompletion or2percent claim. Alltargetperformancevalues remain inrootonly sealedfiles, not an automatic fitting dataset.')
 except(OSError,ValueError,KeyError,TypeError,UnicodeError,tarfile.TarError)as e:report['error']=str(e)
 report['artifact_sha256']={p.name:digest(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.job.resolve(),a.output.resolve());print(json.dumps({k:r.get(k)for k in ['pass','archive_verified','regions','independent_elements','normal_driver_exit_status','error']}));raise SystemExit(0 if r['pass']else 1)
