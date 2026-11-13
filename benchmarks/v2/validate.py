#!/usr/bin/env python3
"""Validate complete v2 console coverage against independent host-side checksums."""
import argparse
import json
from pathlib import Path

def validate(text,corpus):
    if corpus.get('schema_version')!=2: raise ValueError('v2 corpus required')
    expected={(c['case_id'],h):c['expected_checksums'][h] for c in corpus['cases'] for h in range(3) if c['mask']&(1<<h)}
    seen=set();done=[]
    for line in text.splitlines():
        if line.startswith('IRIS_FATAL'): raise ValueError(line)
        if line.startswith('IRIS_BATCH_DONE '): done.append(json.loads(line.split(' ',1)[1]))
        if not line.startswith('IRIS_REGION '): continue
        row=json.loads(line.split(' ',1)[1])
        if type(row.get('hart')) is not int: raise ValueError('invalid hart')
        key=(row['case_id'],row['hart'])
        if key not in expected or key in seen: raise ValueError('unexpected/duplicate case '+repr(key))
        for field in ('start_cycle','end_cycle','instret_delta','checksum','expected_checksum'):
            if type(row.get(field)) is not int or not 0<=row[field]<(1<<64): raise ValueError('invalid '+field)
        if row['end_cycle']<=row['start_cycle'] or row.get('region')!='kernel': raise ValueError('invalid region')
        if row.get('pass') is not True or row['checksum']!=expected[key] or row['expected_checksum']!=expected[key]: raise ValueError('golden checksum mismatch '+repr(key))
        seen.add(key)
    if seen!=set(expected): raise ValueError('missing regions '+repr(sorted(set(expected)-seen)))
    if len(done)!=1 or type(done[0].get('failed')) is not int or done[0]['failed']!=0: raise ValueError('invalid completion')
    return {'cases':len(corpus['cases']),'regions':len(seen),'functional_checks_passed':True,'timing_certified':False,
            'hart_subsets_tested':sorted({c['mask'] for c in corpus['cases']})}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('console',type=Path)
    parser.add_argument('--corpus',type=Path,default=Path(__file__).resolve().parent/'corpus.json')
    args=parser.parse_args()
    try: print(json.dumps(validate(args.console.read_text(),json.loads(args.corpus.read_text())),indent=2))
    except (ValueError,TypeError,KeyError) as error: raise SystemExit(str(error))

if __name__=='__main__': main()
