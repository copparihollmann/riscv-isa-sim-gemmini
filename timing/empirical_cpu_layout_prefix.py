#!/usr/bin/env python3
"""Extract pre-UART CPU batch CSR timings; disclose partial process completion."""
import argparse,collections,csv,hashlib,json,pathlib
from empirical_live_features_v2 import difference
from empirical_cpu_layout_fit import metrics
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def main(a):
 out=a.output;out.mkdir(exist_ok=False,parents=True)
 proof=json.load(open(ROOT/'build/cpu-layout-v2/binary-proof.json'));meta=json.load(open(ROOT/'build/cpu-layout-v2/layout-meta.json'));assert proof['status']=='passed'
 receipt=json.load(open(a.native/'results.json'));assert receipt['input_sha256'][receipt['argv'][-1]]==proof['elf_sha256']
 raw=(a.native/'features.jsonl').read_bytes();complete=raw[:raw.rfind(b'\n')+1];(out/'features.snapshot.jsonl').write_bytes(complete)
 prefixes=[json.loads(s) for s in complete.splitlines()];by=collections.defaultdict(list)
 for p in prefixes:
  if p['schema']!='iris.empirical.prefix.v1' or p['endpoint']!='get_csr_before_current_instruction_retirement':raise ValueError('Bad prefix endpoint')
  if p['csr']!=0xb00 or p['result_discarded'] or type(p['value']) is not int or type(p['hart']) is not int:raise ValueError('Bad source counter observation')
  by[p['hart']].append(p)
 refs={(r['case_id'],int(r['hart'])):r for r in csv.DictReader(open(ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv'))}
 split=json.load(open(ROOT/'calibration/cpu-layout-v2/split.json'));rows=[];checks=0
 for h in range(3):
  ps=sorted(by[h],key=lambda p:p['sequence']);assert len(ps)>=1536
  index=0
  for f in proof['functions']:
   if f['mode']=='noop':continue
   for n in (16,64,256,1024):
    for rep in range(3):
     first,last=ps[index*2:index*2+2];index+=1
     if (first['sequence'],last['sequence'])!=(4*(index-1)+1,4*(index-1)+2):raise ValueError('Missing/nonunique CSR order')
     if (first['pc'],last['pc'])!=(f['begin_pc'],f['end_pc']):raise ValueError('Executed ELF boundary mismatch')
     if last['retired']-first['retired']!=3*n+1:raise ValueError('Unexpected execution/retirement within region')
     fs=difference(first['features'],last['features']);bh=difference({'b':first['branch_history']},{'b':last['branch_history']}).get('b',{})
     if fs['scalar.integer']['instructions']!=2*n or fs['scalar.branch']['instructions']!=n or bh['resolved']!=n:raise ValueError('Actual instruction feature mismatch')
     ident=f"cpu.layout.v2.{f['mode']}.off{f['offset']}.n{n}.repeat{rep}";ref=refs[(ident,h)];cycles=last['value']-first['value']
     if cycles<=0:raise ValueError('Nonpositive source mcycle span')
     rows.append({'case_id':ident,'parent_case_id':ref['parent_case_id'],'hart':h,'mode':f['mode'],'loop_offset':f['offset'],'loop_pc':f['loop_pc'],'n':n,'repeat':rep,'partition':split['split'][ref['parent_case_id']]['partition'],'native_cycles':cycles,'reference_cycles':int(ref['cycles']),'start_cycle':first['value'],'end_cycle':last['value'],'start_sequence':first['sequence'],'end_sequence':last['sequence'],'retired_delta':last['retired']-first['retired'],'features':fs,'branch_history':bh,'memory':difference(first['memory'],last['memory']), 'native_full_guest_numeric_completion_claimed':False})
     checks+=5
 assert len(rows)==2304
 text=(a.native/'stdout').read_bytes();completeout=text[:text.rfind(b'\n')+1];(out/'stdout.snapshot').write_bytes(completeout)
 index={(r['case_id'],r['hart']):r for r in rows};printed=0
 for s in completeout.decode().splitlines():
  if not s.startswith('IRIS_REGION '):continue
  r=json.loads(s[12:])
  if r['mode']=='noop':continue
  p=index[(r['case_id'],r['hart'])]
  if r.get('pass') is not True or r['checksum']!=r['hart']+1+3*r['n'] or r['counter_end']!=r['n']:raise ValueError('Printed numeric failure')
  if (r['start_cycle'],r['end_cycle'])!=(p['start_cycle'],p['end_cycle']):raise ValueError('Printed counter disagreement')
  printed+=1;checks+=2
 for r in rows:r['cycles']=r['reference_cycles'];r['predicted_cycles']=r['native_cycles']
 summary={}
 for partition in ('train','internal_validation'):
  eligible=[r for r in rows if r['partition']==partition];summary[partition]={'all':metrics(eligible),'conditioned_N_ge64_repeats1_2':metrics([r for r in eligible if r['n']>=64 and r['repeat']>0])}
  summary[partition]['conditioned_by_hart_mode']={f'{h}:{m}':metrics([r for r in eligible if r['hart']==h and r['mode']==m and r['n']>=64 and r['repeat']>0]) for h in range(3) for m in ('compact','wide')}
 (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in rows));(out/'native-receipt.snapshot.json').write_bytes((a.native/'results.json').read_bytes())
 report={'schema':'iris.cpu_layout_prefix_batch_baseline.v1','status':'all_main_ROI_CSR_observations_available_process_still_partial' if receipt['status']=='running' else receipt['status'],
 'roi_rows':2304,'actual_counter_and_instruction_checks':checks,'native_printed_numeric_rows_at_snapshot':printed,'all_ROI_numeric_checks_observed':printed==2304,'full_guest_exit0_observed':receipt.get('exit_status')==0,
 'baseline_comparison':summary,'qualification':'Actual successful counter callbacks and retired instruction/branch counts at exact ELF PCs establish these timing observations; partial UART/HTIF completion is disclosed and is not a full native functional gate.',
 'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [pathlib.Path(__file__).resolve(),ROOT/'timing/empirical_live_features_v2.py',ROOT/'build/cpu-layout-v2/binary-proof.json',ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv',ROOT/'calibration/cpu-layout-v2/split.json',out/'features.snapshot.jsonl',out/'stdout.snapshot',out/'native-receipt.snapshot.json']},
 'native_input_sha256':receipt['input_sha256'],'global_heldout_timings_consumed':False,'native_parameter_fit_performed':False,'full_2pct_certified':False,'source_image_association_verified':False}
 write(out/'report.json',report);print(json.dumps(report,indent=2));print('SHA',sha(out/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--native',type=pathlib.Path,default=ROOT/'build/empirical-cpu-layout-823-baseline-v1');p.add_argument('--output',type=pathlib.Path,default=ROOT/'build/empirical-cpu-layout-823-prefix-v1');main(p.parse_args())
