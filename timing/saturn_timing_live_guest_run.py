#!/usr/bin/env python3
"""Functional-only qualification of initial native-bridge ELF on a frozen pair."""
import argparse,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
from spike.run_functional import command
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--pair',type=Path,default=R/'build/combined-frozen-35901887');p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'runner.py');build=a.build.resolve();pair=a.pair.resolve();receipt=json.loads((build/'build.json').read_text());elf=build/'guest.elf'
 if sha(elf)!=receipt['ELF_sha256']:raise ValueError('ELF differs from source build')
 for path,digest in receipt['input_sha256'].items():
  if sha(path)!=digest:raise ValueError('Changed ELF build input '+path)
 rom=R/'board/evidence/bootrom.rv64.img';dtb=R/'board/build/iris.dtb';base=command(pair/'spike',elf);base=['--extlib='+str(pair/'libsifive_uart.so')if x.startswith('--extlib=')else x for x in base];base=base[:-1]+['--iris-bootrom='+str(rom),'--dtb='+str(dtb)]+base[-1:];rows=[]
 for seed in[0,17]:
  cmd=base[:-1]+['--iris-schedule-seed='+str(seed)]+base[-1:];start=time.monotonic();env=dict(os.environ);env['PATH']='/scratch/eygao/iris-cy/.conda-env/bin:'+env['PATH'];q=subprocess.run(cmd,text=True,capture_output=True,timeout=60,env=env,cwd=R);(out/f'seed{seed}.stdout').write_text(q.stdout);(out/f'seed{seed}.stderr').write_text(q.stderr);values=[x for x in q.stdout.splitlines()if x.startswith('IRIS_SATURN_LIVE_VALUES')];done=[x for x in q.stdout.splitlines()if x.startswith('IRIS_SATURN_LIVE_DONE')];passed=q.returncode==0 and values==['IRIS_SATURN_LIVE_VALUES 8 6 64']and done==['IRIS_SATURN_LIVE_DONE 3']and'IRIS_FATAL'not in q.stdout+q.stderr;rows.append({'seed':seed,'argv':cmd,'exit_status':q.returncode,'pass':passed,'values':values,'completion':done,'host_seconds':time.monotonic()-start})
 inputs=[Path(__file__),R/'spike/run_functional.py',build/'build.json',build/'admission.json',elf,pair/'spike',pair/'libsifive_uart.so',pair/'manifest.json',rom,dtb];report={'schema':'iris.saturn_initial_live_guest_functional_only.v1','pass':all(x['pass']for x in rows),'runs':rows,'input_sha256':{str(p):sha(p)for p in inputs},'program_visible_counters_are_timing_qualified':False,'source_runtime_timing_hook_enabled':False,'RTL_cycle_accuracy_claimed':False,'actual_ELF_execution':True,'all_three_hart_boot_and_peer_checks':True,'hardware_contacted':False};report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'report_sha256':sha(out/'report.json'),'runs':rows}))
 if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
