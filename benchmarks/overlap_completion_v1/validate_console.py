#!/usr/bin/env python3
"""Independent full-word validation of the postmeasurement overlap console."""
import argparse,json,struct
from pathlib import Path

def exact(v):
 if type(v)is not int or not 0<=v<1<<64:raise ValueError('Exact unsigned target integer required')
 return v
def expected(c,j):
 if c['hart']==2:return c['count']+1
 tile,col=divmod(j,32)
 if col>=c['edge']:return 0
 n=c['count']//4 if c['rotate']else 0 if tile else c['count']
 return struct.unpack('<I',struct.pack('<f',float(n)))[0]if c['fp8']else n
def validate(text,corpus):
 cases=corpus['cases'];regions={};words={};done=[]
 for line in text.splitlines():
  if line.startswith('IRIS_REGION '):
   r=json.loads(line[len('IRIS_REGION '):]);case=r['case_id'];prefix='overlap.v1.case.'
   if not case.startswith(prefix)or not case[len(prefix):].isdigit():raise ValueError('Unknown case identity')
   i=int(case[len(prefix):]);c=cases[i]
   if i in regions or r['region']!='total'or exact(r['hart'])!=c['hart']or exact(r['failed_elements']):raise ValueError('Duplicate/wrong/failed region')
   values=[exact(r[k])for k in('start_cycle','issue_end_cycle','fence_end_cycle','end_cycle')]
   if values!=sorted(set(values))or exact(r['instret_delta'])==0:raise ValueError('Unordered/empty region boundaries')
   regions[i]=r
  elif line.startswith('IRIS_WORD '):
   r=json.loads(line[len('IRIS_WORD '):]);i=exact(r['case']);j=exact(r['index']);v=exact(r['value']);c=cases[i]
   if exact(r['hart'])!=c['hart']or j>=(c['edge']if c['hart']==2 else 128)or(i,j)in words:raise ValueError('Duplicate/unowned word')
   if v!=expected(c,j):raise ValueError('Independent per-element golden mismatch')
   words[i,j]=v
  elif line.startswith('IRIS_OVERLAP_DONE '):done.append(line)
 if len(regions)!=len(cases)or done!=[f'IRIS_OVERLAP_DONE failed=0 cases={len(cases)}']:raise ValueError('Incomplete actual console')
 for i,c in enumerate(cases):
  n=c['edge']if c['hart']==2 else 128
  if sum(words.get((i,j),-1)for j in range(n))!=exact(regions[i]['checksum']):raise ValueError('Incomplete words/checksum')
 if len(words)!=sum(c['edge']if c['hart']==2 else 128 for c in cases):raise ValueError('Word coverage differs')
 return {'pass':True,'regions':len(regions),'independent_numeric_elements':len(words),'all_four_boundaries_retained':True,'timing_reference_available':False}
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--console',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);a=p.parse_args();print(json.dumps(validate(a.console.read_text(),json.loads(a.corpus.read_text()))))
if __name__=='__main__':main()
