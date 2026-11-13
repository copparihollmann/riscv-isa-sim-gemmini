#!/usr/bin/env python3
"""Require complete graph bytes to equal the prior live-value epoch."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    pairs=[('directed-v2','directed-v1'),('memory-v2','memory-v1'),('initialized-live8-v2','live8-v1'),('uart-v2','uart-v1'),('zephyr-scalar-v2','zephyr-scalar-v1'),('zephyr-mixed-v2','zephyr-mixed-v1')]
    rows=[];inputs={str(Path(__file__).resolve()):sha(__file__)}
    for old,new in pairs:
        before=ROOT/'build'/('frontend-values-native-'+old);after=ROOT/'build'/('frontend-bounded-native-'+new)
        for p in sorted(before.glob('*.graph.json'))+([before/'graph.json'] if (before/'graph.json').exists() else []):
            q=after/p.name
            if not q.is_file() or sha(p)!=sha(q):raise ValueError('bounded storage changed complete model graph: '+str(q))
            rows.append(dict(parent=str(p),new=str(q),sha256=sha(p),byte_identical=True))
        for folder in (before,after):inputs[str(folder/'results.json')]=sha(folder/'results.json')
    if len(rows)!=35:raise ValueError('35 complete-graph controls required')
    receipt=dict(schema='iris.frontend.bounded_equivalence.v1',status='passed_byte_identical_live_graph_equivalence',graphs=len(rows),rows=rows,input_sha256=inputs,
                 scope='Complete graph bytes across directed/memory/live/UART/realZephyr; includes cycles and private values. Host elapsed times are not compared.',calibrated=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status=receipt['status'],graphs=len(rows))))
if __name__=='__main__':main()
