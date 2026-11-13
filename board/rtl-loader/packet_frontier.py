#!/usr/bin/env python3
"""Independently match every sampled RTL load A/D transfer and freeze evidence."""
import argparse,hashlib,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'build/rtl-loader-diag'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def analyse(path):
    events=[json.loads(x.split(' ',1)[1]) for x in path.read_text().splitlines() if x.startswith('RTL_MEMTRACE ')]
    pending={};completed=[];requests=responses=0;last_tb=0;last_completion={};rapid_reissues=0
    for event in events:
        if event['tb']<last_tb or not 0<=event['tag']<32:raise ValueError('Invalid packet event order/tag')
        last_tb=event['tb'];tag=event['tag']
        if event['channel']=='A':
            if tag in pending or event['duplicate_pending']:raise ValueError('Duplicate active load tag')
            prev=last_completion.get(tag)
            if prev and event['address']==prev['request_address'] and event['tb']-prev['tb']==2:rapid_reissues+=1
            pending[tag]=event;requests+=1
        elif event['channel']=='D':
            old=pending.pop(tag,None)
            if old is None or not event['matched'] or event['request_address']!=old['address'] or event['request_tb']!=old['tb']:raise ValueError('Unmatched/misattributed response')
            completed.append(event['tb']-old['tb']);last_completion[tag]=event;responses+=1
        else:raise ValueError('Unknown packet channel')
    if requests-responses!=len(pending):raise ValueError('Inconsistent packet accounting')
    return {'a_transfers':requests,'d_transfers':responses,'remaining_requests':len(pending),'last_event_tb':last_tb,'maximum_completed_latency_tb':max(completed),'same_tag_same_address_reissued_two_tb_after_response':rapid_reissues,'oldest_pending':min(pending.values(),key=lambda x:x['tb']),'pending':[dict(tag=tag,address=hex(x['address']),accepted_tb=x['tb']) for tag,x in sorted(pending.items())],'interpretation':'Sampled control snapshots alias periodic packet activity: later responses/reissues continue while the oldest pending load and guest progress remain blocked. Reissue-origin identification beyond this observer and root cause are not proven.'}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-memory-packets-v1');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        j=json.loads((out/'report.json').read_text())
        for name,digest in j['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('Frozen packet artifact changed')
        if analyse(out/j['stderr'])!=j['packets']:raise ValueError('Packet analysis changed')
        print(json.dumps({'pass':True,'requests':j['packets']['a_transfers'],'responses':j['packets']['d_transfers'],'cause_identified':False}));return
    if out.exists():raise ValueError('Refuse to overwrite frozen packet evidence')
    run=D/'vector-memory-h2-9-packets.json';r=json.loads(run.read_text());stderr=D/'vector-memory-h2-9-packets.stderr';packets=analyse(stderr)
    if r['exit_status']!=1 or r['timed_out'] or packets['remaining_requests']!=17 or packets['same_tag_same_address_reissued_two_tb_after_response']<100:raise ValueError('Expected bounded blocked-head/reissue observation absent')
    if packets['oldest_pending']['tag']!=12 or packets['oldest_pending']['address']!=0x80003940:raise ValueError('Observed oldest pending request changed')
    if sha(stderr)!=r['stderr_sha256'] or sha(Path(r['argv'][0]))!=r['binary_sha256'] or sha(Path(r['argv'][-1]))!=r['elf_sha256']:raise ValueError('Execution identity changed')
    out.mkdir(parents=True);origins={}
    def save(path):
        path=Path(path).resolve()
        try:rel=path.relative_to(ROOT)
        except ValueError:rel=Path('external')/path.relative_to('/')
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst);origins[str(rel)]={'path':str(path),'sha256':sha(path)};return str(rel)
    paths=[run,stderr,D/'vector-memory-h2-9-packets.stdout',D/'packet-diag-build.json',D/'deep-state-build.json',Path(r['argv'][0]),Path(r['argv'][-1]),Path(__file__),ROOT/'build/rtl-memory-frontier-v1/report.json',ROOT/'build/rtl-verilator/manifest.json']
    for name in ['packet_main.cc','deep_fields.inc','diag_fields.inc','SimTSI.cc','start-loader-bss.S','vector-memory-counted.c']:paths.append(ROOT/'board/rtl-loader'/name)
    build=json.loads((D/'packet-diag-build.json').read_text())
    for name in build['link_argv']:
        if name.endswith('.o') or name.endswith('.a'):paths.append(Path(name) if Path(name).is_absolute() else ROOT/'build/rtl-verilator/model'/name)
    for name,digest in json.loads((D/'deep-state-build.json').read_text())['input_sha256'].items():
        if sha(name)!=digest:raise ValueError('Underlying native model changed')
        paths.append(Path(name))
    for path in sorted(set(paths)):save(path)
    j={'schema':'iris.saved_rtl_packet_frontier.v1','packets':packets,'stderr':str(stderr.relative_to(ROOT)),'prior_sampled_state_report_sha256':sha(ROOT/'build/rtl-memory-frontier-v1/report.json'),'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','rtl_design_modified':False,'observation_sampling':'Old stable transfer values before eval; generated tile2 clock rising detected after eval; D then A processing permits tag reuse. Observer A-D count matches sampled TL reader inflights.','runtime_scope':'Separate read-only host instrumentation binary, same9iteration guest ELF and reset/preload/seed1; not a deployed-image observation','sampling_alias_correction':'Stationary10kTB snapshots do not imply no intermediate TL activity, no replay events or global deadlock. All raw packet events are retained.','cause_identified':False,'global_deadlock_proven':False,'four_state_definedness_available':False,'unknown_reset_behavior_proven_irrelevant':False,'memory_lowering':'native FIRRTL memories','matches_ethan_firesim_image':False,'timing_calibrated':False,'hardware_contacted':False,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    (out/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(out/'report.json')

if __name__=='__main__':main()
