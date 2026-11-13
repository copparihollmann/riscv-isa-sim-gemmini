"""One exact hart2/VLE32 m8 256B diagnostic, never calibration."""
import importlib.util,json,struct
from pathlib import Path
from rvv_identify_tk_review import proof as parent_proof
ROOT=Path(__file__).resolve().parents[1];BENCH=ROOT/'benchmarks/rvv_hart2_256_probe_v1'
spec=importlib.util.spec_from_file_location('hart2_probe_validator',BENCH/'validate.py');val=importlib.util.module_from_spec(spec);spec.loader.exec_module(val)
ELF='2025b90905a31c91fca1589ed685ec8eee6cc6acdbea4ddff4f31a81842ed5a6';ROLE='rvv_hart2_256B_stage_diagnostic_v1'
def need(ok,msg):
 if not ok:raise ValueError(msg)
class Validator:
 def validate_corpus(self,c):
  need(c['diagnostic_only']is True and c['calibration_usable']is False and c['all_output_after_measurements']is False and c['fitting_only']is False and c['ROI_contains_progress_and_is_not_calibration']is True and c['regions']==1 and c['trials']==1 and len(c['cases'])==1,'Exact diagnostic scope')
  r=c['cases'][0];need([r[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')]==[2,32,8,0,16,256,2,0,64,1]and r['expected_checksum']==val.golden()and r['case_id']=='rvv.identify.load.e32.m8.mode0.n16.b256.hart2.trial0','Exact one-case source geometry/golden')
 def validate(self,text,c):self.validate_corpus(c);return val.validate(text)
def validator():return Validator()
def inspect(raw,c,layout):
 validator().validate_corpus(c);e=parent_proof.Elf(raw);address,size=e.syms['experiments'];need(size==48,'One48B compiledcase');name,*fields=struct.unpack('<Q10I',e.read(address,48));r=c['cases'][0];need(e.string(name)==r['case_id']and fields==[r[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')],'Compiled exactcase')
 objects={k:dict(address=e.syms[k][0],size=e.syms[k][1])for k in('rvv_records','rvv_record_count','rvv_measurements_done','parked','completion')};need(objects==layout['objects']and objects['rvv_records']['size']==192 and layout['records']==1 and layout['record_bytes']==192 and e.read(objects['rvv_measurements_done']['address'],8)==bytes([255])*8,'Compiled recordABI/sentinel')
 return dict(compiled_case_records=1,table_stride=48,compiled_geometry_counts_roles_and_unique_IDs=True,record_stride=192,record_fields=layout['fields'],buffer_objects=objects,source_count_loop_and_64_per_element_goldens_verified=True,known_filebacked_sentinel=True,padded_controls_and_records_disjoint=True)
def flatten(c):
 validator().validate_corpus(c);r=c['cases'][0];return [dict(id=r['case_id'],active_harts=[2],expected_checksums_by_hart=[val.golden()]*3,parent_case_id=r['parent_case_id'],semantic_parent_case_id=r['semantic_parent_case_id'],trial_id=0,region='kernel',suite='rvv_identify',internal_split='diagnostic_only',corpus_split=ROLE)]
def inspect_clint_window(raw):
 e=parent_proof.Elf(raw);start,size=e.syms['benchmark_main'];pc=start;instructions=[]
 while pc<start+size:
  half=int.from_bytes(e.read(pc,2),'little');n=4 if half&3==3 else 2;w=int.from_bytes(e.read(pc,n),'little');instructions.append((pc,n,w));pc+=n
 cycles=[p for p,n,w in instructions if n==4 and w&0x707f==0x2073 and w>>20==0xb00];retired=[p for p,n,w in instructions if n==4 and w&0x707f==0x2073 and w>>20==0xb02]
 need(len(cycles)==len(retired)==3 and cycles[0]<retired[0]<retired[1]<cycles[1]<retired[2]<cycles[2],'Actual ordered diagnostic CSR reads')
 fences=[p for p,n,w in instructions if w==0x0330000f and cycles[1]<p<cycles[2]];need(len(fences)==1,'Actual diagnostic drain fence')
 return dict(mcycle_begin_pc=cycles[0],mcycle_issue_pc=cycles[1],mcycle_drain_pc=cycles[2],real_minstret_read_pcs=retired,fence_between_issue_and_drain_pc=fences[0],ROI_contains_UART_progress=True,calibration_usable=False,actual_static_order_verified=True)

def progress_prefix(text,corpus):
 validator().validate_corpus(corpus);boot=set();seq=[];wait=set();seen=set();last=None
 for line in text.splitlines():
  if not line.startswith('IRIS_RVV_DIAG '):continue
  r=json.loads(line.split(' ',1)[1]);need(set(r)=={'hart','case_index','stage'}and type(r['hart'])is int and type(r['case_index'])is int and type(r['stage'])is str,'Typed stage');h,i,s=r['hart'],r['case_index'],r['stage'];need(h in(0,1,2)and(h,i,s)not in seen,'Unique marker');seen.add((h,i,s));last=r
  if s=='BOOT':need(i==1,'Boot sentinel');boot.add(h);continue
  need(h in boot and i==0,'Ownboot and case0')
  if s=='WAIT':need(h in(0,1),'Inactivewait');wait.add(h)
  else:need(h==2,'Activehart2');seq.append(s);need(seq==val.STAGES[:len(seq)],'Qualified stage prefix')
 return dict(schema='iris.hart2_256B_diagnostic_progress.v1',boot_harts=sorted(boot),inactive_wait_harts=sorted(wait),active_stages=seq,last_marker=last,markers=len(seen),calibration_usable=False,completion_observed=bool(seq and seq[-1]=='DONE'))
