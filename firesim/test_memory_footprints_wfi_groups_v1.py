#!/usr/bin/env python3
"""Actual frozen packet admission plus changed-input / partial-prefix controls."""
import copy
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from prepare_memory_footprints_wfi_groups_v1 import admit
from analyze_memory_footprints_wfi_groups_v1 import partial_groups

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/memory-footprints-WFI-groups-reviewed-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    controls=[]
    def reject(name, action):
        try:action()
        except(ValueError,AssertionError,KeyError,TypeError):controls.append(name);return
        raise ValueError('Corruption admitted: '+name)
    ready=json.loads((BUILD/'ready.json').read_text())
    admit(BUILD,sha(BUILD/'ready.json'))
    reject('wrong-ready-digest',lambda:admit(BUILD,'0'*64))
    for name,field,value in [('old-IRQ-history','new_reference_due_to_IRQ_and_cache_history',False),
                             ('wrong-barrier-proof','barrier_proof_sha256','0'*64),
                             ('wrong-region-count','required_regions',359),
                             ('unfrozen-source','source_frozen',False),
                             ('old-ELF','elf_sha256','0'*64)]:
        with tempfile.TemporaryDirectory()as tmp:
            d=Path(tmp)
            for path in BUILD.iterdir():
                if path.is_file():shutil.copyfile(path,d/path.name)
            changed=copy.deepcopy(ready);changed[field]=value
            (d/'ready.json').write_text(json.dumps(changed)+'\n')
            reject(name,lambda:admit(d,sha(d/'ready.json')))
    corpus=json.loads((BUILD/'corpus.json').read_text())
    text=(ROOT/'build/memory-footprints-mtime-wfi-groups-fit-v8/seed0/stdout').read_text()
    lines=text.splitlines();cut=next(i for i,l in enumerate(lines)if l.startswith('IRIS_FOOTPRINT_GROUP '))
    rows,scope=partial_groups('\n'.join(lines[:cut+1]),corpus)
    if len(rows)!=24 or scope['full_run_passed']or scope['calibration_usable']:raise ValueError('Partial proof overclaimed')
    reject('truncated-without-frontier',lambda:partial_groups('\n'.join(lines[:cut-1]),corpus))
    bad=lines[:cut+1];r=json.loads(bad[0][len('IRIS_REGION '):]);r['mtime_before']=r['mtime_after']+1;bad[0]='IRIS_REGION '+json.dumps(r)
    reject('reversed-global-window',lambda:partial_groups('\n'.join(bad),corpus))
    out=ROOT/'build/memory-footprints-WFI-managed-admission-tests-v1';out.mkdir(exist_ok=False)
    sources=[Path(__file__).resolve(),*[ROOT/'firesim'/n for n in ['prepare_memory_footprints_wfi_groups_v1.py','analyze_memory_footprints_wfi_groups_v1.py','memory_footprints_wfi_groups_review_v1.py','check_memory_footprint_wfi_groups_clint_v1.py']],BUILD/'ready.json',BUILD/'review.json']
    report={'schema':'iris.memory_footprint_WFI_managed_admission_tests.v1','pass':True,'actual_admitted_cohorts':105,'actual_admitted_regions':360,'corruption_refusals':controls,'partial_frontier_regions':24,'hardware_contacted':False,'new_exact_reference_required':True,'input_sha256':{str(p):sha(p)for p in sources}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'controls':len(controls),'sha256':sha(out/'report.json')}))

if __name__=='__main__':main()
