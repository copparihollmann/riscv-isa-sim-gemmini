#!/usr/bin/env python3
"""Freeze source and read-only saved-RTL memory-return/VC observations."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
from packet_frontier import analyse as packet_analyse
from noc_transitions import extract as extract_transitions, validate as validate_transitions

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'build/rtl-loader-diag'
ELF_SHA='987e5e3691959520351086fdd9761ffbbbe4d50511e4af047ca70c825158280d'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def records(p,prefix):return [json.loads(x[len(prefix):]) for x in p.read_text().splitlines() if x.startswith(prefix)]
def frames(path,prefix,schema):
    names=[x['name'] for x in json.loads(schema.read_text())];out=[]
    for l in path.read_text().splitlines():
        if not l.startswith(prefix):continue
        a=l[len(prefix):].split(',')
        if len(a)!=len(names)+1:raise ValueError('Bad frame width')
        out.append(dict(tb=int(a[0]),**dict(zip(names,[int(x,16) for x in a[1:]]))))
    if any(b['tb']-a['tb']!=2 for a,b in zip(out,out[1:])):raise ValueError('Missed/duplicated source500MHz edge')
    return out

def analyse(base):
    bd=base/'build/rtl-loader-diag';src=base/'board/rtl-loader';st=bd/'vector-memory-h2-9-path.stderr'
    paths=records(st,'RTL_PATH ');packets=packet_analyse(st)
    if packets['a_transfers']!=1973 or packets['d_transfers']!=1956 or packets['oldest_pending']['tag']!=12:raise ValueError('Original frontier absent')
    # Four independent host observer binaries preserve every sampled architectural-facing transfer.
    def lines(p,prefix):return [l for l in p.read_text().splitlines() if l.startswith(prefix)]
    expected=lines(bd/'vector-memory-h2-9-packets.stderr','RTL_MEMTRACE ')
    for n in ['path','va','va2']:
        if lines(bd/f'vector-memory-h2-9-{n}.stderr','RTL_MEMTRACE ')!=expected:raise ValueError('Observer altered sampled VTL sequence')
    for n in ['va','va2']:
        if lines(bd/f'vector-memory-h2-9-{n}.stderr','RTL_NOC ')!=lines(bd/'vector-memory-h2-9-noc.stderr','RTL_NOC '):raise ValueError('Router frame observer discrepancy')
    if lines(bd/'vector-memory-h2-9-va.stderr','RTL_VA ')!=lines(bd/'vector-memory-h2-9-va2.stderr','RTL_VA '):raise ValueError('Compact observer discrepancy')
    original=packets['oldest_pending'];steps=[]
    for stage,source,address in [('CDC_A',44,0x80003940),('NIF_A',556,0x80003940),('L2_1_A',556,0x80003940)]:
        hits=[x for x in paths if x['stage']==stage and x['source']==source and x['address']==address and x['tb']>=original['tb']]
        if len(hits)!=1 or hits[0]['opcode']!=4 or hits[0]['size']!=5:raise ValueError('Request path mismatch')
        steps.append(hits[0])
    returned=[x for x in paths if x['stage']=='L2_1_D' and x['source']==556 and x['tb']>steps[-1]['tb']]
    if [x['tb'] for x in returned]!=[99133,99135,99137,99139,99141] or [x['head'] for x in returned]!=[1,0,0,0,0] or [x['tail'] for x in returned]!=[0,0,0,0,1]:raise ValueError('Incomplete/different L2 response')
    if any(x['stage']=='NIF_D' and x['source']==556 and x['tb']>=99133 for x in paths):raise ValueError('Expected missing NoC return reached adapter')
    va=frames(bd/'vector-memory-h2-9-va2.stderr','RTL_VA ',src/'va_fields.json');blocked=[x for x in va if x['tb']>=99145]
    if len(blocked)!=15428 or blocked[-1]['tb']!=129999:raise ValueError('Missing bounded VC interval')
    for x in blocked:
        if x['state']!=2 or x['valid']!=1 or x['deq_valid']!=1 or x['deq_ptr']!=3 or not x['head_word0']&1 or ((x['head_word0']>>7)&1023)!=556 or x['permitted_out_0']!=1 or any(x['permitted_out_'+str(i)] for i in range(1,6)):raise ValueError('Target packet not continuously present/waiting')
    free=[x for x in blocked if not x['out0_occupied']]
    if [x['tb'] for x in free]!=[99159,99199,99339] or any(x['select']==1 for x in free) or any(x['select']==1 and x['vc_alloc_inputs']&1 for x in blocked):raise ValueError('VC allocation observation changed')
    downstream=frames(bd/'vector-memory-h2-9-va2.stderr','RTL_VA2 ',src/'va2_fields.json')
    return {'vector_reader':packets,'request_path':steps,'l2_response':returned,'nif3_return_for_target_after_response':False,'same_vtl_events_across_four_observers':True,'same_full_router_frames_across_three_observers':True,'source_id_translation':{'load_tag':12,'inner_xbar_reader_bank':32,'tile_master_source':44,'noc_master3_prefix':512,'noc_and_l2_source':556},'router4_blocked':{'node':4,'input_from_node':3,'input_virtual_channel':0,'queue_slot':3,'head_source':556,'state_value':2,'source_state':'g_v: VC allocation wait','first_tb':blocked[0]['tb'],'last_tb':blocked[-1]['tb'],'consecutive_observed_edges':len(blocked),'head_selected_for_va_edges':sum(x['select']==1 for x in blocked),'target_grants':0,'permitted_output_port':1,'permitted_output_virtual_channels':[0],'outgoing_vc_free_edges':[{'tb':x['tb'],'selected_incoming_vc':x['select'].bit_length()-1,'allocated':bool(x['allocated_out0'])} for x in free],'outgoing_vc_occupied_after_tb':99339},'downstream_summary':downstream_analyse(downstream)}

def downstream_analyse(rows):
    # Reconstruct the exact source inner-VA choice without reading the observed choice.
    for x in rows:
        vals=sum(bool(x[str(i)+'_valid'])<<i for i in range(6));eligible=vals&~x['input_mask'];choice=(eligible&-eligible) if eligible else(vals&-vals)
        if x['select']!=choice:raise ValueError('Source inner-VA choice mismatches RTL')
    stable=[x for x in rows if x['tb']>=99367]
    heads={0:564,3:574,4:573,5:575}
    for x in stable:
        for i,source in heads.items():
            if x[str(i)+'_state']!=2 or not x[str(i)+'_valid'] or not x[str(i)+'_head_word0']&1 or ((x[str(i)+'_head_word0']>>7)&1023)!=source:raise ValueError('Downstream blocked header changed')
    free=[x for x in stable if x['egress_empty']]
    if len(free)!=1532 or free[0]['tb']!=99379 or free[-1]['tb']!=129999 or any(b['tb']-a['tb']!=20 for a,b in zip(free,free[1:])):raise ValueError('Egress period changed')
    if any(x['select'] not in [2,4] or x['vc_alloc_inputs']!=1 or not x['allocated_egress'] for x in free):raise ValueError('Phase-locked grants changed')
    return {'node':5,'input_from_node':4,'local_egress_port':2,'local_egress_nif':3,'first_tb':rows[0]['tb'],'last_tb':rows[-1]['tb'],'edges':len(rows),'source_rr_reconstruction_edges':len(rows),'stable_blocked_heads_from_tb':99367,'blocked_virtual_channel_headers':{str(i):v for i,v in heads.items()},'stable_egress_free_first_tb':free[0]['tb'],'stable_egress_free_last_tb':free[-1]['tb'],'stable_egress_free_period_tb':20,'stable_egress_free_period_uncore_cycles':10,'stable_free_slots':len(free),'stable_free_slot_grants':{'incoming_vc1':sum(x['select']==2 for x in free),'incoming_vc2':sum(x['select']==4 for x in free),'other':0},'bounded_starvation_observed':True,'per_vc':{str(i):{'va_wait_edges':sum(x[str(i)+'_state']==2 for x in stable),'selected_edges':sum(x['select']==1<<i for x in stable),'selected_and_egress_free_edges':sum(x['select']==1<<i and x['egress_empty'] for x in stable),'grants':sum(x['select']==1<<i and x['vc_alloc_inputs']&1 for x in stable)} for i in range(6)}}

def decode_signature(path,checks):
    import struct
    raw=b''
    for line in path.read_text().splitlines():
        if len(line) not in [16,32] or not re.fullmatch('[0-9a-f]+',line):raise ValueError('Bad signature format')
        raw+=int(line,16).to_bytes(len(line)//2,'little')
    if len(raw)!=224:raise ValueError('Wrong signature length')
    v=struct.unpack('<28Q',raw)
    if list(v[:4])!=[0x4952495350524f42,1,4,0]:raise ValueError('Wrong/failed memory mailbox')
    rows=[dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],v[4+8*h:12+8*h]),hart=h) for h in range(3)]
    if any(x['done']!=1 or x['checks']!=checks[x['hart']] or x['actual']!=x['expected'] for x in rows):raise ValueError('Failed/incomplete positive memory control')
    return rows


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-memory-return-path-v1-final');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        j=json.loads((out/'report.json').read_text())
        for n,d in j['artifact_sha256'].items():
            if sha(out/n)!=d:raise ValueError('Changed frozen memory-path artifact: '+n)
        if analyse(out)!=j['observation']:raise ValueError('Memory path analysis changed')
        tr=json.loads((out/j['arbiter_transition_vectors']['path']).read_text());validate_transitions(tr)
        if extract_transitions(out)['vectors']!=tr['vectors']:raise ValueError('Frozen transition extraction changed')
        for name,c in j['finite_controls'].items():
            if decode_signature(out/'build/rtl-loader-diag'/(name+'.signature'),[x['checks'] for x in c['harts']])!=c['harts']:raise ValueError('Finite control changed')
        print(json.dumps({'pass':True,'bounded_blockage_identified':True,'root_cause_complete':False,'hardware_contacted':False}));return
    if out.exists():raise ValueError('Refuse to overwrite memory path capsule')
    observation=analyse(ROOT);transitions=json.loads((D/'noc-arbiter-transitions.json').read_text());validate_transitions(transitions)
    if extract_transitions(ROOT)['vectors']!=transitions['vectors']:raise ValueError('Transition extraction changed')
    paths=[Path(__file__),ROOT/'board/rtl-loader/packet_frontier.py',ROOT/'build/rtl-memory-packets-v1/report.json',ROOT/'build/rtl-memory-frontier-v1/report.json',ROOT/'build/rtl-verilator/manifest.json',ROOT/'hardware/manifest.json']
    for n in ['path','noc','va','va2']:
        run=D/f'vector-memory-h2-9-{n}.json';j=json.loads(run.read_text())
        if j['exit_status']!=1 or j['timed_out'] or j['elf_sha256']!=ELF_SHA:raise ValueError('Wrong/incomplete negative run')
        for field,path in [('binary_sha256',Path(j['argv'][0])),('elf_sha256',Path(j['argv'][-1])),('stdout_sha256',D/f'vector-memory-h2-9-{n}.stdout'),('stderr_sha256',D/f'vector-memory-h2-9-{n}.stderr'),('build_receipt_sha256',D/f'{n}-diag-build.json')]:
            if sha(path)!=j[field]:raise ValueError('Wrong run artifact identity')
            paths.append(path)
        paths.append(run);b=json.loads((D/f'{n}-diag-build.json').read_text())
        for path,digest in b['input_sha256'].items():
            if sha(path)!=digest:raise ValueError('Changed observer input')
            paths.append(Path(path))
        for path in b['link_argv']:
            if path.endswith(('.o','.a')):paths.append(Path(path) if Path(path).is_absolute() else ROOT/'build/rtl-verilator/model'/path)
    for ext in ['json','stderr','stdout']:paths.append(D/f'vector-memory-h2-9-packets.{ext}')
    for n in ['vector-memory-counted.c','start-loader-bss.S','SimTSI.cc']:paths.append(ROOT/'board/rtl-loader'/n)
    # Generated HDL is exact to the saved standalone FIR, distinct from FireSim's source FIR.
    paths+=list((ROOT/'build/rtl-verilator/gen-collateral').glob('*.sv'))
    paths.append(Path('/scratch/eygao/iris-cy/sims/vcs/generated-src/chipyard.harness.TestHarness.IrisConfig/chipyard.harness.TestHarness.IrisConfig.fir'))
    paths.append(ROOT/'board/rtl-loader/constellation-source.json')
    for n,digest in json.loads((D/'deep-state-build.json').read_text())['input_sha256'].items():
        if sha(n)!=digest:raise ValueError('Changed underlying native RTL input')
        paths.append(Path(n))
    for path,digest in json.loads((D/'loader-build.json').read_text())['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('Changed shared RTL host ABI input')
        paths.append(Path(path))
    controls={}
    for name,checks in [('vector-memory-h2-8-path',[0,0,64]),('vector-memory-h2-9-backoff',[0,0,72]),('vector-memory-h2-9-load-fences',[0,0,72])]:
        j=json.loads((D/(name+'.json')).read_text())
        if j['exit_status'] or j['timed_out']:raise ValueError('Failed finite control')
        for ext in ['json','signature','stdout','stderr']:
            path=D/(name+'.'+ext)
            if ext in ['stdout','stderr'] and sha(path)!=j[ext+'_sha256']:raise ValueError('Finite control transcript mismatch')
            paths.append(path)
        for key,path in [('elf_sha256',Path(j['argv'][-1])),('binary_sha256',Path(j['argv'][0]))]:
            if sha(path)!=j[key]:raise ValueError('Finite control identity mismatch')
            paths.append(path)
        controls[name]={'harts':decode_signature(D/(name+'.signature'),checks),'binary_sha256':j['binary_sha256'],'elf_sha256':j['elf_sha256'],'host_env_overrides':j.get('env_overrides',{}),'scope':'Finite counterfactual observation, not a general fix or calibration'}
    for path in [ROOT/'board/rtl-loader/noc_transitions.py',D/'noc-arbiter-transitions.json',ROOT/'board/rtl-loader/MEMORY_RETURN_PATH.md',D/'poll-backoff-build.json',D/'load-fences-build.json',ROOT/'board/rtl-loader/poll_SimTSI.cc',ROOT/'board/rtl-loader/vector-memory-h2-9-load-fences.c']:
        paths.append(path)
    for n in ['InputUnit.scala','OutputUnit.scala','EgressUnit.scala','vcalloc/SingleVCAllocator.scala','vcalloc/ISLIP.scala']:
        paths.append(Path('/scratch/eygao/iris-cy/generators/constellation/src/main/scala/router')/n)
    source_facts=[]
    cited=[('build/rtl-verilator/gen-collateral/TLXbar_i2_o1_a35d256s6k4z4u.sv','assign auto_anon_out_a_bits_source =','Reader input0 gains bit5'),('build/rtl-verilator/gen-collateral/TLXbar_MasterXbar_RocketTile_i3_o1_a35d64s7k4z4c.sv','assign auto_anon_out_a_bits_source =','Vector master input2 preserves low6bits'),('build/rtl-verilator/gen-collateral/TLAToNoC_3.sv',"io_protocol_bits_source | 10'h200",'NoC master3 adds0x200'),('build/rtl-verilator/gen-collateral/TLDToNoC_2.sv','assign io_flit_bits_egress_id =','Source556 routes to NIF3'),('build/rtl-verilator/gen-collateral/InputUnit_10.sv','else if (vcalloc_vals_0 |','Internal selection mask advances on valid attempt'),('build/rtl-verilator/gen-collateral/RotatingSingleVCAllocator_5.sv','wire        in_arb_reqs_0_2_0','Selected local-egress request filtered by occupied'),('build/rtl-verilator/gen-collateral/EgressUnit_21.sv','assign io_channel_status_0_occupied','Egress reservation gating')]
    for name,needle,fact in cited:
        path=ROOT/name;hits=[i for i,line in enumerate(path.read_text().splitlines(),1) if needle in line]
        if len(hits)!=1:raise ValueError('Source citation ambiguous: '+name)
        source_facts.append({'path':name,'line':hits[0],'sha256':sha(path),'fact':fact})
    out.mkdir(parents=True);origins={}
    for path in sorted(set(paths)):
        path=path.resolve()
        try:rel=path.relative_to(ROOT)
        except ValueError:rel=Path('external')/path.relative_to('/')
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst);origins[str(rel)]={'path':str(path),'sha256':sha(path)}
    j={'schema':'iris.saved_rtl_memory_return_path.v1','observation':observation,'finite_controls':controls,'arbiter_transition_vectors':{'path':'build/rtl-loader-diag/noc-arbiter-transitions.json','transitions':len(transitions['vectors']),'stages_per_transition':3,'mutation_rejections':transitions['mutation_rejections']},'source_facts':source_facts,'source_constellation_commit':'c1b42cd0c7c7d6e4fc1ed9bf1f86fbd3b31ac510','source_constellation_tracked_modified':False,'bounded_allocation_starvation_mechanism_identified':True,'bounded_blockage_identified':True,'root_cause_complete':False,'speculative_rtl_fix_applied':False,'interpretation':'The oldest accepted reader load reaches L2, which emits its complete response into the NoC. The intact response queues at router4/input0/VC0, waiting for downstreamVC0. At router5 the shared local egress is free every10 uncorecycles, always when another incomingVC1or2 is selected. Four other VA requests remain queued and never granted overthe explicitinterval; their attempts fall onoccupiedcycles. Source InputUnit attemptsadvance its mask evenwithoutready, while SingleVCAllocator filters occupied outputs, producing the observed phase-locked bounded starvation. No proof of infinite/globaldeadlock, deployedFPGAfault or timingcalibration is implied.','source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','source_design':'chipyard.harness.TestHarness.IrisConfig','source_memory_lowering':'native FIRRTL memories','observer':'Old stable combinational values, event accepted only on actual source500MHz risingedge; no RTL state writes. Raw500MHz frames preserve per-cycle activity.','four_state_definedness_available':False,'unknown_reset_behavior_proven_irrelevant':False,'matches_ethan_firesim_image':False,'full_rtl_certified':False,'timing_calibrated':False,'hardware_contacted':False,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    (out/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(out/'report.json')

if __name__=='__main__':main()
