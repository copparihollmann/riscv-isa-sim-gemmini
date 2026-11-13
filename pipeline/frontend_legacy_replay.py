#!/usr/bin/env python3
"""Replay byte-bound frozen258 guests and require identical legacy graph bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();uart=a.uart.resolve();identity=sha(binary),sha(uart)
    manifest=ROOT/'build/frontend-bounded-native-frozen-258143d6/manifest.json';frozen=json.loads(manifest.read_text());rows=[];inputs={str(manifest):sha(manifest),str(Path(__file__).resolve()):sha(__file__)}
    groups=['frontend-bounded-native-directed-v1','frontend-bounded-native-memory-v1','frontend-bounded-native-live8-v1']
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    for group in groups:
        receipt=ROOT/'build'/group/'results.json'
        if sha(receipt)!=frozen['reports'][group]['sha256']:raise ValueError('frozen legacy report changed')
        inputs[str(receipt)]=sha(receipt);old=json.loads(receipt.read_text())
        for row in old['results']:
            if row.get('binary_sha256',old['binary_sha256'])!=frozen['binary_sha256']:continue
            name=group+'-'+row['name'];target=out/name;target.mkdir();argv=list(row['argv']);argv[0]=str(binary);argv=['--extlib='+str(uart) if x.startswith('--extlib=') else x for x in argv]
            old_graph=None
            for i,x in enumerate(argv):
                if x.startswith('--iris-timing-trace='):
                    old_graph=Path(x.split('=',1)[1]);argv[i]='--iris-timing-trace='+str(target/'graph.json')
            for arg in argv[1:]:
                path=Path(arg.split('=',1)[1])if '=' in arg else Path(arg)
                if path.is_file() and not arg.startswith(('--extlib=','--iris-timing-trace=')):inputs[str(path.resolve())]=sha(path)
            stdout=receipt.parent/(row['name']+'.stdout');stderr=receipt.parent/(row['name']+'.stderr')
            if sha(stdout)!=row['stdout_sha256'] or sha(stderr)!=row['stderr_sha256']:raise ValueError('frozen console bytes changed')
            if old_graph is None or sha(old_graph)!=row['graph_sha256']:raise ValueError('frozen graph bytes changed')
            start=time.perf_counter();r=subprocess.run(argv,env=env,text=True,capture_output=True,timeout=90);elapsed=time.perf_counter()-start
            (target/'stdout').write_text(r.stdout);(target/'stderr').write_text(r.stderr)
            if r.returncode or (target/'stdout').read_bytes()!=stdout.read_bytes() or (target/'stderr').read_bytes()!=stderr.read_bytes() or sha(target/'graph.json')!=row['graph_sha256']:
                raise ValueError('legacy frontend-off behavior changed: '+name+' '+r.stderr)
            rows.append(dict(name=name,argv=argv,host_seconds=elapsed,elf_sha256=sha(argv[-1]),graph_sha256=sha(target/'graph.json'),stdout_sha256=sha(target/'stdout'),stderr_sha256=sha(target/'stderr'),graph_byte_identical=True))
    if identity!=(sha(binary),sha(uart)) or any(sha(path)!=digest for path,digest in inputs.items()):raise ValueError('legacy gate inputs changed')
    report=dict(schema='iris.frontend.legacy_replay.v1',status='passed_frontend_disabled_legacy_byte_identity',binary_sha256=identity[0],uart_sha256=identity[1],reference_binary_sha256=frozen['binary_sha256'],rows=rows,input_sha256=inputs,
                scope='Exact frozen258 positive ELF/fixture/console/counter/graph bytes replayed with source frontend disabled. New live source frontend is separately gated. All legacy hart pipelines, memory routes and ordering/interrupt cases retained.',calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],runs=len(rows))))
if __name__=='__main__':main()
