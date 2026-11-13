#!/usr/bin/env python3
"""Build v2: small memory probes and compute families precede expensive streams.

Its layout, cache/predictor history and post-ROI record stores differ from the
original campaign: only a fresh exact-ELF reference may calibrate this workload.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build(output, compiler, trials):
    output.mkdir(parents=True, exist_ok=False)
    parent=output/'parent-derived'
    subprocess.run([sys.executable,str(ROOT/'benchmarks/campaign/build.py'),'--output',str(parent),
                    '--compiler',str(compiler),'--trials',str(trials)],check=True,capture_output=True)
    corpus=json.loads((parent/'corpus.json').read_text())
    originals=copy.deepcopy(corpus['cases'])
    # Order by static source work/footprint, never measured target cycles.
    # The wrappers still process every case; their phase hooks emit no UART.
    rank={'dependent':0,'independent':1,'branch':2,'scalar_fp':3,'vector_int':4,'vector_fp':5,
          'vme_int':6,'vme_fp8':7,'row_read':8,'row_write':9,'tile_zero':10,'shared_fpu':11,
          'vme_memory':12,'vme_refusal':13,'pipeline':14,'pipeline_vme':15,'atomic':16,
          'frontend':17,'memory':18}
    memory=[c for c in originals if c['suite']=='memory']
    distribution=[c for c in originals if c['suite']=='distribution']
    def priority(c):
        group=rank[c['kind']]
        if c['kind']=='memory':
            if c['protocol']==1 and c['mode']==0 and c['bytes']==131072 and c['mask'] in (1,3): group=17
            elif (c['protocol']==1 and c['mode']==0 and c['bytes']==1048576 and c['mask'] in (1,3,4)
                  and c['parent_case_id'].startswith('v2.contention.private-read.')): group=18
            else: group=20
        elif c['kind']=='frontend': group=19
        return (group,c.get('bytes',0) if c['kind'] in ('memory','frontend') else 0,c['parent_case_id'],c['trial_id'])
    distribution.sort(key=priority)
    priority_cases=len(memory)+sum(priority(c)[0]<20 for c in distribution)
    baseline=[c for c in originals if c['suite']=='baseline']
    originals=memory+distribution+baseline
    corpus['cases']=copy.deepcopy(originals)
    corpus['order']='memory routes first; distribution by static kind/footprint/semantic parent/trial; baseline last'
    corpus['ordering_uses_measured_cycles']=False
    corpus['priority_prefix_cases']=priority_cases
    corpus['priority_prefix_regions']=sum(bin(c['mask']).count('1') for c in originals[:priority_cases])
    corpus['small_streaming_basis_policy']='Warm128KiB reads masks1/3, then warm1MiB private reads masks1/3/4, all3trials; all other large/eviction traffic deferred'
    corpus['priority_distribution_kind_order']=rank
    for case in corpus['cases']:
        case['semantic_parent_case_id']=case['parent_case_id']
        case['case_id']='buffered.v2.'+case['case_id']
        case['parent_case_id']='buffered.v2.'+case['parent_case_id']
    corpus.update(split_id='iris-buffered-priority-fit-campaign-v2',schema='iris.buffered_fitting_corpus.v2',
        purpose='New exact-ELF buffered fitting workload; old campaign timings are inapplicable',
        original_corpus_sha256=sha(parent/'corpus.json'),
        console_policy='All numeric checks and record stores before bulk console; no per-case UART',
        cache_policy='New evolving cache/branch state, same parent preparation; no cold-state guarantee',
        source_image_association_verified=False)
    (output/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    for name in ('campaign_counts.h','baseline_ids.inc','memory_cases.inc'):
        (output/name).write_bytes((parent/name).read_bytes())
    distribution=[c for c in originals if c['suite']=='distribution']
    fields=('n','mask','sew','lmul','mode','bytes','protocol','edge','tk','tiles')
    (output/'distribution_cases.inc').write_text('static const case_t experiments[]={\n'+',\n'.join('{'+json.dumps(c['case_id'])+',K_'+c['kind']+','+','.join(str(c[k]) for k in fields)+',{'+','.join(str(v)+'ULL' for v in c['expected_checksums'])+'}}' for c in distribution)+'\n};\n')
    tables=[]
    for name,key in [('original_ids',None),('ids','case_id'),('parent_ids','parent_case_id'),('suites','suite')]:
        values=[c['case_id'] for c in originals] if key is None else [c[key] for c in corpus['cases']]
        tables.append('static const char *const buffered_'+name+'[]={'+','.join(json.dumps(v) for v in values)+'};')
    for name,key in [('masks','mask'),('trials','trial_id')]:
        tables.append('static const unsigned buffered_'+name+'[]={'+','.join(str(c[key]) for c in corpus['cases'])+'};')
    tables.append('static const uint64_t buffered_goldens[][3]={'+','.join('{'+','.join(str(v)+'ULL' for v in c['expected_checksums'])+'}' for c in corpus['cases'])+'};')
    (output/'buffered_cases.inc').write_text('\n'.join(tables)+'\n')
    transformations=[]
    for suite in ('baseline','distribution','memory'):
        original=(parent/(suite+'.c')).read_text()
        text=original.replace('#include "campaign.h"','#include "campaign.h"\n#include "buffered.h"',1)
        start=text.index('putstr("IRIS_REGION ')
        stop=text.index('putstr("}\\n");',start)+len('putstr("}\\n");')
        if suite=='baseline': args='id,i,r.start,r.end,r.instret,r.checksum,r.expected'
        elif suite=='distribution': args='c->id,i,r.start,r.end,r.instret,r.checksum,c->expected[i]'
        else: args='c->id,i,r.begin,r.end,r.instructions,r.checksum,c->expected[i]'
        removed=text[start:stop]
        text=text[:start]+'buffer_record('+args+');'+text[stop:]
        marker='  if(!h&&failed)campaign_abort("'+suite+'",failed);'
        assert marker in text
        # Only the first occurrence is the per-case check; later suite checks
        # must not advance the record index a second time.
        text=text.replace(marker,'  if(!h)buffer_commit_case();\n'+marker,1)
        before=original[:original.index('static void run(')]
        after=text[:text.index('static void run(')].replace('#include "buffered.h"\n','')
        assert before==after and 'IRIS_REGION ' not in text
        (output/(suite+'.c')).write_text(text)
        transformations.append({'suite':suite,'parent_derived_sha256':sha(parent/(suite+'.c')),
            'new_source_sha256':sha(output/(suite+'.c')),
            'kernel_and_preparation_source_prefix_unchanged':True,
            'kernel_prefix_sha256':hashlib.sha256(before.encode()).hexdigest(),
            'removed_console_block_sha256':hashlib.sha256(removed.encode()).hexdigest()})
    parent_build=json.loads((parent/'build.json').read_text())
    argv=parent_build['argv']
    argv=[('-I'+str(output) if v=='-I'+str(parent) else v) for v in argv]
    argv.insert(argv.index('-T'),'-I'+str(HERE))
    argv=[str(HERE/'main_reordered.c') if v==str(ROOT/'benchmarks/campaign/main.c') else
          str(output/Path(v).name) if v in [str(parent/(s+'.c')) for s in ('baseline','distribution','memory')] else v for v in argv]
    argv[-1]=str(output/'campaign.elf')
    process=subprocess.run(argv,capture_output=True,text=True)
    (output/'build.stdout').write_text(process.stdout);(output/'build.stderr').write_text(process.stderr)
    if process.returncode: raise RuntimeError('Buffered build failed; inspect build.stderr')
    elf=output/'campaign.elf'
    tool=compiler.with_name('riscv64-unknown-elf-objdump')
    with (output/'disassembly.txt').open('w') as stream:
        subprocess.run([str(tool),'-d',str(elf)],stdout=stream,check=True)
    nm=compiler.with_name('riscv64-unknown-elf-nm')
    symbols=subprocess.check_output([str(nm),'-S','--defined-only',str(elf)],text=True)
    (output/'symbols.txt').write_text(symbols)
    objects={}
    for line in symbols.splitlines():
        f=line.split()
        if len(f)==4 and f[3] in ('buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count'):
            objects[f[3]]={'address':int(f[0],16),'size':int(f[1],16)}
    if set(objects)!={'buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count'}:
        raise ValueError('Missing readback objects')
    if objects['buffered_records']['size']!=64*corpus['expected_region_count']:
        raise ValueError('Unexpected record geometry')
    raw=elf.read_bytes();phoff=struct.unpack_from('<Q',raw,32)[0];phsize,phnum=struct.unpack_from('<HH',raw,54)
    segments=[];sentinel=None
    for k in range(phnum):
        typ,flags,off,va,pa,fs,ms,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+k*phsize)
        if typ!=1: continue
        segments.append({'physical_base':pa,'memory_bytes':ms,'file_bytes':fs})
        for name,(base,size) in corpus['memory_regions'].items():
            if max(base,pa)<min(base+size,pa+ms): raise ValueError('ELF overlaps tested memory '+name)
        addr=objects['buffered_measurements_done']['address']
        if pa<=addr and addr+8<=pa+fs:
            sentinel=int.from_bytes(raw[off+addr-pa:off+addr-pa+8],'little')
    if sentinel!=(1<<64)-1: raise ValueError('Debug stop sentinel must be known file-backed UINT64_MAX')
    (output/'readback-layout.json').write_text(json.dumps({'schema':'iris.buffered_campaign_readback_layout.v1',
        'elf_sha256':sha(elf),'objects':objects,'fields':['case_index','hart','start','end','instret','checksum','expected','pass'],
        'record_bytes':64,'records':corpus['expected_region_count'],'stop_sentinel_initial_value':sentinel,
        'stop_sentinel_complete_value':0,'file_backed_initial_sentinel_verified':True,
        'intentional_debugger_stop_is_normal_guest_exit':False},indent=2)+'\n')
    paths=[HERE/'main_reordered.c',HERE/'buffered.h',Path(__file__).resolve(),compiler,tool,nm,parent/'build.json',parent/'corpus.json']
    paths += [p for p in output.iterdir() if p.suffix in ('.c','.inc','.h','.json')]
    inputs={str(p):sha(p) for p in paths}
    inputs.update(parent_build['input_sha256'])
    (output/'inputs').mkdir()
    for path,digest in inputs.items():
        dest=output/'inputs'/digest
        if not dest.exists(): dest.write_bytes(Path(path).read_bytes())
    receipt={'schema':'iris.buffered_campaign_build.v2','argv':argv,'input_sha256':inputs,
        'elf_sha256':sha(elf),'corpus_sha256':sha(output/'corpus.json'),
        'readback_layout_sha256':sha(output/'readback-layout.json'),
        'disassembly_sha256':sha(output/'disassembly.txt'),'source_transformations':transformations,
        'parent_build_sha256':sha(parent/'build.json'),'ELF_load_segments':segments,
        'cases':len(corpus['cases']),'regions':corpus['expected_region_count'],'trials':trials,
        'parent_kernel_source_unchanged':True,'ordering_uses_measured_cycles':False,'same_ELF_as_original_campaign':False,
        'old_campaign_timings_applicable':False,'hardware_contacted':False,'functional_qualification_passed':False}
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--trials',type=int,default=3)
    p.add_argument('--compiler',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc'))
    a=p.parse_args()
    if not 1<=a.trials<=20: p.error('Trials must be 1..20')
    r=build(a.output.resolve(),a.compiler.resolve(),a.trials)
    print(json.dumps({k:r[k] for k in ('elf_sha256','cases','regions','trials')}))


if __name__=='__main__': main()
