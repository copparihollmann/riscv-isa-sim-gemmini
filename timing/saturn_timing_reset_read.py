#!/usr/bin/env python3
"""Independent symbolic known-bit replay of accepted reset/writer transcripts."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_transcript(path):
 cases={}
 for line in path.read_text().splitlines():
  if not line.startswith('RESET_WRITE '):continue
  tokens=line.split(' ',1)[1].split(',');profile=tokens[0];kind,seed,edge,active,cursor,eg,label=map(int,tokens[1:8]);masks=list(map(int,tokens[8:]));egs,dlen,banks=(64,128,4)if profile=='compute'else(32,256,1)if profile=='rocket'else(0,0,0)
  if not egs or len(masks)!=dlen//32 or label not in [0,7]or not 0<=eg<egs:raise ValueError('Malformed accepted bank write')
  key=(profile,kind,seed);c=cases.setdefault(key,{'memory':[[0]*(dlen//32)for _ in range(egs)],'known':[[0]*(dlen//32)for _ in range(egs)],'zero_egs':set(),'producer_egs':set(),'last_edge':-1,'writes':0,'first_producer':None,'seen_cursor':set(),'order':[]})
  if edge<c['last_edge']:raise ValueError('Nonmonotonic source edge')
  if bool(active)!=(edge<egs)or(active and cursor!=edge):raise ValueError('Source scrub progression inconsistent with actual EG count')
  c['last_edge']=edge
  if active:c['seen_cursor'].add(cursor)
  word=0x07070707 if label==7 else 0
  for index,mask in enumerate(masks):
   if mask<0 or mask>0xffffffff:raise ValueError('Write bit mask exceeds32 bits')
   c['memory'][eg][index]=(c['memory'][eg][index]&~mask)|(word&mask);c['known'][eg][index]|=mask
  if label==0:c['zero_egs'].add(eg)
  else:c['producer_egs'].add(eg);c['first_producer']=edge if c['first_producer']is None else c['first_producer']
  c['writes']+=1;c['order'].append((edge,eg,label))
 return cases

def validate(cases,summary):
 result=[]
 if len(cases)!=len(summary):raise ValueError('Missing/extra writer cases')
 for row in summary:
  key=(row['profile'],row['kind'],row['seed']);c=cases[key];egs,dlen=(64,128)if key[0]=='compute'else(32,256);target=8*(256//dlen);end=16*(256//dlen);unknown=sum(mask!=0xffffffff for group in c['known']for mask in group);zero=sum(v==0 for group in c['memory'][target:end]for v in group);seven=sum(v==0x07070707 for group in c['memory'][target:end]for v in group);readback=c['memory'][target][0]|c['memory'][target][1]<<32
  expected={'scrubbed_EGs_seen':len(c['zero_egs']),'producer_EGs_seen':len(c['producer_egs']),'physical_writes':c['writes'],'destination_zero_words':zero,'destination_seven_words':seven,'unwritten_unknown_words':unknown,'scalar_readback':readback,'first_nonzero_write_edge':c['first_producer']}
  if any(row[n]!=value for n,value in expected.items()):raise ValueError('Accepted-write symbolic reader disagrees with observed RAM/readback: '+str(key))
  if c['seen_cursor']!=set(range(egs)):raise ValueError('Incomplete reset cursor history')
  overwritten=[eg for eg in c['producer_egs']if any(label==7 and group==eg and any(later>edge and group2==eg and label2==0 for later,group2,label2 in c['order'])for edge,group,label in c['order'])]
  result.append({'profile':key[0],'kind':key[1],'seed':key[2],**expected,'producer_EGs_later_zeroed':sorted(overwritten),'qualified_abstraction':'Post-scrub first-access only; early compute load must preserve actual write ordering'if overwritten else'Observed producer data wins in this finite scenario'})
 return result

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=R/'build/saturn-timing-reset-writers-v1';j=json.loads((base/'report.json').read_text());cases=read_transcript(base/'stdout');results=validate(cases,j['results']);changed=[dict(x)for x in j['results']];changed[0]['scalar_readback']^=1
 try:validate(cases,changed)
 except ValueError as ex:mutation=str(ex)
 else:raise ValueError('Reader missed changed expected readback')
 boot=[]
 for case in ['vme','rvv','fpcomp','shared-fpu']:
  for h in range(3):
   report=R/'build/saturn-timing-replay-v2'/case/f'hart{h}.benchmark-window.json';first=json.loads(report.read_text())['first_EX_candidate_edge'];fields=json.loads((R/'build/saturn-timing-source-v1'/('rocket'if h==2 else'compute')/'ports.json').read_text())['words']['input'];reset=next(f['word_index']for f in fields if f['word_name']=='reset');last=-1
   for line in(R/'build/saturn-timing-replay-v2'/case/f'hart{h}.input').open():
    words=line.split();edge=int(words[1])
    if edge>first:break
    if int(words[2+reset]):last=edge
   margin=first-last-1;required=32 if h==2 else 64
   if margin<required:raise ValueError('Observed guest reaches vector before actual source scrub completion')
   boot.append({'case':case,'hart':h,'first_EX_candidate_edge':first,'last_reset_edge_before_first_EX':last,'post_reset_edges_before_first_EX':margin,'required_scrub_edges':required,'scope':'Observed frozen ELF/startup only; not a universal boot lower-bound proof'})
 vme=R/'build/saturn-timing-reset-vme-v2/report.json';vrf=R/'build/saturn-timing-reset-scrub-v1/report.json';inputs=[Path(__file__),base/'stdout',base/'report.json',vme,vrf];report={'schema':'iris.saturn_reset_independent_transcript.v1','input_sha256':{str(p):sha(p)for p in inputs},'writer_cases':results,'actual_guest_boot_margins':boot,'wrong_readback_summary_rejected':True,'mutation_reason':mutation,'universal_first_access_zero_abstraction_proven':False,'instant_constructor_zero_allowed':False,'tile_reset_zero_proven':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'writer_cases':len(results),'bounded_compute_load_overwrite_cases':sum(bool(x['producer_EGs_later_zeroed'])for x in results),'minimum_observed_boot_margin':min(x['post_reset_edges_before_first_EX']for x in boot),'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
