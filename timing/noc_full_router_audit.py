#!/usr/bin/env python3
"""Source citations, physical coverage, and a second reset seed for node5."""
import argparse,collections,hashlib,json,subprocess
from pathlib import Path
import noc_full_router_check as check
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/noc-full-router-audit-v2');a=p.parse_args();o=a.output.resolve()
 if o.exists():raise ValueError('Refuse to overwrite audit')
 o.mkdir();b=R/'build/noc-full-router-v2';src=b/'rtl'
 def cite(file,needle):
  path=src/file if (src/file).exists() else R/file;lines=path.read_text().splitlines();matches=[n+1 for n,x in enumerate(lines) if needle in x];assert matches,(file,needle)
  return {'path':str(path.relative_to(R)),'sha256':sha(path),'line':matches[0],'match':needle}
 facts=[]
 def fact(name,value,file,needle):facts.append({'fact':name,'value':value,'source':cite(file,needle)})
 fact('router_inputs',['network0 from4','network1 from6','localA global-ingress6','localC global-ingress7'],'Router_5.sv','InputUnit_10 input_unit_0_from_4')
 fact('second_network_input','InputUnit_11','Router_5.sv','InputUnit_11 input_unit_1_from_6')
 fact('local_A_input','IngressUnit_15','Router_5.sv','IngressUnit_15 ingress_unit_2_from_6')
 fact('local_C_input','IngressUnit_16','Router_5.sv','IngressUnit_16 ingress_unit_3_from_7')
 fact('outputs',['network0 to4','network1 to6','local NIF global-egress3'],'Router_5.sv','OutputUnit_1 output_unit_0_to_4')
 fact('input_VCs_per_network_port',6,'InputUnit_10.sv','reg  [2:0]  states_5_g')
 fact('input_FIFO_words_and_width',[5,75],'ram_5x75.sv','reg [74:0] Memory[0:4]')
 fact('network0_reset_credits_per_VC',5,'OutputUnit_1.sv',"states_0_c <= 3'h5")
 fact('network_output_credit_updates','credit_return minus own emitted flit','OutputUnit_1.sv','states_0_c <= states_0_c +')
 fact('VC_reservation_updates','allocation OR occupied-and-not-vc_free','OutputUnit_1.sv','states_0_occupied <= io_allocs_0_alloc')
 fact('network1_VC0','untraversable/source-elided; not fabricated as occupied storage','OutputUnit.sv','output        io_channel_status_1_occupied')
 fact('network_outputs','combinational switch transfer with credit/reservation state, no added output FIFO','OutputUnit.sv','assign io_out_flit_0_valid = io_in_0_valid')
 fact('local_egress_FIFO',2,'EgressUnit_21.sv','Queue2_EgressFlit q')
 fact('local_credit_available','local queue count equals zero','EgressUnit_21.sv',"assign io_credit_available_0 = _q_io_count == 2'h0")
 for instance,depth,mod in [('route_buffer',2,'Queue2_Flit'),('route_q',2,'Queue2_RouteComputerResp_15'),('vcalloc_buffer',2,'Queue2_Flit'),('vcalloc_q',1,'Queue1_VCAllocResp_15')]:
  fact('each_local_ingress_'+instance,depth,'IngressUnit_15.sv',mod+' '+instance)
 fact('full_router_route_logic','saved exact elaborated minterms, not a fitted route/latency','Router_5.sv','RouteComputer_5 route_computer')
 fact('full_router_VA','complete four-input/thirteen-output rotating single-VC allocator','Router_5.sv','RotatingSingleVCAllocator_5 vc_allocator')
 fact('saved_uncore_clock_period_ns',2,'build/rtl-verilator/gen-collateral/TestHarness.sv','.PERIOD(2.000000e+00)')
 coverage=[];second_seed=[]
 for case in ['original9','control8','fenced9','peer']:
  schema,rows=check.read_frames(case);names=[x['name'] for x in schema['fields'][44:]];domain={};valid={};accepted={}
  for k in range(2):
   prefix='i_net'+str(k)+'_';flows=collections.Counter(tuple(x[prefix+n] for n in ['vc','vnet','ingress_node','ingress_id','egress_node','egress_id']) for x in rows if not x['i_reset'] and x[prefix+'valid'] and x[prefix+'head']);domain[prefix]={'unique_header_flows':len(flows),'header_flow_counts':{'/'.join(map(str,key)):n for key,n in flows.items()}}
   valid['local'+str(k)]=sum(x['i_local'+str(k)+'_valid'] for x in rows if not x['i_reset']);accepted['local'+str(k)]=sum(x['i_local'+str(k)+'_valid'] and x['o_ingress_ready'+str(k)] for x in rows if not x['i_reset'])
  coverage.append({'case':case,'network_header_flows':domain,'local_ingress_valid_cycles':valid,'local_ingress_accepted_flits':accepted,'local_egress_valid_cycles':sum(x['o_local_valid'] for x in rows if not x['i_reset']),'local_egress_accepted_flits':sum(x['o_local_valid'] and x['i_local_ready'] for x in rows if not x['i_reset'])})
  if case not in ['original9','peer']:continue
  argv=[str(b/'noc-full-router'),'--seed','17'];body=(R/'build/noc-full-router-accept-v2'/(case+'.input')).read_text();q=subprocess.run(argv,input=body,text=True,capture_output=True,timeout=30);(o/(case+'-seed17.stdout')).write_text(q.stdout);(o/(case+'-seed17.stderr')).write_text(q.stderr);q.check_returncode();actual=[[int(v) for v in line.split()] for line in q.stdout.splitlines()];result=check.compare(actual,rows,names);result.update(case=case,seed=17,pass_result=True,argv=argv,stdout_sha256=sha(o/(case+'-seed17.stdout')));second_seed.append(result)
 contract=json.loads((R/'timing/noc_full_router_contract.json').read_text());report={'schema':'iris.full_router_source_audit.v2','facts':facts,'source_contract':contract,'coverage':coverage,'second_reset_seed':second_seed,'constellation_source_pin':'c1b42cd0c7c7d6e4fc1ed9bf1f86fbd3b31ac510','constellation_pin_associates_saved_elaboration':False,'source_FIR_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','scope':'Exact source-generated configured node5 subtree; external network endpoint behavior remains physical inputs','unknowns':['No full NoC/CDC/NIF/cache integration yet','Two-state Verilator native FIRRTL-memory lowering and explicit readonly preload harness, not deployed FPGA','Decoder annotated don\'t-care default refused outside declared legal flows','Inactive flit fields and reset outputs are not claimed defined','All configured machines instantiated, but finite capture does not exhaust every legal route/state'],'idle_skipping':False,'internal_state_or_eligibility_reinjected':False,'hardware_contacted':False}
 (o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'source_facts':len(facts),'second_seed_cases':len(second_seed),'report_sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
