#!/usr/bin/env python3
"""Qualify real history parity and profile full events with honest payload scope."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions
from iris_model.counter_regions import annotate,observations
from iris_model.event_lifecycle import completed,cancelled
from iris_model.report import profile,symbols

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):
 with Path(p).open()as f:return json.load(f)
def check_receipt(folder):
 r=load(folder/'run.json')
 if r.get('pass')is not True or r.get('exit_status')!=0 or r.get('timed_out')is not False or r.get('owned_process_cleanup_complete')is not True:raise ValueError('Actual normal guest exit and complete local ownership cleanup required')
 if r.get('debug_commands_end')!='unbounded silent run; no quit command':raise ValueError('Readback must resume to normal HTIF exit, never forced quit')
 for name,value in {**r['input_sha256'],**r['output_sha256']}.items():
  if sha(name)!=value:raise ValueError('Execution source/evidence changed')
 return r


def decode(text):
 lines=text.splitlines()
 if any(l!=':'and not re.fullmatch('0x[0-9a-f]{16}',l)for l in lines):raise ValueError('Unexpected debugger/error output')
 words=[int(l,16)for l in lines if l!=':']
 if len(words)!=122 or words[0]!=0 or words[-1]!=0:raise ValueError('Complete stable measured-memory readback required')
 regions=[];active_words=0
 for k in range(2):
  for h in range(3):
   i=3*k+h;begin,end,instret,value=words[1+4*i:5+4*i]
   if not 0<=begin<end<1<<64 or instret<=0:raise ValueError('Invalid actual target counter interval')
   expected_word=5 if h==2 else 0x40800000 if k else 4;count=8 if h==2 else 32
   packed=words[25+16*i:25+16*(i+1)];raw=[v for w in packed for v in(w&0xffffffff,w>>32)]
   if raw!=[expected_word]*count+[0]*(32-count)or value!=count*expected_word:raise ValueError('Independent complete per-word INT32/FP32/vector golden mismatch')
   active_words+=count
   regions.append({'case_id':'profile.source.VME.E4M3'if k else'profile.source.VME.uint8','region':'kernel','hart':h,'start_cycle':begin,'end_cycle':end,'instret_delta':instret,'checksum':value,'expected_checksum':count*expected_word,'pass':True})
 return regions,active_words


def main():
 p=argparse.ArgumentParser(__doc__)
 for n in('build','bounded','full','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);started=time.monotonic()
 b,f=check_receipt(a.bounded),check_receipt(a.full)
 for name in('stdout','stderr','features.jsonl'):
  if(a.bounded/name).read_bytes()!=(a.full/name).read_bytes():raise ValueError('History changes actual '+name)
 if(a.full/'stdout').read_bytes()!=b'P':raise ValueError('Normal guest success marker missing')
 rb=(a.bounded/'job.fixture').read_bytes();rf=(a.full/'job.fixture').read_bytes()
 if rf.replace(b'iris-empirical-priority-28a0-v2 full',b'iris-empirical-priority-28a0-v2 bounded')!=rb:raise ValueError('Only exact history token may change')
 regions,word_count=decode((a.full/'stderr').read_text());console=''.join('IRIS_REGION '+json.dumps(r)+'\n'for r in regions);(out/'observed-regions.txt').write_text(console)
 elf=a.build/'profile-vme.elf';rom=ROOT/'board/evidence/bootrom.rv64.img';nm=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm')
 if sha(elf)!=f['ELF_sha256']or sha(elf)!=b['ELF_sha256']:raise ValueError('Actual ELF identity mismatch')
 print('Loading exact full graph',flush=True);g=load(a.full/'graph.json')
 if g.get('schema_version')!=1 or not isinstance(g.get('events'),list):raise ValueError('Complete full-history schema1 event/DAG required')
 prefix=[json.loads(l)for l in(a.full/'features.jsonl').read_text().splitlines()]
 reads=observations(g,Instructions(elf,rom));index={(r['hart'],r['value']):r for r in reads if r['csr'] in(0xb00,0xc00)and not r['result_discarded']}
 for r in regions:
  begin=index[r['hart'],r['start_cycle']];end=index[r['hart'],r['end_cycle']]
  between=[x for x in reads if x['hart']==r['hart']and begin['sequence']<x['sequence']<end['sequence']and x['csr']in(0xb02,0xc02)]
  if len(between)!=2 or (between[1]['value']-between[0]['value'])%(1<<64)!=r['instret_delta']:raise ValueError('Actual minstret readbacks disagree with ELF region')
 print('Projecting six actual counter regions',flush=True);g=annotate(g,console,Instructions(elf,rom));table=symbols(elf,str(nm))
 print('Profiling original events and dependency spans',flush=True);summary,timeline=profile(g,500000000,'provider-selected parent base_hz500MHz; exact history-only job fixture',table)
 logical=[]
 for boundary in g['region_boundaries']:
  events=[e for e in g['events']if e['hart']==boundary['hart']and e['macs']and boundary['start']<=e['start']and e['end']<=boundary['end']and completed(e)and not cancelled(e)]
  macs=sum(e['macs']for e in events);expected=4096 if boundary['hart']<2 else 0
  logical.append({'hart':boundary['hart'],'region':boundary['region'],'completed_model_requested_MACs':macs,'expected_algorithmic_MACs':expected,'model_requested_work_matches_algorithm':macs==expected,'physical_completed_MACs':None,'physical_memory_bytes':None,'physical_bandwidth':None,'roofline':None,'stall_breakdown':None})
 summary['execution_provenance']={'run_receipt_sha256':sha(a.full/'run.json'),'ELF_sha256':sha(elf),'full_graph_sha256':sha(a.full/'graph.json'),'native_binary_sha256':f['native_binary_sha256'],'calibration_identity':f['calibration_identity'],'normal_HTIF_guest_exit':True,'only_history_token_changed':True,'guest_region_source':'actual post-ROI stored values read by standard debugger and joined to actual captured CSR instruction/results; resumed to normal HTIF exit without quit'}
 summary['payload_semantic_review']={'arithmetic':'Event MAC fields are requested algorithmic model work credited on modeled completion; these are not observed physical OPU executions.','traffic':'Event byte fields are requested model payloads across mixed actors; they do not establish physical per-level completed memory traffic or DRAM bandwidth.','physical_traffic_available':False,'physical_achieved_accelerator_rate_available':False,'roofline_available':False,'stall_classification_available':False,'logical_regions':logical}
 summary['limitations']+=['The legacy28 effective timing model is not RTL or2percent certified.','Physical traffic/DRAM bandwidth unknown; no physical roofline or calibrated stall causes are supplied.','Full native history includes startup and post-ROI work. Observed regions use actual captured CSR intersections.']
 print('Writing JSON and Perfetto artifacts',flush=True)
 with(out/'summary.json').open('w')as stream:json.dump(summary,stream,indent=2);stream.write('\n')
 with(out/'trace.json').open('w')as stream:json.dump(timeline,stream);stream.write('\n')
 report={'schema':'iris.actual_ELF_full_graph_profile_workflow.v1','pass':True,'all144_active_output_words_independently_checked':word_count==144,'additional_zero_padding_words_checked':48,'bounded_full_stdout_parity':True,'bounded_full_debug_readback_counter_parity':True,'bounded_full_all24_feature_prefixes_byteequal':len(prefix)==24,'normal_guest_exit_verified':True,'forced_debug_quit':False,'actual_mcycle_region_boundaries':12,'actual_minstret_pairs':6,'regions':6,'full_graph_events':len(g['events']),'full_graph_partial_at_HTIF_exit':g.get('partial',False),'functions_attributed':len(summary['functions']),'physical_traffic_available':False,'roofline_available':False,'stall_breakdown_available':False,'all_logical_MAC_work_matches_algorithm':all(x['model_requested_work_matches_algorithm']for x in logical),'model_payload_review':logical,'hardware_contacted':False,'global_heldout_timings_consumed':False,'calibration_changed':False,'full_2pct_certified':False,'source_image_association_verified':False,'input_sha256':{str(x.resolve()):sha(x)for x in(Path(__file__),a.build/'build.json',elf,a.bounded/'run.json',a.full/'run.json',a.full/'graph.json',ROOT/'iris_model/graph_run_buffered.py',ROOT/'iris_model/report.py',ROOT/'iris_model/counter_regions.py',ROOT/'iris_model/event_lifecycle.py',ROOT/'iris_model/memory_profile.py',nm)},'host_seconds':time.monotonic()-started}
 report['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'events':report['full_graph_events'],'logical_work_matches':report['all_logical_MAC_work_matches_algorithm'],'output':str(out)}))


if __name__=='__main__':main()
