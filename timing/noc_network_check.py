#!/usr/bin/env python3
"""Continuously compare full endpoint-TL replay with whole-SoC physical wires."""
import argparse,hashlib,itertools,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];RTL=R/'build/noc-network-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def schema():return json.loads((R/'build/noc-network-source-v2/extraction.json').read_text())['physical_ports']
def frames(case):
 count=len(schema());previous=None
 with(RTL/(case+'.stderr')).open()as f:
  for line in f:
   if not line.startswith('RTL_NOC_NETWORK '):continue
   data=line[16:].rstrip().split(',');assert len(data)==count+1,('Physical TL frame width',len(data));tb=int(data[0]);values=[int(x,16)for x in data[1:]]
   if previous is None:assert tb==3 and values[165]==1,'Actual physical reset start required'
   else:assert tb==previous+2,'Missing/duplicate physical edge'
   previous=tb;yield tb,values
def compare(case,path):
 fields=schema();outputs=[x for x in fields if x['direction']=='output'];indices={x['name']:208+x['index']for x in outputs};comparisons=active=edges=0;actual_count=0
 with path.open()as f:
  pairs=itertools.zip_longest(frames(case),(line for line in f if line.strip()and not line.startswith('-')))
  for wanted,line in pairs:
   if wanted is None or line is None:raise ValueError('Incomplete/reordered full network replay')
   tb,values=wanted;got=[int(x)for x in line.split()];actual_count+=1;edges+=1
   if len(got)!=296 or got[0]!=tb:raise ValueError('Physical TL result row width/order')
   if values[165]:continue
   for field in outputs:
    name=field['name'];index=field['index']
    if '_bits_'in name:
     valid=name.split('_bits_')[0]+'_valid'
     if valid not in indices:raise ValueError('Missing source validity boundary for '+name)
     if not values[indices[valid]]:continue
    comparisons+=1
    if got[index+1]!=values[208+index]:raise ValueError('TB'+str(tb)+' '+name+' native='+str(got[index+1])+' wholeRTL='+str(values[208+index]))
   active+=1
 return {'edges':edges,'post_reset_edges':active,'physical_signal_comparisons':comparisons,'pass':True}
def run(case,binary,out,mode):
 out.mkdir(parents=True,exist_ok=True);stem=case+'-'+mode;input_file=out/(stem+'.input')
 if input_file.exists():raise ValueError('Preserve existing replay evidence')
 with input_file.open('w')as f:
  for tb,values in frames(case):
   f.write(('evaluate'if mode=='phased'else mode)+' '+str(tb)+' '+' '.join(str(x)for x in values[:208])+'\n')
   if mode=='phased':f.write('sample\ncommit\n')
 started=time.monotonic();argv=[str(binary),'--seed','1']
 with input_file.open()as stdin,(out/(stem+'.stdout')).open('w')as stdout,(out/(stem+'.stderr')).open('w')as stderr:q=subprocess.run(argv,stdin=stdin,stdout=stdout,stderr=stderr,timeout=180)
 elapsed=time.monotonic()-started
 if q.returncode:raise ValueError('Native full NoC refused: '+(out/(stem+'.stderr')).read_text()[-1600:])
 result=compare(case,out/(stem+'.stdout'));result.update(case=case,mode=mode,argv=argv,host_seconds=elapsed,native_sha256=sha(binary),physical_input_sha256=sha(input_file),whole_rtl_trace_sha256=sha(RTL/(case+'.stderr')),stdout_sha256=sha(out/(stem+'.stdout')),stderr_sha256=sha(out/(stem+'.stderr')),actual_reset=True,internal_state_inputs=False,hardware_contacted=False);(out/(stem+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return result
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--case',choices=['original9','control8','fenced9','peer','coherent'],required=True);p.add_argument('--binary',type=Path,default=R/'build/noc-network-native-v2/noc-network');p.add_argument('--output',type=Path,default=R/'build/noc-network-replay-v1');p.add_argument('--mode',choices=['step','repeat','phased'],default='step');a=p.parse_args();run(a.case,a.binary.resolve(),a.output.resolve(),a.mode)
if __name__=='__main__':main()
