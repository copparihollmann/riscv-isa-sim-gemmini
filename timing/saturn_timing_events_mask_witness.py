#!/usr/bin/env python3
"""Preserve the old full-bus sub-beat mask bug against the corrected same trace."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);old=R/'build/saturn-timing-events-v2';new=R/'build/saturn-timing-events-v3';fast=R/'build/saturn-timing-fast-component-v1-final';sdk=fast/'build/saturn-timing-fast-v1/sdk/sdk';source=out/'driver.cpp';shutil.copy2(new/'source/saturn_timing_events_driver.cpp',source);command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(old/'sdk'),'-I'+str(sdk),str(source),str(old/'sdk/libiris_saturn_events.a'),str(sdk/'libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'old-mask-control')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 ports=fast/'build/saturn-timing-fast-replay-v1/fpcomp/hart0.input';values=fast/'build/saturn-timing-fast-replay-v1/fpcomp/hart0.stdout';run=[str(out/'old-mask-control'),'compute','0',str(ports),str(values)];q=subprocess.run(run,capture_output=True,text=True,timeout=60);(out/'stdout').write_text(q.stdout);(out/'stderr').write_text(q.stderr)
 if q.returncode:raise ValueError('Old mask comparison did not run')
 actual=json.loads(q.stdout);correct=next(x for x in json.loads((new/'report.json').read_text())['runs']if x['case']=='fpcomp'and x['hart']==0)
 for key in['edges','pending_TL_sources_at_end','command_identity_checks','command_identity_mix64','TL_event_checks','source_events']:assert actual[key]==correct[key],key
 assert actual['TL_owned_data_mask_mix64']!=correct['TL_owned_data_mask_mix64'],'Old mask bug was not detected by independent ownership/data mask comparison'
 paths=[Path(__file__),source,old/'report.json',old/'sdk/saturn_timing_events.hpp',old/'sdk/libiris_saturn_events.a',new/'report.json',ports,values,sdk/'libiris_saturn_timing.a',Path('/usr/bin/g++')];report={'schema':'iris.saturn_subbeat_mask_bug_witness.v1','pass':True,'compile_argv':command,'argv':run,'old_projection':actual,'correct_data_mask_mix64':correct['TL_owned_data_mask_mix64'],'counts_and_instruction_identity_unchanged':True,'old_subbeat_byte_mask_rejected':True,'mask_scope':'Protocol significant lanes; actual data knownness must additionally come from the memory/functional producer.','input_sha256':{str(p):sha(p)for p in paths},'artifact_sha256':{str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()},'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'old_data_mask_mix64':actual['TL_owned_data_mask_mix64'],'correct_data_mask_mix64':correct['TL_owned_data_mask_mix64'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
