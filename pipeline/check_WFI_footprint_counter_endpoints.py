#!/usr/bin/env python3
"""Join genuine program counter endpoints to exact compiled CSR instructions."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(rows,prefix):
    index={}
    for p in prefix:
        if p['csr']==0xb00:index.setdefault((p['hart'],p['value']),[]).append(p)
    joined=[]
    for r in rows:
        pair=[]
        for key,pc,raw,dst in [('start_cycle',0x800006c4,0xb0002873,16),('end_cycle',0x800006f8,0xb0002673,12)]:
            matches=[p for p in index.get((r['hart'],r[key]),[])if p['pc']==pc]
            if len(matches)!=1:raise ValueError('Unique actual hart/value/PC CSR endpoint required')
            p=matches[0]
            if p['raw']!=raw or p['destination']!=dst or p['result_discarded']is not False:raise ValueError('Actual instruction encoding/destination mismatch')
            pair.append(p)
        if pair[0]['sequence']>=pair[1]['sequence']or pair[0]['read_cycle']>=pair[1]['read_cycle']:raise ValueError('Reversed actual counter endpoints')
        joined.append({'hart':r['hart'],'case_id':r['case_id'],'start_sequence':pair[0]['sequence'],'end_sequence':pair[1]['sequence'],'start_global_read_cycle':pair[0]['read_cycle'],'end_global_read_cycle':pair[1]['read_cycle']})
    if len(joined)!=360:raise ValueError('All360 actual program regions required')
    return joined
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args();out=a.run.resolve();q=json.loads((out/'qualification.json').read_text())
    if q['pass']is not True:raise ValueError('Completed independently qualified normal run required')
    rows=[json.loads(l[len('IRIS_REGION '):])for l in(out/'stdout').read_text().splitlines()if l.startswith('IRIS_REGION ')];prefix=[json.loads(l)for l in(out/'features.jsonl').read_text().splitlines()];joins=check(rows,prefix);mutants=[]
    for field,value in [('pc',0x800006c6),('raw',0xb0002872),('hart',17)]:
        changed=copy.deepcopy(prefix);i=next(i for i,x in enumerate(changed)if x['csr']==0xb00 and x['pc']==0x800006c4);changed[i][field]=value
        try:check(rows,changed)
        except ValueError:mutants.append(field)
        else:raise ValueError('Changed endpoint admitted')
    report={'schema':'iris.WFI_footprint_actual_CSR_endpoint_qualification.v1','pass':True,'regions':360,'actual_counter_endpoints':720,'prefix_records':len(prefix),'counter_source':'program mcycle + genuine get_csr prefix, before current retirement','joins':joins,'corruption_refusals':mutants,'new_exact_reference_required':True,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in [Path(__file__).resolve(),out/'qualification.json',out/'stdout',out/'features.jsonl']}}
    (out/'CSR-endpoint-qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'regions':360,'endpoints':720,'sha256':sha(out/'CSR-endpoint-qualification.json')}))
if __name__=='__main__':main()
