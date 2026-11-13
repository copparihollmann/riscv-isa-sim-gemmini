#!/usr/bin/env python3
"""Join actual private result values to the independent guest ALU corpus."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from pipeline.alu_corpus import evaluate,REGISTERS
from spike.run_functional import symbols

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=a.run.resolve();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    report=json.loads((run/'results.json').read_text())
    if report['status']!='passed_directed_integration' or not report['private_forwarded_values']:raise ValueError('private pipeline directed gate missing')
    graph_path=run/'alu-pure.graph.json';graph=json.loads(graph_path.read_text());program=json.loads((run/'alu-program.json').read_text());sym=symbols(run/'alu-corpus.elf');start,end=sym['alu_corpus_begin'],sym['alu_corpus_end']
    registers={int(k):v for k,v in program['initial_registers'].items()};registers[0]=0;expected=[]
    for index,op in enumerate(program['instructions']):
        values=evaluate(dict(initial_registers=registers,instructions=[op]),start+4*index)
        registers.update(zip(REGISTERS,values));expected.append(registers[op['rd']] if op['rd'] else None)
    events={row['id']:row for row in graph['events']};findings=[]
    all_rows=graph['shuttle_pipeline']['instructions']+graph['rocket_pipeline']['instructions']
    for hart in (0,1,2):
        rows=[row for row in all_rows if row['hart']==hart and start<=row['pc']<end]
        if len(rows)!=len(expected):raise ValueError('actual per-hart corpus incomplete')
        compared=0
        for index,(row,want) in enumerate(zip(rows,expected)):
            if row['raw']!=program['instructions'][index]['word'] or not row['private_value_ready']:raise ValueError('private actual instruction/value readiness mismatch')
            if want is not None:
                if row['private_value']!=want:raise ValueError('private value differs from independent instruction oracle')
                compared+=1
            ready=events[row['result_node']]['end'];retire=events[row['COM_node'] if hart<2 else row['WB_node']]['end']
            if ready>=retire:raise ValueError('pure ALU private values were computed at/after architectural retirement')
        findings.append(dict(hart=hart,actual_instructions=len(rows),independently_compared_values=compared,all_result_ready_before_architectural_commit=True))
    paths=[Path(__file__).resolve(),ROOT/'pipeline/alu_corpus.py',ROOT/'spike/run_functional.py',run/'results.json',graph_path,run/'alu-program.json',run/'alu-corpus.elf']
    receipt=dict(schema='iris.frontend.native_forwarded_values.v1',status='passed_live_private_results_against_integer_oracle',binary_sha256=report['binary_sha256'],uart_sha256=report['uart_sha256'],findings=findings,
                 source_sha256={str(p):sha(p) for p in paths},actual_guest_state_writes_at_commit=True,claim_basis='Native COM validation plus unchanged independent guest goldens; private value timestamps are actual completed model result nodes.',
                 source_frontend_integrated=False,calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(dict(status=receipt['status'],values=sum(x['independently_compared_values'] for x in findings))))
if __name__=='__main__':main()
