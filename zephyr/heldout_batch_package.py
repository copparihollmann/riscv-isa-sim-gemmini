#!/usr/bin/env python3
"""Archive exact frozen batch inputs and acceptance evidence without timing fitting."""
import argparse,hashlib,json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true')
    p.add_argument('--batch',type=Path,default=ROOT/'build/fast-heldout-zephyr-compact-v5');p.add_argument('--gate',type=Path,action='append',default=[])
    a=p.parse_args();out=a.output.resolve()
    if a.verify:
        report=json.loads((out/'report.json').read_text())
        for h in report['objects']:
            if sha(out/'objects'/h)!=h:raise ValueError('Changed archived object')
        for path,item in report['inputs'].items():
            if item['sha256']not in report['objects']:raise ValueError('Missing closure object '+path)
        if report['fitting_allowed']or report['timing_certified']:raise ValueError('Heldout closure may not claim fitting/certification')
        print(json.dumps({'verified':True,'objects':len(report['objects']),'files':len(report['inputs'])}));return
    out.mkdir(parents=True,exist_ok=False);objects=out/'objects';objects.mkdir();inputs={};sizes={}
    def retain(original,source=None,wanted=None):
        original=Path(original).resolve();source=Path(source or original);digest=sha(source)
        if wanted and digest!=wanted:raise ValueError('Evidence changed '+str(original))
        dest=objects/digest
        if not dest.exists():shutil.copyfile(source,dest)
        if sha(dest)!=digest:raise ValueError('Copy changed')
        inputs[str(original)]={'sha256':digest,'object':'objects/'+digest};sizes[digest]=dest.stat().st_size
        return digest
    batch=a.batch.resolve();manifest=json.loads((batch/'manifest.json').read_text());retain(batch/'manifest.json')
    for name,item in manifest['inputs'].items():retain(name,batch/item['object'],item['sha256'])
    for name in ['cases.json','golden.json','build.log']:retain(batch/name)
    gates=a.gate or [ROOT/'build/fast-heldout-compact-functional-seed0-v1/report.json',ROOT/'build/fast-heldout-compact-functional-seed17-v1/report.json',ROOT/'build/fast-heldout-compact-controls-v3/report.json',ROOT/'build/fast-validation-OS-unfitted-baseline-v1/report.json',ROOT/'build/fast-fit-independent-audit-v2/report.json']
    gate_entries=[]
    for path in gates:
        path=path.resolve();data=json.loads(path.read_text())
        if data.get('pass')is not True:raise ValueError('Failed or incomplete gate '+str(path))
        gate_entries.append({'path':str(path),'sha256':retain(path),'schema':data['schema']})
        for name,h in data.get('input_sha256',{}).items():retain(name,wanted=h)
        for path2 in path.parent.rglob('*'):
            if path2.is_file() and path2.suffix!='.pyc':retain(path2)
    for name in ['zephyr/heldout_batch_build.py','zephyr/heldout_batch_run.py','zephyr/heldout_batch_checks.py','zephyr/heldout_batch_compare.py','zephyr/test_heldout_batch_compare.py','zephyr/empirical_os_validate.py','zephyr/heldout_batch_package.py','zephyr/heldout-batch/README.md','hardware/dtypes.json','hardware/manifest.json']:
        retain(ROOT/name)
    report={'schema':'iris.frozen_compact_heldout_batch_acceptance_closure.v1','pass':True,'workload_manifest_sha256':sha(batch/'manifest.json'),
        'ELF_sha256':manifest['ELF_sha256'],'expected_regions':188,'global_elapsed_intervals':8 if manifest.get('global_elapsed_source') else 0,'cases':128,'physical_harts':3,'trials':5,
        'gates':gate_entries,'inputs':inputs,'objects':sizes,'unique_bytes':sum(sizes.values()),
        'fitting_allowed':False,'timing_certified':False,'hardware_contacted':False,
        'scope':'Exact compact independent batch and actual functional/earlyexperimental-engine checks. No hardware timing reference or modelaccuracy admission. Original hardware divergence exclusions remain.'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'files':len(inputs),'objects':len(sizes),'unique_bytes':report['unique_bytes'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
