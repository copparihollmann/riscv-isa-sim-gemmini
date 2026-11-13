#!/usr/bin/env python3
"""Validate every buffered fitting identity against its independent corpus."""
import argparse
import collections
import json
from pathlib import Path


def expected_rows(corpus):
    if (corpus.get('schema')!='iris.buffered_fitting_corpus.v1'
            or corpus.get('split_id')!='iris-buffered-fit-campaign-v1'):
        raise ValueError('Wrong buffered fitting corpus')
    cases=corpus['cases']
    if len({c['case_id'] for c in cases})!=len(cases): raise ValueError('Duplicate corpus case')
    expected={(c['case_id'],h):(c,c['expected_checksums'][h]) for c in cases for h in range(3) if c['mask']&(1<<h)}
    if len(expected)!=corpus['expected_region_count']: raise ValueError('Wrong corpus region count')
    return expected


def check_rows(rows,corpus):
    expected=expected_rows(corpus);seen={}
    for row in rows:
        key=(row['case_id'],row['hart'])
        if key not in expected or key in seen: raise ValueError('Unexpected/duplicate buffered region '+repr(key))
        case,golden=expected[key]
        for field in ('parent_case_id','trial_id','suite'):
            if row.get(field)!=case[field]: raise ValueError('Wrong buffered '+field)
        for field in ('hart','trial_id','start_cycle','end_cycle','instret_delta','checksum','expected_checksum'):
            if type(row.get(field))is not int or not 0<=row[field]<(1<<64): raise ValueError('Invalid buffered '+field)
        if (row.get('pass')is not True or row['checksum']!=golden or row['expected_checksum']!=golden
                or row.get('region')!='kernel' or row['end_cycle']<=row['start_cycle']):
            raise ValueError('Independent checksum/measurement failure '+repr(key))
        seen[key]=row
    if set(seen)!=set(expected): raise ValueError('Missing buffered regions '+str(len(set(expected)-set(seen))))
    return {'functional_checks_passed':True,'cases':len(corpus['cases']),'regions':len(seen),
        'trials':corpus['trials'],'all_independent_checksums_passed':True,
        'all_parent_trial_hart_ids_unique':True,'per_hart_regions':dict(collections.Counter(h for _,h in seen)),
        'per_suite_cases':dict(collections.Counter(c['suite'] for c in corpus['cases'])),
        'timing_certified':False,'calibration_usable':False}


def validate(text,corpus):
    rows=[];done=[]
    for line in text.splitlines():
        if line.startswith(('IRIS_FATAL','IRIS_CAMPAIGN_FAILED')): raise ValueError(line)
        if line.startswith('IRIS_REGION '): rows.append(json.loads(line.split(' ',1)[1]))
        if line.startswith('IRIS_BATCH_DONE '): done.append(json.loads(line.split(' ',1)[1]))
        if line.startswith('IRIS_CAMPAIGN_PHASE '): raise ValueError('This new buffered workload has no per-case phase UART')
    result=check_rows(rows,corpus)
    if done!=[{'failed':0,'cases':len(corpus['cases']),'regions':len(rows),'trials':corpus['trials']}]:
        raise ValueError('Missing/duplicate/wrong buffered completion')
    return result


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('console',type=Path);p.add_argument('--corpus',type=Path,required=True)
    a=p.parse_args();print(json.dumps(validate(a.console.read_text(),json.loads(a.corpus.read_text())),indent=2))


if __name__=='__main__': main()
