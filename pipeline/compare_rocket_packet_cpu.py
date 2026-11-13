#!/usr/bin/env python3
"""Compare development CPU packet rows; never feed labels into the simulator."""
import argparse,csv,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--reference',type=Path,default=ROOT/'build/fpga-cpu-layout-v2-001-analysis/regions.csv');p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);rows=[json.loads(x)for x in(a.model/'main-regions.jsonl').read_text().splitlines()];ref={(x['case_id'],int(x['hart'])):x for x in csv.DictReader(a.reference.open())};errors=[];groups={}
 def metrics(v):
  av=sorted(abs(x)for x in v);return{'rows':len(v),'median_signed_percent':statistics.median(v),'median_absolute_percent':statistics.median(av),'p90_absolute_percent':av[int(.9*(len(av)-1))],'maximum_absolute_percent':max(av),'within2':sum(x<=2 for x in av)}
 for row in rows:
  actual=ref[(row['case_id'],row['hart'])]
  for key in['instret_delta','checksum','counter_end','loop_pc','begin_pc','end_pc']:assert row[key]==int(actual[key]),(row['case_id'],row['hart'],key)
  predicted=row['end_cycle']-row['start_cycle'];real=int(actual['cycles']);error=100*(predicted-real)/real;errors.append(error);key=str(row['hart'])+':'+row['mode'];g=groups.setdefault(key,{'all':[],'warm_n_ge64':[],'warm_n_ge256':[]});g['all'].append(error)
  if row['repeat']>=1:
   for lower in[64,256]:
    if row['n']>=lower:g['warm_n_ge'+str(lower)].append(error)
 assert len(rows)==2304;result={'schema':'iris.rocket_packet.CPU_layout_development_comparison.v2','pass_functional':True,'main_regions':len(rows),'metrics':metrics(errors),'groups':{key:{name:metrics(v)for name,v in g.items()}for key,g in groups.items()},'native_sha256':sha(a.binary),'new_model_fitted_to_these_cycles':False,'global_heldout_timing_consumed':False,'scope':'sourceIBuf+experimentalwordarrival/predictorfallback, exactELFcomponentdevelopment; not fullmodel or heldout2pct certification','input_sha256':{str(x.resolve()):sha(x)for x in[Path(__file__).resolve(),a.model/'main-regions.jsonl',a.model/'validation.json',a.reference,a.binary]}};out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['metrics']));print(json.dumps(result['groups']['2:wide']['warm_n_ge256']))
if __name__=='__main__':main()
