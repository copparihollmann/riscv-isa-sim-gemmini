#!/usr/bin/env python3
"""Source-only conditional capacity catalog; no runtime model or hardware access."""
import argparse,bisect,collections,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SV_SHA='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
MODULES=('DigitalTop','TilePRCIDomain','TilePRCIDomain_2','ShuttleTile','RocketTile','ShuttleCore','Rocket','ShuttleFPPipe','FPU','FPUFMAPipe_l4_f16','FPUFMAPipe_l4_f32','FPUFMAPipe_l4_f64','FPUFMAPipe_l3_f16','FPUFMAPipe_l3_f32','FPUFMAPipe_l3_f64','VectorBackend','VectorBackend_2','SaturnShuttleUnit','SaturnRocketUnit','OuterProductUnit','OuterProductCluster','OuterProductCluster_4','OuterProductCell','OuterProductSequencer','FPFMAPipe','SegmentedFMAPipe','SharedScalarElementwiseFPFMA','ExecutionUnitint','ExecutionUnitfp','ExecutionUnitfp_int','IntegerPipe','IntegerPipe_2','AdderArray','AdderArray_6','ExecuteSequencer','ExecuteSequencer_1','ExecuteSequencer_4','VectorMemUnit','VectorMemUnit_2','RegisterAccess','RegisterAccess_2','RegisterFile','RegisterFile_2','TLSplitInterface','TLSplitInterface_2')

def require(ok,message):
 if not ok:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(path):return sha(Path(path).read_bytes())
def split_modules(text):
 out={};newlines=[m.start()for m in re.finditer('\n',text)]
 for m in re.finditer(r'^module\s+(\w+)\s*\(',text,re.M):
  name=m.group(1);end=text.index('endmodule',m.end())+len('endmodule');require(name not in out,'Duplicate module '+name)
  out[name]={'text':text[m.start():end],'start_line':bisect.bisect_left(newlines,m.start())+1,'end_line':bisect.bisect_left(newlines,end)+1}
 return out

def instances(body):return re.findall(r'^\s{2}([A-Z]\w*)\s+(\w+)\s*\(',body,re.M)
def count(body,typename):return sum(t==typename for t,n in instances(body))
def port_width(body,name):
 matches=re.findall(r'^\s*(input|output)\s+(?:\[(\d+):0\]\s+)?'+re.escape(name)+r'\s*[,)]',body,re.M)
 require(len(matches)==1,'Unique port declaration required: '+name)
 return int(matches[0][1])+1 if matches[0][1]else 1

def derive_geometry(modules):
 t=lambda n:modules[n]['text']
 require(count(t('DigitalTop'),'TilePRCIDomain')==2 and count(t('DigitalTop'),'TilePRCIDomain_2')==1,'Three-hart tile placement changed')
 require(count(t('TilePRCIDomain'),'ShuttleTile')==1 and count(t('TilePRCIDomain_2'),'RocketTile')==1,'Tile domain ownership changed')
 require(count(t('ShuttleTile'),'SaturnShuttleUnit')==1 and count(t('RocketTile'),'SaturnRocketUnit')==1,'Vector placement changed')
 require(count(t('VectorBackend'),'OuterProductUnit')==1 and count(t('VectorBackend_2'),'OuterProductUnit')==0,'OPU placement changed')
 clusters=[(typ,name)for typ,name in instances(t('OuterProductUnit'))if typ.startswith('OuterProductCluster')]
 require(len(clusters)==16 and {name for _,name in clusters}=={'clusters_%d_%d'%(i,j)for i in range(4)for j in range(4)},'OPU cluster geometry changed')
 for typ in set(typ for typ,name in clusters):
  cells=[name for c,name in instances(t(typ))if c=='OuterProductCell']
  require(set(cells)=={'cells_%d_%d'%(i,j)for i in range(4)for j in range(4)} and len(cells)==16,'OPU cell geometry changed')
 require(re.search(r'reg \[1:0\] fp8_hist_valid;',t('OuterProductSequencer')),'FP8 same-entry history changed')
 require('fp8_hist_valid[0]'in t('OuterProductSequencer')and'fp8_hist_valid[1]'in t('OuterProductSequencer'),'FP8 history comparisons changed')
 require('assign fma_io_validin = io_macc & io_fp8;'in t('OuterProductCell'),'FP8 accepted-MAC predicate changed')
 require('MulAddRecFNPipe_l2_e8_s24' in t('OuterProductCell'),'FP8 pipeline depth/type changed')
 byte_widths=[]
 for name in ('AdderArray','AdderArray_6'):
  ports=re.findall(r'^\s*output\s+\[7:0\]\s+io_out_(\d+)\s*[,)]',t(name),re.M)
  require(set(map(int,ports))==set(range(len(ports))) and len(ports)in(16,32),'Integer byte-array geometry changed');byte_widths.append(len(ports))
 require(byte_widths==[16,32],'Configured integer arrays changed')
 require(count(t('ExecutionUnitint'),'IntegerPipe')==1 and count(t('ExecutionUnitfp_int'),'IntegerPipe_2')==1,'Integer path count changed')
 require(count(t('ExecutionUnitfp'),'FPFMAPipe')==1 and count(t('FPFMAPipe'),'SegmentedFMAPipe')==2,'Compute FP block count changed')
 require(count(t('ExecutionUnitfp_int'),'SharedScalarElementwiseFPFMA')==1 and count(t('VectorBackend_2'),'ExecutionUnitfp_int')==1,'Rocket shared FP count changed')
 require('assign io_fp_req_valid = io_pipe_0_valid;'in t('SharedScalarElementwiseFPFMA')and'assign io_stall = ~io_fp_req_ready;'in t('SharedScalarElementwiseFPFMA'),'Rocket elementwise admission changed')
 for core,depth in (('ShuttleFPPipe',4),('FPU',3)):
  require(all(count(t(core),'FPUFMAPipe_l%d_f%d'%(depth,width))==1 for width in (16,32,64)),'Scalar FADD pipe depth/count changed')
 widths=[]
 for name in ('SaturnShuttleUnit','SaturnRocketUnit'):
  a=port_width(t(name),'auto_atl_out_a_bits_data');d=port_width(t(name),'auto_atl_out_d_bits_data')
  require(a==d and all(port_width(t(name),f)==1 for f in ('auto_atl_out_a_valid','auto_atl_out_a_ready','auto_atl_out_d_valid','auto_atl_out_d_ready')),'ATL ready/valid width mismatch');widths.append(a)
 require(widths==[256,64],'Physical ATL geometry changed')
 return {'compute_harts':[0,1],'rocket_hart':2,'opu_clusters_per_hart':len(clusters),'opu_cells_per_cluster':16,'opu_macs_per_accepted_array_edge':len(clusters)*16,'integer_byte_slices_by_class':byte_widths,'compute_segmented_fp_blocks64':2,'rocket_shared_fp_element_requests_per_edge':1,'scalar_fadd_latency_by_hart':[4,4,3],'atl_data_bits_by_hart':[widths[0],widths[0],widths[1]]}


def shape_schedule(tm,tn,tk,fp8=False):
 require(all(type(x)is int for x in (tm,tn,tk))and 0<=tm<=32 and 0<=tn<=32 and 0<=tk<=4,'Source matrix geometry out of range')
 require(type(fp8)is bool,'FP8 selector must be Boolean')
 if not tm or not tn or not tk:return {'macs':0,'microissues':0,'earliest_issue_edges':[],'per_edge_cell_macs':[],'issue_span_edges':0,'last_result_edge':None}
 entries=[(k,r,c,min(16,tm-r*16)*min(16,tn-c*16))for k in range(tk)for r in range((tm+15)//16)for c in range((tn+15)//16)]
 last={};edges=[];work=[];edge=0
 for k,r,c,macs in entries:
  entry=(r,c)
  if fp8:edge=max(edge,last.get(entry,-3)+3)
  edges.append(edge);work.append(macs);last[entry]=edge;edge+=1
 return {'macs':sum(work),'microissues':len(entries),'earliest_issue_edges':edges,'per_edge_cell_macs':work,'issue_span_edges':edges[-1]+1,'last_result_edge':edges[-1]+(2 if fp8 else 0),'scope':'Earliest source sequencer/array schedule assuming all operands/ports ready; excludes frontend/dispatch/readout and does not establish achieved utilization.'}


def capacity(hart,family,sew=None):
 require(type(hart)is int and hart in (0,1,2),'Unknown hart')
 if family=='vme.int8' or family=='vme.fp8':
  require(hart!=2,'Hart2 has no OPU');return 256
 if family=='rvv.integer.vadd':
  require(type(sew)is int and sew in (8,16,32,64),'Unsupported VADD SEW');return (128 if hart<2 else 256)//sew
 if family=='rvv.fp.fadd' or family=='rvv.fp.fma':
  require(type(sew)is int and sew in (16,32,64),'Unsupported IEEE FP SEW');return 2*{16:4,32:2,64:1}[sew] if hart<2 else 1
 if family=='rvv.fp8.fma' or family=='rvv.bf16.fma':
  require(hart<2,'Hart2 MX arithmetic not configured');return 16 if family=='rvv.fp8.fma'else 8
 if family=='scalar.fadd':return 1
 if family=='scalar.integer.alu':return 2 if hart<2 else 1
 raise ValueError('Capacity unproved for family '+family)


def vector_work_bound(hart,family,sew,vl,lmul):
 require(type(vl)is int and vl>=0,'VL must be a nonnegative integer')
 require(type(lmul)in(int,float) and lmul in (0.125,0.25,0.5,1,2,4,8),'Unsupported LMUL')
 require(type(sew)is int and sew in (8,16,32,64),'Unsupported SEW')
 require(vl<=int(256*lmul/sew),'VL exceeds configured VLMAX')
 lanes=capacity(hart,family,sew)
 return {'element_operations':vl,'conditional_min_service_edges':(vl+lanes-1)//lanes,'elements_per_accepted_edge_upper':lanes,'setup_edges':None,'dependent_II':None,'LMUL_replication_factor':1}


def source_refs(root,modules):
 refs={}
 def add(key,path,anchors):
  raw=Path(path).read_bytes();lines=raw.decode().splitlines();matches=[]
  for anchor in anchors:
   hit=[i+1 for i,l in enumerate(lines)if anchor in l];require(hit,'Missing source expression '+key+': '+anchor)
   matches.append({'expression':anchor,'lines':hit})
  refs[key]={'path':str(path),'sha256':sha(raw),'expressions':matches}
 add('opu_scala',root/'hardware/evidence/outer-product-unit.scala',['def fp8MaccLatency = 2','val int_macc = io.macc && !is_fp8','val cells = Seq.fill(clusterYdim, clusterXdim)','val clusters = Seq.fill(yDim, xDim)','val gated_clock = clock','val en = io.row_en(i) && io.col_en(j)'])
 add('opu_sequence',root/'hardware/evidence/outer-product-sequencer.scala',['val S = subTileEdge','val d_empty = Mux','val fp8_hist_valid = RegInit','val do_mm = fire && mm && !nop','io.iss.bits.row_en(i)(j) :=','io.iss.bits.col_en(i)(j) :=','val move_latency = ((yDim+1).U - move_cluster)'])
 add('integer_scala',root/'third_party/saturn/src/main/scala/exu/int/IntegerPipe.scala',['class AdderArray(dLenB: Int)','Fill(dLenB >> eew','def insns = (baseInsns ++ wideningInsns).map(_.pipelined(1))','io.stall := false.B'])
 add('execution_scala',root/'third_party/saturn/src/main/scala/exu/ExecutionUnit.scala',['assert(PopCount(io.iss.bits.fu_sel) <= 1.U)','io.iss.ready := !Mux1H','val pipe_iss = io.iss.fire'])
 add('fp_scala',root/'third_party/saturn/src/main/scala/exu/fp/FPFMAPipe.scala',['val nTandemFMA = dLenB / 8','FType.D -> Wire(Vec(1, UInt(64.W)))','FType.S -> Wire(Vec(2, UInt(32.W)))','FType.H -> Wire(Vec(4, UInt(16.W)))','MXFType.BF16 -> Wire(Vec(4, UInt(16.W)))','MXFType.E5M3 -> Wire(Vec(8, UInt(8.W)))','fma_types.foldLeft','io.stall := false.B'])
 add('shared_fp_scala',root/'third_party/saturn/src/main/scala/exu/fp/SharedFPFMA.scala',['base_insns.map(_.elementWise)','io.stall := !io_fp_req.ready','io_fp_req.valid := io.pipe(0).valid'])
 add('vector_params',root/'hardware/evidence/saturn-parameters.scala',['def opuMxParams','def dmaParams','case object Split','case object Unified','def opuTE(vLen: Int)'])
 add('iris_config',root/'hardware/evidence/iris-config.scala',['WithRocketVectorUnit(256, 256, VectorParams.dmaParams)','WithTileFrequency(500.0)','VectorParams.opuMxParams'])
 add('shuttle_vector_config',root/'third_party/saturn/src/main/scala/shuttle/Configs.scala',['mLen=mLen.getOrElse(dLen)'])
 add('rocket_vector_config',root/'third_party/saturn/src/main/scala/rocket/Configs.scala',['mLen=mLen.getOrElse(dLen)'])
 add('clock_summary',root/'hardware/evidence/firesim-clocks.freq-summary',['clock_500.0MHz, requested: 500.0 MHz, actual: 500.0 MHz'])
 return refs


def derive(output):
 output=Path(output).resolve();require(not output.exists(),'Fresh output required');output.mkdir(parents=True);(output/'modules').mkdir();(output/'inputs').mkdir()
 associated=ROOT/'build/firesim-observability-archived-driver-v3/report.json';ar=json.loads(associated.read_text());path=next(p for p in ar['input_sha256']if p.endswith('/design/FireSim-generated.sv'));raw=Path(path).read_bytes()
 require(sha(raw)==ar['input_sha256'][path]==SV_SHA,'Associated generated SV changed')
 allmods=split_modules(raw.decode());mods={n:allmods[n]for n in MODULES};geometry=derive_geometry(mods);refs=source_refs(ROOT,mods)
 provenance=json.loads((ROOT/'hardware/manifest.json').read_text());proof_path=ROOT/'build/scalar-fadd-whole-RTL-proof-v2/report.json';proof=json.loads(proof_path.read_text())
 require(proof['checks']==2613 and proof['accepted_source_fadds']==288,'Finite scalar phase proof differs')
 for region in proof['regions']:
  require(region['source_latency']==(4 if region['hart']<2 else 3)and min(map(int,region['write_to_next_EX_gaps']))==1,'Scalar FP phase control differs')
 for name,m in mods.items():
  target=output/'modules'/(name+'.sv');target.write_text(m['text']);m['sha256']=digest(target);m['artifact']=str(target.relative_to(output));del m['text']
 inputs={str(associated):digest(associated),path:SV_SHA,str(proof_path):digest(proof_path),str(ROOT/'hardware/manifest.json'):digest(ROOT/'hardware/manifest.json')}
 inputs.update({r['path']:r['sha256']for r in refs.values()})
 extras=['third_party/shuttle/src/main/scala/exu/Core.scala','third_party/shuttle/src/main/scala/exu/FPU.scala','third_party/rocket-chip/src/main/scala/tile/FPU.scala','third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala','third_party/saturn/src/main/scala/exu/FunctionalUnit.scala','third_party/saturn/src/main/scala/backend/ExecuteSequencer.scala','third_party/saturn/src/main/scala/backend/Backend.scala','third_party/saturn/src/main/scala/backend/RegisterFile.scala','third_party/saturn/src/main/scala/backend/RegisterAccess.scala','third_party/saturn/src/main/scala/vmu/TLSplitInterface.scala','hardware/opu_cell/check.py','hardware/opu_array/check.py','build/opu-array-rtl-proof-v2-pipelined/results.json','build/opu-cell-rtl-proof-v2/results.json','build/opu-sequencer-component-v2-final/report.json']
 for rel in extras:
  p=ROOT/rel
  if p.is_file():inputs[str(p)]=digest(p)
 for key,r in refs.items():shutil.copyfile(r['path'],output/'inputs'/r['sha256'])
 inputs[str(Path(__file__).resolve())]=digest(__file__)
 # Each value below is a conditional source upper bound, never measured rate.
 records=[]
 def record(family,hart,value,unit,conditions,evidence,**extra):
  records.append(dict(family=family,hart=hart,value=value,units=unit,kind='conditional_source_capacity_upper_bound',conditions=conditions,evidence=evidence,**extra))
 common=['clocked source edge','legal supported opcode/configuration','active operands already available and defined','ready/valid accepted without competing ports or writeback conflicts','excludes setup, dependencies, masks/tails, frontend, memory and drain overhead']
 for h in (0,1,2):
  record('scalar.integer.alu',h,capacity(h,'scalar.integer.alu'),'integer_ALU_instructions/core_edge',common+['Shuttle pairing legality and data hazards may reduce two-ALU issue'],['ShuttleCore'if h<2 else'Rocket'])
  record('scalar.fadd',h,1,'scalar_adds/core_edge',common+['one scalar issue input; H/S/D physical pipes are format alternatives, not additive capacities','Rocket CP vector requests share the scalar FPU input'],['ShuttleFPPipe'if h<2 else'FPU'],physical_result_latency_edges=4 if h<2 else 3,dependent_chain_min_accept_gap_edges=5 if h<2 else 4,dependent_chain_upper_adds_per_edge=1/(5 if h<2 else 4),phase_proof_sha256=digest(proof_path))
  for sew in (8,16,32,64):record('rvv.integer.vadd',h,capacity(h,'rvv.integer.vadd',sew),'element_adds/core_edge',common+['one VADD micro-op per issue path per edge','LMUL extends iterations; it does not replicate adders','non-widening and non-reduction VADD only'],['integer_scala','execution_scala','AdderArray'if h<2 else'AdderArray_6'],sew=sew)
  for sew in (16,32,64):
   record('rvv.fp.fadd',h,capacity(h,'rvv.fp.fadd',sew),'element_adds/core_edge',common+(['one selected-format 128-bit SIMD group per edge through two explicit 64-bit segmented FMA blocks']if h<2 else['ONE elementwise scalar FP request per edge regardless of SEW/DLEN; shared scalar FPU ready required']),['fp_scala','FPFMAPipe','SegmentedFMAPipe']if h<2 else['shared_fp_scala','SharedScalarElementwiseFPFMA','FPU'],sew=sew)
   record('rvv.fp.fma',h,capacity(h,'rvv.fp.fma',sew),'element_FMAs/core_edge',common+['2 FLOPs/FMA convention; FADD is 1 FLOP, not 2','same format resources as vector FADD; capacities cannot be summed'],['fp_scala','shared_fp_scala'],sew=sew,flops_per_fma=2)
  record('vector.ATL.A.data',h,geometry['atl_data_bits_by_hart'][h]//8,'wire_data_bytes/source_edge',common+['at most one A ready&&valid beat','payload applies to Put data; Get control does not transport logical read bytes here','partial strobes and control reduce useful payload'],['SaturnShuttleUnit'if h<2 else'SaturnRocketUnit'],achieved_bytes_per_second=None)
  record('vector.ATL.D.data',h,geometry['atl_data_bits_by_hart'][h]//8,'wire_data_bytes/source_edge',common+['at most one D ready&&valid beat','AccessAckData only; acknowledgments/control do not count as full payload'],['SaturnShuttleUnit'if h<2 else'SaturnRocketUnit'],achieved_bytes_per_second=None)
  if h<2:
   for family in ('vme.int8','vme.fp8'):record(family,h,256,'cell_MACs/accepted_array_edge',common+['all16x16 cells enabled for the selected subtile','INT8 writes same physical edge; FP8 completes2 edges later','FP8 same MRF entry cannot be reissued within the two history entries; minimum issue gap3; distinct entries can pipeline','whole instruction rate must account for TM/TN shape and TK plus VRF hazards'],['opu_scala','opu_sequence','OuterProductUnit','OuterProductCluster','OuterProductCell'],arithmetic_ops_per_mac=2)
   record('vme.zero',h,256,'MRF_elements_zeroed/accepted_array_edge',common+['only active shape subtile cells; zero is not MAC/FLOP work'],['opu_scala','opu_sequence'])
   record('vme.row_move',h,4,'32bit_elements/microissue_edge',common+['source xDim4 output/input words per iteration','row readout path latency5-cluster_position plus backend capture stages; column readout is not configured'],['opu_sequence','OuterProductUnit'])
   for fmt,sew in (('fp8',8),('bf16',16)):record('rvv.'+fmt+'.fma',h,16 if sew==8 else 8,'element_FMAs/core_edge',common+['selected format only; segmented datapaths overlap with H/S/D alternatives','format/definedness not certified by a width count'],['fp_scala','SegmentedFMAPipe'],sew=sew)
 examples={name:shape_schedule(tm,tn,tk,fp8)for name,tm,tn,tk,fp8 in [('int8_full32_K4',32,32,4,False),('fp8_full32_K4',32,32,4,True),('fp8_single_subtile_K4',16,16,4,True),('fp8_partial17_K4',17,17,4,True),('empty_M',0,32,4,True)]}
 report={'schema':'iris.source_throughput_limits.v1','pass':True,'generated_source':{'path':path,'sha256':SV_SHA,'bytes':len(raw),'association':'Co-located archived image-build generated SV; full source/implementation/loaded-image attestation remains false','association_receipt':str(associated),'association_receipt_sha256':digest(associated)},'repository_pins':{k:v['commit']for k,v in provenance['repositories'].items()},'source_image_association_verified':False,'loaded_image_verified':False,'timing_accuracy_certified':False,'hardware_contacted':False,'runtime_model_changed':False,'geometry':geometry,'vector_geometry':{'VLEN':256,'DLEN_by_hart':[128,128,256],'MLEN_by_hart':[128,128,256],'matrix_tile_edge':32,'matrix_element_width':32,'LMUL':'changes group length only; not physical lane count'},'nominal_clock_conversion':{'core_hz_by_hart':[500000000]*3,'scope':'Source requested/clock-summary frequency only. Multiply per-edge ceilings by500e6 only while that clock is running; not achieved frequency/workload performance or loaded-image attestation.','evidence':'clock_summary'},'capacity_records':records,'shape_counterexamples':examples,'ordinary_vector_counterexamples':{'Rocket_FP16_VL32_LMUL2':vector_work_bound(2,'rvv.fp.fadd',16,32,2),'compute_FP16_VL32_LMUL2':vector_work_bound(0,'rvv.fp.fadd',16,32,2),'compute_e8_VL256_LMUL8':vector_work_bound(0,'rvv.integer.vadd',8,256,8)},'unknown_or_unqualified_capacities':{'achieved_DRAM_bytes_per_second':None,'NoC_end_to_end_bytes_per_second':None,'cache_miss_service_latency':None,'arbitrary_RVV_opcode_peak':None,'scalar_divide_peak':None,'combined_machine_peak':None,'FP8_or_BF16_Rocket_arithmetic':None},'non_additivity':['Different FP format ceilings share physical arithmetic','Rocket vector FP and scalar FP share input/FMA service','Unit peak sums ignore frontend/VRF/NoC/clock sharing and are not workload roofs','Intent bytes are not physical traffic; only accepted data beats qualify wire utilization'],'source_conflict_note':'Use hardware/evidence/outer-product-unit.scala be2f... actual ungated OPU source. The third_party copy daf... contains a clock-gate difference and is not silently substituted.','source_expressions':refs,'associated_modules':mods,'input_sha256':inputs,'input_count':len(inputs)}
 (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=derive(a.output);print(json.dumps({'pass':r['pass'],'records':len(r['capacity_records']),'inputs':r['input_count'],'modules':len(r['associated_modules'])}))
