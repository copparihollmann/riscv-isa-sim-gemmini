#!/usr/bin/env python3
"""Build and certify an isolated source-derived native NoC arbiter component."""
import argparse,copy,hashlib,json,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
EXPECTED_NAMES=['selected_vc','input_unit_mask_next','input_unit_grants','single_vc_input_mask_next','islip_output_selection','output_vc_grants','islip_output_mask_next']
STATE_NAMES=['input_unit_mask','single_vc_input_mask','islip_output_mask']
INPUT_NAMES=['waiting_vcs','incoming_route_fire','incoming_route_vc','eligible_input_units','selected_eligible_output_vcs']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def jread(p):return json.loads(Path(p).read_text())
def seed(state):return 'seed '+' '.join(str(state[n]) for n in STATE_NAMES)+'\n'
def step(v):return 'step '+str(v['tb'])+' '+' '.join(str(int(v['input'][n])) for n in INPUT_NAMES)+'\n'
def payload(vectors,continuous):return (seed(vectors[0]['state'])+''.join(step(v) for v in vectors)) if continuous else ''.join(seed(v['state'])+step(v) for v in vectors)
def expected(v):
    e=v['expected'];return [v['tb']]+[e[n] for n in EXPECTED_NAMES]+[int(e['selected_vc']!=0 and bool(e['input_unit_grants']&1))]
def compare(rows,vectors):
    if len(rows)!=len(vectors):raise ValueError('Native row count mismatch')
    for row,v in zip(rows,vectors):
        if row!=expected(v):raise ValueError('Native NoC mismatch atTB'+str(v['tb']))

def parse_frames(path,schema,prefix='RTL_ARB '):
    names=[x['name'] for x in jread(schema)];rows=[]
    for line in path.read_text().splitlines():
        if not line.startswith(prefix):continue
        values=line[len(prefix):].split(',')
        if len(values)!=len(names)+1:raise ValueError('Missing arbiter boundary field')
        rows.append(dict(tb=int(values[0]),**dict(zip(names,[int(x,16) for x in values[1:]]))))
    if len(rows)!=15500 or rows[0]['tb']!=99001 or rows[-1]['tb']!=129999 or any(b['tb']!=a['tb']+2 for a,b in zip(rows,rows[1:])):raise ValueError('Nonconsecutive or incomplete live arbitration boundary')
    return rows

def frame_vectors(frames):
    vectors=[]
    for a,b in zip(frames,frames[1:]):
        e={n:a[n] for n in ['selected_vc','input_unit_grants','islip_output_selection','output_vc_grants']}
        e.update({n+'_next':b[n] for n in STATE_NAMES})
        vectors.append({'tb':a['tb'],'state':{n:a[n] for n in STATE_NAMES},'input':{n:a[n] for n in INPUT_NAMES},'expected':e})
    return vectors

def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,default=ROOT/'build/noc-component-v1-final');parser.add_argument('--verify',action='store_true');a=parser.parse_args();out=a.output.resolve()
    if a.verify:
        report=jread(out/'report.json')
        for name,digest in report['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('Frozen component input/output changed: '+name)
        for ex in report['executions']:
            q=subprocess.run([str(out/'noc-arbiter')]+ex['argv'][1:],input=(out/(ex['name']+'.input')).read_text(),text=True,capture_output=True,timeout=15)
            if q.returncode!=ex['exit_status'] or hashlib.sha256(q.stdout.encode()).hexdigest()!=ex['stdout_sha256'] or hashlib.sha256(q.stderr.encode()).hexdigest()!=ex['stderr_sha256']:raise ValueError('Frozen native replay changed: '+ex['name'])
        print(json.dumps({'pass':True,'source_capsule_sha256':report['source_capsule_sha256'],'continuous_cycles':report['long_continuous']['cycles'],'whole_noc_certified':False}));return
    if out.exists():raise ValueError('Refuse to overwrite component evidence')
    profile=jread(ROOT/'timing/noc_sources.json')
    if sha(CAP/'report.json')!=profile['source_capsule_sha256']:raise ValueError('Wrong source capsule')
    for citation in list(profile['parameter_sources'].values())+profile['semantic_sources']:
        if sha(ROOT/citation['path'])!=citation['sha256']:raise ValueError('Source profile citation changed')
    fixture=jread(ROOT/profile['fixture']);p=profile['parameters']
    if [p['input_virtual_channels'],p['router_input_units'],p['output_virtual_channels'],p['local_input_unit']]!=[fixture['input_virtual_channels'],fixture['router_input_units'],sum(map(len,fixture['flattened_output_vcs'].values())),fixture['input_unit']]:raise ValueError('Source parameter/profile mismatch')
    out.mkdir(parents=True);compiler=Path(shutil.which('c++')).resolve();binary=out/'noc-arbiter';command=[str(compiler),'-O2','-std=c++20','-Wall','-Wextra','-Werror',str(ROOT/'timing/noc_arbiter.cpp'),str(ROOT/'timing/noc_driver.cpp'),'-o',str(binary)];subprocess.run(command,check=True)
    argv=[str(binary),'--input-vcs',str(p['input_virtual_channels']),'--router-inputs',str(p['router_input_units']),'--output-vcs',str(p['output_virtual_channels']),'--local-input',str(p['local_input_unit'])]
    executions=[]
    def run(label,body,expect_status=0,args=None):
        cmd=argv if args is None else args
        started=time.monotonic();q=subprocess.run(cmd,input=body,text=True,capture_output=True,timeout=15);seconds=time.monotonic()-started
        (out/(label+'.input')).write_text(body);(out/(label+'.stdout')).write_text(q.stdout);(out/(label+'.stderr')).write_text(q.stderr)
        executions.append({'name':label,'argv':cmd,'exit_status':q.returncode,'host_seconds':seconds,'input_sha256':sha(out/(label+'.input')),'stdout_sha256':sha(out/(label+'.stdout')),'stderr_sha256':sha(out/(label+'.stderr'))})
        if q.returncode!=expect_status:raise ValueError('Unexpected native exit in '+label+': '+q.stderr)
        return [[int(x) for x in line.split()] for line in q.stdout.splitlines()]
    vectors=fixture['vectors'];rows=run('rtl99-rows',payload(vectors,False));compare(rows,vectors)
    body=payload(vectors,True);continuous=run('rtl99-continuous',body);compare(continuous,vectors)
    poisoned=copy.deepcopy(vectors)
    for v in poisoned[1:]:v['state']={k:0 for k in STATE_NAMES}
    if payload(poisoned,True)!=body:raise ValueError('Continuous protocol reused observed state')
    mutation_rejections=[]
    for key in ['selected_vc','input_unit_mask_next','input_unit_grants','output_vc_grants','islip_output_mask_next']:
        bad=copy.deepcopy(vectors);bad[0]['expected'][key]^=1
        try:compare(continuous,bad)
        except ValueError:mutation_rejections.append(key)
        else:raise ValueError('Corrupt expected transition admitted')
    source_run=ROOT/'build/noc-rtl-state-v1';r=jread(source_run/'run.json');b=jread(source_run/'observer-build.json')
    if r['exit_status']!=1 or r['timed_out'] or r['elf_sha256']!='987e5e3691959520351086fdd9761ffbbbe4d50511e4af047ca70c825158280d':raise ValueError('Wrong bounded RTL execution')
    for key,path in [('binary_sha256',Path(r['argv'][0])),('elf_sha256',Path(r['argv'][-1])),('stdout_sha256',source_run/'run.stdout'),('stderr_sha256',source_run/'run.stderr'),('build_receipt_sha256',source_run/'observer-build.json')]:
        if sha(path)!=r[key]:raise ValueError('RTL identity mismatch')
    for name,digest in b['input_sha256'].items():
        if sha(name)!=digest:raise ValueError('RTL build input changed')
    for prefix,original in [('RTL_MEMTRACE ','vector-memory-h2-9-va2.stderr'),('RTL_NOC ','vector-memory-h2-9-va2.stderr'),('RTL_VA ','vector-memory-h2-9-va2.stderr'),('RTL_VA2 ','vector-memory-h2-9-va2.stderr')]:
        def lines(path):return [x for x in path.read_text().splitlines() if x.startswith(prefix)]
        if lines(source_run/'run.stderr')!=lines(CAP/'build/rtl-loader-diag'/original):raise ValueError('New observer altered original trace')
    frames=parse_frames(source_run/'run.stderr',ROOT/'timing/noc_observer_fields.json');long=frame_vectors(frames);long_body=payload(long,True);long_rows=run('rtl15499-continuous',long_body);compare(long_rows,long)
    # Native keeps its mask state; the only new ready requests come from captured ready-arrival boundaries.
    stable=[x for x in frames if x['tb']>=99367];egress_bit=fixture['flattened_output_vcs']['port2_local_nif3'][0];egress_body=seed({k:stable[0][k] for k in STATE_NAMES})+'pending '+str(stable[0]['waiting_vcs'])+'\n';previous=stable[0]['waiting_vcs']
    for i,x in enumerate(stable):
        arrivals=0 if i==0 else x['waiting_vcs']&~previous
        egress_body+='egress_step '+str(x['tb'])+' '+str(arrivals)+' '+str(x['incoming_route_fire'])+' '+str(x['incoming_route_vc'])+' '+str(x['egress_empty'])+' '+str(egress_bit)+'\n';previous=x['waiting_vcs']
    egress_rows=run('bounded-starvation-ready-arrivals',egress_body)
    grant_counts={str(i):0 for i in range(p['input_virtual_channels'])};free_tbs=[];arrival_counts={str(i):0 for i in range(p['input_virtual_channels'])}
    for previous,current in zip(stable,stable[1:]):
        arrived=current['waiting_vcs']&~previous['waiting_vcs']
        for i in range(p['input_virtual_channels']):arrival_counts[str(i)]+=int(bool(arrived&1<<i))
    for actual,x in zip(egress_rows,stable):
        if len(actual)!=11 or actual[0]!=x['tb'] or actual[9]!=x['waiting_vcs'] or actual[1]!=x['selected_vc']:raise ValueError('Ready-arrival or inner-mask boundary not closed')
        if actual[8]:grant_counts[str(actual[1].bit_length()-1)]+=1
        if x['egress_empty']:
            if actual[6]!=1<<egress_bit:raise ValueError('Native missed captured free egress slot')
            free_tbs.append(x['tb'])
    if grant_counts!={'0':0,'1':766,'2':766,'3':0,'4':0,'5':0} or any(b-a!=20 for a,b in zip(free_tbs,free_tbs[1:])):raise ValueError('Bounded starvation not reproduced')
    for i,source in [(0,564),(3,574),(4,573),(5,575)]:
        if any(x['vc'+str(i)+'_state']!=2 or not x['vc'+str(i)+'_head_word0']&1 or (x['vc'+str(i)+'_head_word0']>>7)&1023!=source for x in stable):raise ValueError('Blocked response header changed')
    invalid=[('unseeded','step 0 0 0 0 0 0\n'),('waiting-width','reset\nstep 0 64 0 0 0 0\n'),('mask-width','seed 64 0 0\n'),('route-vc','reset\nstep 0 0 1 6 0 0\n'),('inconsistent-eligibility','reset\nstep 0 1 0 0 1 0\n'),('local-eligibility-without-request','reset\nstep 0 0 0 0 1 1\n'),('duplicate-ready-arrival','reset\npending 1\negress_step 0 1 0 0 0 12\n')]
    for name,bad in invalid:run('reject-'+name,bad,2)
    # Explicit reset and attempt-without-ready behavior, independent of captured active state.
    directed=run('reset-and-unaccepted-attempt','reset\nstep 0 1 0 0 0 0\nstep 1 3 0 0 0 0\nstep 2 0 1 4 0 0\n')
    if directed!=[[0,1,1,0,0,0,0,0,0],[1,2,3,0,0,0,0,0,0],[2,0,15,0,0,0,0,0,0]]:raise ValueError('Reset/attempt/route-priority mismatch')
    files=[ROOT/'timing'/n for n in ['noc_arbiter.hpp','noc_arbiter.cpp','noc_driver.cpp','noc_check.py','noc_sources.json','noc_observer.cpp','noc_observer.hpp','noc_observer_fields.json','noc_observer_build.py','noc_README.md']]+[compiler,ROOT/profile['fixture'],CAP/'report.json',source_run/'run.json',source_run/'run.stderr',source_run/'run.stdout',source_run/'observer-build.json',Path(r['argv'][0])]
    for name,digest in b['input_sha256'].items():files.append(Path(name))
    for citation in list(profile['parameter_sources'].values())+profile['semantic_sources']:files.append(ROOT/citation['path'])
    for relative,meta in jread(CAP/'report.json')['origins'].items():
        original=Path(meta['path'])
        if '/riscv-tools/lib/' in str(original):
            if sha(original)!=meta['sha256'] or sha(CAP/relative)!=meta['sha256']:raise ValueError('Changed linked RTL host ABI input')
            files.append(original)
    origins={}
    for path in sorted(set(files)):
        path=path.resolve()
        try:rel=Path('inputs')/path.relative_to(ROOT)
        except ValueError:rel=Path('inputs/external')/path.relative_to('/')
        target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);origins[str(rel)]={'path':str(path),'sha256':sha(path)}
    report={'schema':'iris.native_noc_arbiter_component.v1','pass':True,'parameters':p,'source_capsule_sha256':sha(CAP/'report.json'),'native_binary_sha256':sha(binary),'compiler':{'path':str(compiler),'sha256':sha(compiler),'argv':command,'version':subprocess.check_output([str(compiler),'--version'],text=True)},'rtl99':{'cycles':len(vectors),'stage_transitions':len(vectors)*3,'per_row_and_continuous_pass':True,'observed_state_after_first_not_used':True,'poisoned_later_state_does_not_change_serialized_input':True,'mutation_rejections':mutation_rejections},'long_continuous':{'cycles':len(long),'stage_transitions':len(long)*3,'initial_tb':long[0]['tb'],'last_tb':long[-1]['tb'],'initial_state_seeds':1,'observed_state_after_first_not_used':True,'missing_external_state_detected':False,'external_inputs':'Captured queue/route/occupancy eligibility; queue, route, fullpacket and CDC state remain outside this component.'},'bounded_starvation':{'cycles':len(stable),'first_tb':stable[0]['tb'],'last_tb':stable[-1]['tb'],'initial_pending_mask':stable[0]['waiting_vcs'],'ready_arrivals_by_vc':arrival_counts,'free_egress_slots':len(free_tbs),'free_period_tb':20,'grants_by_incoming_vc':grant_counts,'waiting_state_carried_from_ready_arrivals':True,'arbiter_masks_carried':True,'stimulus':'Exact finite arbiter-ready arrivals (waiting rising edges), source route-completion inputs, and local-egress free slots. Native pending mask advances from computed grants; actual percycle waiting state is only a comparison oracle. Other router traffic is excluded in this isolated-egress reproduction.','whole_queue_or_route_model':False},'native_rejections':[x[0] for x in invalid],'source_rtl_modified':False,'whole_noc_certified':False,'timing_calibrated':False,'hardware_contacted':False,'executions':executions,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'rtl99_cycles':len(vectors),'continuous_cycles':len(long),'starvation_grants':grant_counts,'report':str(out/'report.json')}))
if __name__=='__main__':main()
