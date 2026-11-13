#!/usr/bin/env python3
"""Associated-source clock/probe/busy audit. No model or hardware mutations."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SV=Path('/scratch/eygao/iris-cy/sims/firesim/deploy/results-build/2026-11-03--03-10-49-corigine_mimicturbo_gt_firesim_iris_tethered_bringup_nocflush/cl_corigine_mimicturbo_gt-firesim-FireSim-IrisFiresimNOCflushCombinedConfig-BaseCorigineMimicTurboGTConfig/design/FireSim-generated.sv')
EXPECTED='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
GUARDS={
 'FixedClockBroadcast_7':['assign auto_anon_out_0_clock = auto_anon_in_clock;','assign auto_anon_out_2_clock = auto_anon_in_clock;','assign auto_anon_out_3_clock = auto_anon_in_clock;'],
 'TilePRCIDomain':['assign element_reset_domain_shuttle_tile_clock = auto_tap_clock_in_clock;'],
 'ShuttleTile':['assign dcache_clock = clock;','assign core_clock = clock;','assign vector_unit_clock = clock;'],
 'ShuttleCore':['assign csr_io_ungated_clock = clock;','assign io_trace_core_ingress_time = csr_io_time;'],
 'ShuttleDCache':['assign auto_out_b_ready = prober_io_req_ready & _prober_io_req_valid_T;','assign prober_io_req_valid = auto_out_b_valid & ~lrsc_valid;','assign prober_io_mshr_rdy = mshrs_io_probe_rdy;'],
 'ProbeUnit':['assign io_req_ready = state == 4\'h0;','assign io_rep_valid = state == 4\'h5;','assign io_wb_req_valid = state == 4\'h6;'],
 'CSRFile':['assign io_csr_stall = reg_wfi | io_status_cease;','assign io_time = {large_1,small_1};'],
 'RocketTile':['assign vector_unit_clock = clock;','assign core_clock = clock;','assign fpuOpt_clock = clock;'],
 'Rocket':['assign csr_io_ungated_clock = clock;','assign csr_clock = clock;'],
 'SaturnShuttleUnit':['assign tl_if_clock = clock;','assign vu_clock = clock;','assign vmu_clock = clock;','assign io_backend_busy = vu_io_busy | tl_if_io_mem_busy | vmu_io_busy;'],
 'SaturnRocketUnit':['assign tl_if_clock = clock;','assign vu_clock = clock;','assign vmu_clock = clock;','assign hella_if_clock = clock;','assign io_core_backend_busy = vu_io_busy | tl_if_io_mem_busy | hella_if_io_mem_busy | vmu_io_busy;'],
 'DigitalTop':['assign tile_prci_domain_1_auto_tap_clock_in_clock = sbus_fixedClockNode_auto_anon_out_3_clock;','assign sbus_system_bus_noc_be_noc_nif_master_be_2_clock = sbus_fixedClockNode_auto_anon_out_0_clock;','assign sbus_system_bus_noc_acd_noc_nif_master_acd_2_clock = sbus_fixedClockNode_auto_anon_out_0_clock;']}
def compact(t):return re.sub(r'\s+',' ',re.sub(r'//[^\n]*','',t))
def guard(name,text):
 s=compact(text)
 for literal in GUARDS[name]:
  if literal not in s:raise ValueError('Changed source witness '+name+':'+literal)
def main(out):
 out.mkdir(parents=True,exist_ok=False);snaps=out/'source';snaps.mkdir()
 if sha(SV)!=EXPECTED:raise ValueError('Associated generated SV changed')
 alltext=SV.read_text();mods={m.group(1):m.group()+'\n'for m in re.finditer(r'^module\s+(\w+)[\s\S]*?^endmodule',alltext,re.M)};witness={}
 for name in GUARDS:
  guard(name,mods[name]);(snaps/(name+'.sv')).write_text(mods[name]);witness[name]={'sha256':sha(snaps/(name+'.sv')),'exact_expressions':GUARDS[name]}
 reach={}
 for root in ['SaturnShuttleUnit','SaturnRocketUnit','Rocket','FPU']:
  if root not in mods:continue
  seen={};todo=[root]
  while todo:
   n=todo.pop()
   if n in seen:continue
   kids=sorted(set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',mods[n],re.M))&mods.keys());seen[n]=kids;todo.extend(x for x in kids if x not in seen)
  gates=[n for n in seen if any(x in n.lower()for x in ['clockgate','clock_gate','eicg'])];reach[root]={'unique_modules':len(seen),'clock_gate_modules':gates,'children':seen}
  if root in ['SaturnShuttleUnit','SaturnRocketUnit','Rocket']and gates:raise ValueError('Unexpected inner clock gate '+root)
 (out/'reachable-clock-modules.json').write_text(json.dumps(reach,indent=2)+'\n')
 mutations=[]
 for name,old,new in [('ShuttleTile','assign dcache_clock = clock;','assign dcache_clock = clock & !cpu_wfi;'),('RocketTile','assign vector_unit_clock = clock;','assign vector_unit_clock = core_gated_clock;'),('SaturnRocketUnit','| tl_if_io_mem_busy |','| 1\'h0 |'),('ShuttleDCache','auto_out_b_valid & ~lrsc_valid','auto_out_b_valid & ~lrsc_valid & !cpu_wfi'),('CSRFile','reg_wfi | io_status_cease','io_status_cease')]:
  assert old in mods[name]
  try:guard(name,mods[name].replace(old,new,1))
  except ValueError:mutations.append({'module':name,'changed_expression':old,'rejected':True})
  else:raise ValueError('Source mutation admitted '+name)
 source_files=[Path('/scratch/eygao/iris-cy/generators/shuttle/src/main/scala/'+p)for p in ['common/Tile.scala','exu/Core.scala','dmem/DCache.scala','dmem/MSHR.scala','dmem/MSHRs.scala']]
 source_files +=[Path('/scratch/eygao/iris-cy/generators/rocket-chip/src/main/scala/'+p)for p in ['rocket/CSR.scala','rocket/RocketCore.scala','rocket/NBDcache.scala','tile/RocketTile.scala','tile/TilePRCIDomain.scala','subsystem/HierarchicalElementPRCIDomain.scala']]
 source_files +=[Path('/scratch/eygao/iris-cy/generators/saturn/src/main/scala/'+p)for p in ['rocket/Integration.scala','shuttle/Integration.scala','mem/TLInterface.scala','rocket/HellaInterface.scala','mem/Mem.scala','backend/Backend.scala','common/ReorderBuffer.scala']]
 dynamic=[ROOT/'build/WFI-idle-dirty-cache-component-v1/run.json',ROOT/'build/WFI-idle-dirty-cache-component-v1/check.stdout',ROOT/'build/Shuttle-WFI-source-component-v3/run.json',ROOT/'build/Shuttle-WFI-source-component-v3/check.stdout']
 for p in dynamic:
  if p.name=='run.json'and json.loads(p.read_text())['exit_status']!=0:raise ValueError('Dynamic proof failed')
 scopes={'clock':'associatedSV showscontinuousSBUS-derivedShuttlecache/tile/NoCclocks; noWFIgate; RocketcoreandSaturnunitdirecttileclock; noClockGatemodulereachablewithinSaturnroots','WFI_counter':'actualsavedShuttleCore h0/1×seeds1/17; executesfullydefinedmie8/WFI;96externalclockedges passwithmcycleconstant8;MSIP160→marker164 andmcycle67at220; trace_timealiasesCSRreg_cycle','probe':'actualfrozenall3memorySDK; CPUexcluded; scalarrequestvalidhart1held0; dirtyownerB4677→8CProbeAckDatabeats4685..4692;peerreceivesdirtyvaluewithoutouterreread; nointernalstateorreadyinputs','probe_gates':'BacceptrequiresProbeUnitidleand!LRSCvalid;MSHRsame-indexbefore-refill/meta-hazardcanretry;dirtyreplywaitsWBslotandactualCready;fairdownstreamserviceisassumption','memory_busy':'TLreader/writerbusytracksAaccept−Dresponse,notjustissue;VMUstoreSIQlastdequeuewaitsactualstoreROBmatchingack;RocketHellaIFtracksenq−response too','busy_limit':'ORofVU/TL/Hella/VMUdoesNOTcertifycompleteOPU/FP8/readouttailquiescence;noidleclockskippermission','counter_limit':'per-hartmcycleisnotglobalelapsedtimeacrossWFI;CLINTglobalcounterisoutsideCoretest;Rocketcounterdynamicproofnotperformedhere','fixture_knownness':'cachepositiveuses64actualacceptedwarmuploadeachShuttletoinitializeRPQslots;strictunknown-replayguardretained;notproofnormalbootinitializesallslots','unreset_counterexample':'firstCoretestCSRRSI8preservedunresetMIEandpendinginterruptbits,preventingWFI;v3usesactualCSRRWI8,nointernalinitialization;notav6causeclaim'}
 inputs=[Path(__file__).resolve(),SV,ROOT/'hardware/evidence/iris-config.scala',ROOT/'hardware/manifest.json',ROOT/'hardware/evidence/outer-product-unit.scala',ROOT/'timing/wfi_cache_probe_source_check.cpp',ROOT/'pipeline/test_Shuttle_WFI_source_clock.cpp',ROOT/'build/shuttle-memory-system-component-v1/report.json',ROOT/'build/shuttle-memory-system-component-v1-verify/report.json',ROOT/'build/shuttle-memory-system-check-final-v1/report.json',ROOT/'build/shuttle-lsu-phase-source-v1/build.json',*dynamic,*source_files]
 report={'schema':'iris.WFI_cache_vector_clock_coherence_source_audit.v1','pass':True,'associated_generated_SV_sha256':EXPECTED,'source_witnesses':witness,'source_mutations_rejected':mutations,'clock_roots':{k:{x:y for x,y in v.items()if x!='children'}for k,v in reach.items()},'scope_and_findings':scopes,'cache_component_checks':82608,'WFI_core_checks':1552,'hardware_contacted':False,'native_policy_or_callbacks_changed':False,'protected_timing_labels_consumed':False,'watch_causality_established':False,'observed_hardware_stall_cause_identified':False,'full_source_loaded_image_attestation':False,'whole_CPU_cache_joint_dynamic_proof':False,'remaining_hypotheses':['actualMSHR/probe/backpressurestateunobserved','IRQ/FPU/vectorcontextorderingunderindependentaudit','externalNoC/L2/hosttokenforwardprogressnotuniversallyproven'],'input_sha256':{str(p):sha(p)for p in inputs}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);main(p.parse_args().output.resolve())
