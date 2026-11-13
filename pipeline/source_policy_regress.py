#!/usr/bin/env python3
"""Run unchanged functional goldens after a proved source counter-policy change."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import run_case,symbols
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-counter-policy-v1/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-counter-policy-v1/libsifive_uart.so')
    parser.add_argument('--output',type=Path,default=ROOT/'build/counter-policy-v1-functional32')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress","calibrated":false}\n')
    provenance=ROOT/'build/snapshot-5e6cc309/provenance.json';baseline=json.loads(provenance.read_text());results=[]
    native=args.binary.resolve();uart=args.uart.resolve();identity=(sha(native),sha(uart))
    for row in baseline['selftest']['guest_results']:
        name=row['name'];argv=list(row['argv']);reference=name.endswith('-reference')
        if not reference:
            argv[0]=str(native);argv=['--extlib='+str(uart) if a.startswith('--extlib=') else a for a in argv]
        elif sha(argv[0])!=baseline['reference_binary_sha256']:raise RuntimeError('upstream reference changed')
        if sha(argv[-1])!=row['elf_sha256']:raise RuntimeError('unchanged golden guest ELF changed')
        env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);env.pop('IRIS_FATAL_PCS',None)
        if name=='fatal-entry':env['IRIS_FATAL_PCS']=hex(symbols(argv[-1])['_start'])
        result=run_case(name,argv,env,out,expected=row['expected_exit_status'],timeout=120)
        result.update(binary_sha256=sha(argv[0]),reference_case=reference,
                      legacy_stdout_equal=result['stdout_sha256']==row['stdout_sha256'],
                      legacy_stderr_equal=result['stderr_sha256']==row['stderr_sha256'])
        if not result['pass']:raise RuntimeError('unchanged functional golden failed: '+name)
        results.append(result)
    if len(results)!=32 or (sha(native),sha(uart))!=identity:raise RuntimeError('functional32 scope/bytes changed')
    report=dict(schema='iris.source_counter_policy.functionals.v1',status='passed_unchanged_functional32_goldens',
                binary_sha256=identity[0],uart_sha256=identity[1],baseline_provenance_sha256=sha(provenance),results=results,
                source_sha256={'pipeline/source_policy_regress.py':sha(__file__),'spike/run_functional.py':sha(ROOT/'spike/run_functional.py')},
                counter_policy='Iris_source_counter_edge_v1',old_golden_sources_modified=False,
                legacy_text_hashes_are_not_new_counter_goldens=True,calibrated=False,rtl_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],cases=len(results),receipt=str(out/'results.json'))))


if __name__=='__main__':main()
