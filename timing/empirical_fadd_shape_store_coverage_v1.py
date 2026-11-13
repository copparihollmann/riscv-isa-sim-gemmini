#!/usr/bin/env python3
"""Audit own-runtime family rule reachability without changing the fitted model."""
import collections
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parameters=ROOT/'calibration/compute-fit-fadd-shape-store-9b2-selected-v2/parameters.json'
    features=ROOT/'build/compute-fit-features-fadd-shape-store-9b2-selected-v2/regions.jsonl'
    params=json.loads(parameters.read_text());rows=[json.loads(s)for s in features.read_text().splitlines()]
    totals=collections.defaultdict(collections.Counter);work=collections.defaultdict(set)
    for row in rows:
        for family,v in row['features'].items():
            key=row['hart'],family;totals[key].update(v)
            if v['instructions']:work[key].add(v['work']/v['instructions'])
    checks=[]
    for rule in params['families']:
        key=rule['hart'],rule['family'];v=totals[key]
        checks.append({**rule,'observed_instruction_count':v.get('instructions',0),'observed_work':v.get('work',0),
            'observed_work_per_instruction_domain':sorted(work[key]),'reached_in_own1008':v.get('instructions',0)>0,
            'unreached_rule_declared_prior':'prior'in rule['scope']})
    if not all(r['reached_in_own1008']or r['unreached_rule_declared_prior']for r in checks):
        raise ValueError('Configured own-fit family has no actual instruction coverage')
    out=ROOT/'build/fadd-shape-store-9b2-runtime-feature-coverage-v1';out.mkdir(exist_ok=False)
    report={'schema':'iris.empirical_runtime_rule_coverage.v1','pass':True,'regions':len(rows),'checks':checks,
        'scalar_fadd_source_feature_counts':{str(h):{f:dict(v)for (hart,f),v in totals.items()if hart==h and f.startswith('scalar.fadd.')}for h in range(3)},
        'all_own_fitted_family_rules_reached':True,'unreached_paths_are_explicit_unqualified_prior_transfers':True,
        'model_or_parameters_changed':False,'global_heldout_timings_consumed':False,'source_image_association_verified':False,
        'full_2pct_certified':False,'input_sha256':{str(p):sha(p)for p in
            (Path(__file__).resolve(),parameters,features,ROOT/'build/fadd-shape-store-frozen-9b2a9053/manifest.json')}}
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'rules':len(checks),'own_reached':sum(r['reached_in_own1008']for r in checks),
        'unreached_explicit_prior':sum(not r['reached_in_own1008']for r in checks),'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':main()
