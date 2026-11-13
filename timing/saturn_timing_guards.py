#!/usr/bin/env python3
"""Exercise real physical payload corruption and recoverable SDK phase guards."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from saturn_timing_check import capture,compare,qualified,Timeline
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=R/'build/saturn-timing-sdk-v1';profiles={k:json.loads((R/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in['compute','rocket']};mutations=[];inputs=[Path(__file__),R/'timing/saturn_timing_check.py',R/'timing/saturn_timing_guards.cpp',sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',sdk/'sdk/saturn_timing.hpp',Path('/usr/bin/g++')]
 for case,h,targets in [('vme',0,['io_ex_ready','auto_atl_out_a_valid','auto_atl_out_a_bits_source','auto_atl_out_a_bits_address','auto_atl_out_a_bits_data_0']),('rvv',2,['io_core_wb_replay','io_core_wb_pc','auto_atl_out_a_bits_size']),('shared-fpu',2,['io_fp_req_valid','io_fp_req_bits_in1_0'])]:
  run=R/'build/saturn-timing-rtl-v1'/f'{case}.stderr';replay=R/'build/saturn-timing-replay-v2'/case/f'hart{h}.stdout';inputs.extend([run,replay]);rows,gold,tbs=capture(run,profiles);profile='rocket'if h==2 else'compute';j=profiles[profile];lines=[x for x in replay.read_text().splitlines()if x.startswith('SATURN_FRAME ')];ledger=Timeline(profile);available=[];known=False
  for e,(i,o,tb)in enumerate(zip(rows[h],gold[h],tbs[h])):
   available.append(qualified(profile,i,o,ledger.s2,ledger.hella_store)if known else{});known|=bool(i['reset']);ledger.observe(e,tb,i,o)
  for target in targets:
   edge=next((e for e,m in enumerate(available)if m.get(target,0)),None)
   if edge is None:raise ValueError('Missing active corruption target '+target)
   fields=[f['word_name']for f in j['words']['output']];word=fields.index(target);parts=lines[edge].split();bit=available[edge][target]&-available[edge][target];parts[word+2]=str(int(parts[word+2])^bit);changed=lines[:edge+1];changed[edge]=' '.join(parts)
   try:compare(profile,j,rows[h][:edge+1],gold[h][:edge+1],tbs[h][:edge+1],changed)
   except ValueError as error:
    if 'Runtime mismatch'not in str(error):raise
    mutations.append({'case':case,'hart':h,'field':target,'edge':edge,'flipped_bit':bit,'rejected':str(error)})
   else:raise ValueError('Physical corruption accepted')
  del rows,gold,tbs,lines,available
 source=R/'timing/saturn_timing_guards.cpp';binary=out/'phase-guards';command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(sdk/'sdk'),str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(binary)]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 phase=[]
 for profile,h in [('compute',0),('rocket',2)]:
  original=R/'build/saturn-timing-replay-v2/rvv'/f'hart{h}.input';inputs.append(original);subset=out/f'{profile}.input';lines=original.read_text().splitlines();first=next(n for n,line in enumerate(lines)if int(line.split()[2+[f['word_name']for f in profiles[profile]['words']['input']].index('io_ex_valid'if h==0 else'io_core_ex_valid')]))
  subset.write_text('\n'.join(lines[:first+2500])+'\n');command_run=[str(binary),profile,str(subset)]
  with(out/f'{profile}.stdout').open('w')as stdout,(out/f'{profile}.stderr').open('w')as stderr:q=subprocess.run(command_run,stdout=stdout,stderr=stderr,timeout=90)
  if q.returncode:raise ValueError('Phase recovery failed '+profile)
  result=next(json.loads(x.split(' ',1)[1])for x in(out/f'{profile}.stderr').read_text().splitlines()if x.startswith('SATURN_GUARDS '));phase.append({'profile':profile,'argv':command_run,**result})
 report={'schema':'iris.saturn_runtime_guards.v1','pass':True,'physical_checker_corruptions':mutations,'phase_recovery':phase,'compile_argv':command,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(binary),'hardware_contacted':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'corruptions':len(mutations),'phase_recovery':phase,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
