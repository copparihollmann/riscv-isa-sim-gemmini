#!/usr/bin/env python3
"""Additive source review of the corrected globally settled prepare boundary."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    cap=ROOT/'build/source-System-global-prepare-component-v1'
    assert sha(cap/'manifest.json')=='a9ae782a65caf556609f7d57d703e706e5007be70ba5dabbb2c0a4d5d4b9496e'
    manifest=json.loads((cap/'manifest.json').read_text());assert manifest['pass'] is True
    checks=0
    for n,d in manifest['artifact_sha256'].items():assert sha(cap/n)==d;checks+=1
    for n,d in manifest['external_input_sha256'].items():assert sha(n)==d;checks+=1
    fixture=ROOT/'timing/shuttle_memory_coupled_fixture_v1.hpp'
    text=fixture.read_text();control=text.split('void evaluate_control(){',1)[1].split('void step(){',1)[0]
    assert 'prepare(' not in control
    assert 'bin=next;if(same&&previous==out)return;' in control
    assert 'evaluate_control();service.prepare();const bool edge=' in text
    peers=[ROOT/'timing/saturn_storefront_system_arena_v3.cpp',ROOT/'timing/saturn_storefront_system_writeback_v3.cpp']
    for p in peers:
        t=p.read_text();evaluate=t.split('void evaluate(){',1)[1].split('void step(){',1)[0]
        assert evaluate.count('service.prepare()')==1
        converged=evaluate.split('if(!changed){',1)[1]
        assert 'f.service.prepare();return;}' in converged
        # Writeback's explicit wrong-write-data negative mutates the held
        # payload here. That fault path is not normal coupled evaluation.
        assert evaluate.index('if(!changed){')<evaluate.index('f.service.prepare();')
        assert 'f.evaluate_control();changed|=old_system!=f.out;' in evaluate
        step=t.split('void step(){',1)[1].split('void startup(){',1)[0]
        assert step.index('evaluate();')<step.index('c.transport->prepare(f.tick)')<step.index('f.system.commit(')<step.index('f.service.commit();')<step.index('c.transport->commit();c.rob.commit();')
        held=step[step.index('f.system.commit('):step.index('c.transport->commit();c.rob.commit();')]
        assert 'evaluate' not in held and 'sample(' not in held
        assert 'c.get("io_vec_store_ack_valid")' in step and 'c.rob.evaluate' in step
        assert 'c.owners.retire(tag)' in step
    old=ROOT/'build/saturn-storefront-System-independent-review-v1/report.json'
    report=dict(schema='iris.source_System_global_prepare_independent_addendum.v1',**{'pass':True},
                prior_finding='inner-ledger-prepare-before-global-convergence',
                finding_resolved_in_new_source=True,verified_source_scope='resident and line-serialized writeback fixtures',
                exact_prepare_boundary='control fixed points settle all peers; prepare backing once, prepare source owners, commit all selected peers from held preedge pins',
                wrong_write_data_control='explicit negative-only payload mutation after convergence; excluded from normal coupled-boundary claim',
                standalone_fixture_step='prepare once after its own complete local convergence',
                ACK_scope='source VMU response drives ordered ROB; TL D alone does not release upstream lease',
                positive_replays_attributed_to_frozen_component_not_rerun=True,digest_checks=checks,
                broader_visibility_policy_restriction_preserved=True,
                limitations=['No full VMU/CPU/native arena-history qualification.',
                             'External idle checkpoint is not RISC-V FENCE/coherent visibility equivalence.',
                             'High-window EXTERNAL_FENCE_REQUIRED remains an intentional scope boundary.',
                             'No hardware, protected timing labels, or model parameter changes.'],
                input_sha256={str(p):sha(p) for p in [Path(__file__),fixture,*peers,cap/'manifest.json',old]})
    out=ROOT/'build/saturn-storefront-System-prepare-independent-v3';out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
