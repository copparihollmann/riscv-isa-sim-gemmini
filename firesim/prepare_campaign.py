#!/usr/bin/env python3
"""Prepare initial recovery/calibration batches locally, without contacting FPGA."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benchmarks.export_cases import export
from batch_runner import digest,prepare,save_manifest,validate_cases,OBSERVABILITY_REPORT

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--deploy',type=Path,default=Path('/scratch/eygao/iris-cy/sims/firesim/deploy'))
    p.add_argument('--driver-tar',type=Path,required=True)
    p.add_argument('--observability-report',type=Path,default=OBSERVABILITY_REPORT)
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    corpus1=ROOT/'benchmarks/calibration-corpus.json';corpus2=ROOT/'benchmarks/v2/build/corpus.json'
    cases_dir=out/'cases';cases_dir.mkdir();jobs=[]
    for name,elf,corpus,smoke,validator in [
        ('smoke',ROOT/'benchmarks/build/smoke.elf',corpus1,True,'benchmarks/validate_console.py --smoke'),
        ('baseline',ROOT/'benchmarks/build/batch.elf',corpus1,False,'benchmarks/validate_console.py'),
        ('distribution-v2',ROOT/'benchmarks/v2/build/batch-v2.elf',corpus2,False,'benchmarks/v2/validate.py')]:
        raw=corpus.read_bytes();rows=export(json.loads(raw),smoke=smoke)
        for row in rows:row['corpus_sha256']=hashlib.sha256(raw).hexdigest()
        validate_cases(rows,True);cases=cases_dir/(name+'.json');cases.write_text(json.dumps(rows,indent=2)+'\n')
        job=out/name
        manager,manifest=prepare(args.deploy.resolve(),job,elf,rows,args.deploy/'config_runtime.yaml',
                                 args.deploy/'config_hwdb.yaml',args.driver_tar,
                                 observability_report=args.observability_report)
        manifest.update(require_regions=True,require_goldens=True,calibration_usable=False,
                        corpus_sha256=digest(corpus),post_validation_required=validator,
                        hardware_source_association_verified=False)
        manifest['input_sha256'].update({str(corpus):digest(corpus),str(cases):digest(cases)})
        save_manifest(job,manifest)
        jobs.append({'name':name,'job':str(job),'cases':len(rows),'expected_regions':sum(len(r['active_harts']) for r in rows),
                     'elf_sha256':manifest['elf_sha256'],'run_receipt_sha256':digest(job/'run.json'),
                     'verify_argv':[sys.executable,str(ROOT/'firesim/run_prepared.py'),str(job)],
                     'execute_argv':['/scratch/eygao/iris-cy/.conda-env/bin/python3',str(ROOT/'firesim/run_prepared.py'),str(job),
                                     '--execute','--allocation-id','<current-exclusive-allocation>']})
    campaign={'schema_version':1,'status':'prepared_not_executed','hardware_contacted':False,
              'generator_sha256':digest(Path(__file__)),'jobs':jobs,'calibrated':False,
              'prerequisites':['Operator restores host and PCIe/FPGA health','Authorized manager setup path and current exclusive allocation',
                  'Loaded image/driver/source association before admitting calibration','Source FireSim manager environment'],
              'remaining_suite':['Source/CSR/dtype identity probes','SMP synchronization negative/positive corpus',
                  'Actual Zephyr/compiler fitting batches','Additional cache/vector/VME overlap identification','Repeated trials and independent held-outs'],
              'note':'These initial three batches are immediately preparable; they are not the complete calibration/validation campaign.'}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2)+'\n');print(out/'campaign.json')

if __name__=='__main__':main()
