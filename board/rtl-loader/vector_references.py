#!/usr/bin/env python3
"""Freeze selected vector/FPComp functional observations with explicit harness scope."""
import argparse,hashlib,json,re,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'build/rtl-loader-diag'
FIELDS=['stage','actual','expected','cause','pc','tval','checks','done']
CASES={'cold12-scalar':(3,[259]*3),'cold12-vector':(3,[259]*3),'cold12-vector-fenced':(3,[259]*3),'vector-memory-h2only-backoff':(4,[0,0,128]),'vector-memory-h2-9-load-fences':(4,[0,0,72]),'fpcomp-aggregate-load-fences':(3,[52]*3)}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def decode(path,kind,checks):
    lines=path.read_text().splitlines()
    if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',x) for x in lines):raise ValueError('Invalid TSI signature')
    values=[int(x,16) for x in lines]
    if values[:4]!=[0x4952495350524f42,1,kind,0]:raise ValueError('Failed or wrong-kind vector mailbox')
    rows=[dict(zip(FIELDS,values[4+8*h:12+8*h]),hart=h) for h in range(3)]
    if any(x['done']!=1 or x['checks']!=checks[x['hart']] or x['actual']!=x['expected'] for x in rows):raise ValueError('Incomplete or mismatching vector hart')
    return rows

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-selected-vector-references-v1');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        j=json.loads((out/'report.json').read_text())
        for name,digest in j['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('Frozen vector observation changed')
        for name,(kind,checks) in CASES.items():
            if decode(out/j['cases'][name]['signature'],kind,checks)!=j['cases'][name]['harts']:raise ValueError('Vector signature reader changed')
        print(json.dumps({'pass':True,'programs':len(CASES),'full_rtl_certified':False}));return
    if out.exists():raise ValueError('Refuse to overwrite vector reference capsule')
    out.mkdir(parents=True);origins={}
    def save(path):
        path=Path(path).resolve()
        try:rel=path.relative_to(ROOT)
        except ValueError:rel=Path('external')/path.relative_to('/')
        dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dst);origins[str(rel)]={'path':str(path),'sha256':sha(path)};return str(rel)
    cases={}
    for name,(kind,checks) in CASES.items():
        run=D/(name+'.json');r=json.loads(run.read_text());elf=Path(r['argv'][-1]);binary=Path(r['argv'][0])
        if r['exit_status'] or r['timed_out'] or sha(elf)!=r['elf_sha256'] or sha(binary)!=r['binary_sha256']:raise ValueError('Wrong/failed selected vector execution')
        item={ext:save(D/(name+'.'+ext)) for ext in ['json','signature','stdout','stderr']};item.update(elf=save(elf),binary=save(binary),elf_sha256=r['elf_sha256'],binary_sha256=r['binary_sha256'],host_env_overrides=r.get('env_overrides',{}),harts=decode(D/(name+'.signature'),kind,checks),host_seconds=r['host_seconds'])
        if name=='fpcomp-aggregate-load-fences':item.update(fpcomp_cases_per_hart=16,altfmt_values=[0,1],sew_bits=[16,32,64],masked_output_bytes_compared_per_hart=1024,initialization_vector_stores_fenced=True,operand_loads_individually_fenced=True)
        cases[name]=item
    for rec in ['deep-state-build.json','poll-backoff-build.json','cold12-build.json','vector-memory-build.json','fpcomp-aggregate-build.json','load-fences-build.json']:save(D/rec)
    for path in (ROOT/'board/rtl-loader').rglob('*'):
        if path.is_file() and '__pycache__' not in str(path):save(path)
    for name in ['probe_runtime.c','probe_runtime.h']:save(ROOT/'build/definedness-dev/rtl-probes'/name)
    for name in ['runtime.h','link.ld']:save(ROOT/'benchmarks'/name)
    for name in ['deep-state-build.json']:
        b=json.loads((D/name).read_text())
        for path,digest in b['input_sha256'].items():
            if sha(path)!=digest:raise ValueError('Changed native RTL model input')
            save(path)
        for path in b['link_argv']:
            if path.endswith('.o') or path.endswith('.a'):save(Path(path) if Path(path).is_absolute() else ROOT/'build/rtl-verilator/model'/path)
    for path in [ROOT/'build/rtl-verilator/manifest.json',ROOT/'hardware/manifest.json',ROOT/'hardware/memory-paths.json',ROOT/'build/rtl-memory-frontier-v1/report.json',ROOT/'build/rtl-memory-packets-v1/report.json']:save(path)
    j={'schema':'iris.selected_saved_rtl_vector_references.v1','selected_probes_pass':True,'cases':cases,'physical_harts':[0,1,2],'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','source_design':'chipyard.harness.TestHarness.IrisConfig','source_memory_lowering':'native FIRRTL memory semantics','preload':'explicit native-RAM FESVR hooks with PT_LOAD BSS zero fill and compactCRT','full_fpcomp_sequence_scope':'16 selected H/S/D/max/min/sgnj/compare/reduction cases perhart with both source altfmt settings; individually fenced operand loads, explicitly changed test ELF; all1024maskedbytes compared perhart by zero-OR check','unfenced_memory_frontier_resolved':False,'host_poll_backoff_general_fix':False,'four_state_definedness_available':False,'unknown_reset_behavior_proven_irrelevant':False,'matches_ethan_firesim_image':False,'full_rtl_certified':False,'timing_calibrated':False,'hardware_contacted':False,'origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    (out/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(out/'report.json')

if __name__=='__main__':main()
