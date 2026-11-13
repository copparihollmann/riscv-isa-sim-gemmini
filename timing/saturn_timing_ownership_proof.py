#!/usr/bin/env python3
"""Continuous source/native ownership replay plus qualified transcript corruptions."""
import argparse,array,concurrent.futures,gzip,hashlib,json,shutil,struct,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
BASE=R/'build/saturn-timing-activity-component-v1-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def fields(schema,profile):
 result={}
 for f in schema['profiles'][profile]['fields']:
  for w in f['words']:result[f['name']+('@'+str(w['lo'])if f['width']>64 else'')]=w['index']
 return result
def mutation(out,capture,ownership_schema,case,name,target,gate):
 base=load(BASE/'build/saturn-timing-activity-schema-v1/schema.json');extra=load(ownership_schema);profile='compute';ai=fields(base,profile);xi=fields(extra,profile)
 ports=load(R/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/ports.json');ni=len(ports['words']['input']);no=len(ports['words']['output']);physical={}
 # The physical declaration catalog includes clock; the driver word schema
 # deliberately excludes it. Bind the actual driver words, never re-count
 # declarations and accidentally offset every valid/ready/control field.
 for direction,offset in [('input',0),('output',ni)]:
  for f in ports['words'][direction]:physical[f['word_name']]=offset+f['word_index']
 def locate(token):
  if token in physical:return 'activity',physical[token]
  if token in ai:return 'activity',ni+no+ai[token]
  if token in xi:return 'ownership',xi[token]
  raise ValueError('Unresolved mutation field '+token)
 kind,index=locate(target);dest=out/(name+'.'+kind+'.bin.gz');source=capture/case
 with gzip.open(source/'activity.bin.gz','rb')as af,gzip.open(source/'ownership.bin.gz','rb')as xf,gzip.open(dest,'wb',compresslevel=1)as mutated:
  ah=af.read(32);xh=xf.read(32);mutated.write(ah if kind=='activity'else xh);found=None
  while True:
   ab=af.read(32);xb=xf.read(32)
   if len(ab)!=32 or len(xb)!=32:raise ValueError('No actual qualified corruption gate '+name)
   aheader=struct.unpack('<4Q',ab);xheader=struct.unpack('<4Q',xb)
   if aheader[:3]!=xheader[:3]:raise ValueError('Mutation source joins differ')
   av=array.array('Q');av.frombytes(af.read(aheader[3]*8));xv=array.array('Q');xv.frombytes(xf.read(xheader[3]*8))
   def read(n):k,j=locate(n);return(av if k=='activity'else xv)[j]
   qualify=aheader[2]==0 and not read('reset') and all(bool(read(n))==expected for n,expected in gate)
   if qualify:
    values=av if kind=='activity'else xv;before=values[index];values[index]^=1;found={'tb':aheader[0],'source_edge':aheader[1],'hart':0,'target_field':target,'before':before,'after':values[index]}
   mutated.write(ab if kind=='activity'else xb);mutated.write((av if kind=='activity'else xv).tobytes())
   if found:break
 return dest,kind,found
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--captures',type=Path,required=True);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'runner.py');replay=a.replay.resolve();captures=a.captures.resolve();sdk=a.sdk.resolve();bridge=a.bridge.resolve()
 def positive(case,seed):
  stem=f'{case}-seed{seed}';cmd=[str(replay/'replay'),str(captures/case/'activity.bin.gz'),str(captures/case/'ownership.bin.gz'),str(seed),str(out/(stem+'-events.ndjson.gz'))];start=time.monotonic()
  with(out/(stem+'.stdout')).open('w')as stdout,(out/(stem+'.stderr')).open('w')as stderr:q=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=600)
  lines=(out/(stem+'.stdout')).read_text().splitlines();result=json.loads(lines[-1])if q.returncode==0 else None
  return {'case':case,'seed':seed,'argv':cmd,'exit_status':q.returncode,'host_seconds':time.monotonic()-start,'result':result}
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:runs=list(pool.map(lambda pair:positive(*pair),[(case,seed)for case in ['vme','rvv','fpcomp','shared-fpu']for seed in [0,17,91]]))
 specs=[('dispatcher-generation','vme','dis.debug_id_ctr',[('dis.io_dis_valid',True),('dis.io_dis_ready',True)]),('masked-VRF-data','vme','vu.vrf.vrf.vrf_0.write_bits_data@0',[('vu.vrf.vrf.vrf_0.io_write_valid',True)]),('INT8-MRF-data','vme','vu.vopu.clusters_0_0.cells_0_0._sum_int_T_1',[('vu.vopu.clusters_0_0.cells_0_0.io_macc',True),('vu.vopu.clusters_0_0.cells_0_0.io_fp8',False)]),('zero-MRF-index','vme','vu.vopu.clusters_0_0.cells_0_0.io_mrf_idx',[('vu.vopu.clusters_0_0.cells_0_0.io_zero',True)]),('load-response-generation','fpcomp','vmu.io_vu_lresp_q.do_enq',[('vmu.io_vu_lresp_q.do_enq',True)]),('physical-source-ID','vme','auto_atl_out_a_bits_source',[('auto_atl_out_a_valid',True),('auto_atl_out_a_ready',True)])]
 negatives=[]
 for name,case,target,gate in specs:
  path,kind,where=mutation(out,captures,sdk/'sdk/ownership-schema.json',case,name,target,gate);activity=path if kind=='activity'else captures/case/'activity.bin.gz';ownership=path if kind=='ownership'else captures/case/'ownership.bin.gz';cmd=[str(replay/'replay'),str(activity),str(ownership),'17',str(out/(name+'-events.ndjson.gz'))]
  with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:q=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=300)
  reason=(out/(name+'.stderr')).read_text().splitlines()[-1];valid=q.returncode!=0 and all(x not in reason for x in ['Truncated','Extra ownership','Partial source','schema width mismatch']);negatives.append({'name':name,'case':case,'argv':cmd,'mutation':where,'exit_status':q.returncode,'reason':reason,'meaningful_refusal':valid})
 inputs=[Path(__file__),replay/'build.json',replay/'replay',sdk/'build.json',sdk/'sdk/ownership-schema.json',sdk/'sdk/libiris_saturn_timing.a',bridge/'build.json',bridge/'sdk/libiris_saturn_live_bridge.a',BASE/'report.json']
 for case in ['vme','rvv','fpcomp','shared-fpu']:inputs += list((captures/case).glob('*'))
 report={'schema':'iris.saturn_causal_ownership_numeric_proof.v1','pass':all(x['exit_status']==0 for x in runs)and all(x['meaningful_refusal']for x in negatives),'positive_runs':runs,'negative_controls':negatives,'input_sha256':{str(x):sha(x)for x in inputs if x.is_file()},'continuous_state_replay':True,'only_source_physical_inputs_driven':True,'caller_nodes_are_metadata':True,'numeric_payload_knownness_inferred':False,'actual_native_Spike_ELF_execution':False,'whole_SoC_source_capture_not_Ethan_image_attestation':True,'hardware_contacted':False};report['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'report_sha256':sha(out/'report.json'),'positive_runs':len(runs),'negative_controls':negatives}))
 if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
