#!/usr/bin/env python3
"""Read-only source/owner review of frozen source arena/writeback fixtures."""
from pathlib import Path
import hashlib,json
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/saturn-storefront-System-independent-review-v1';o.mkdir();caps=[R/'build/saturn-storefront-System-arena-component-v1',R/'build/saturn-storefront-System-writeback-component-v1'];pins=['83c8417b98d7174d523ac921bdd758ab0733447b8b1e62656cfd548fc9650e8f','eb5a9dbf453050ac063ba1618fcbbe9d347a55121d3395bc8d4676eea0703a0a'];checked=0
 for c,pin in zip(caps,pins):
  assert sha(c/'manifest.json')==pin;m=json.loads((c/'manifest.json').read_text());assert m['pass']is True
  for n,h in m['artifact_sha256'].items():assert sha(c/n)==h,n;checked+=1
  for n,h in m['external_input_sha256'].items():assert sha(n)==h,n;checked+=1
 base=R/'timing/shuttle_memory_system_write_v1.cpp';arena=R/'timing/saturn_storefront_system_arena_v2.cpp';writes=R/'timing/saturn_storefront_system_writeback_v2.cpp';service=R/'timing/fased_backing_service_v2.hpp';transport=R/'timing/saturn_storefront_v1.cpp';boundary=R/'timing/rvv_memory_fabric_boundary_v1.hpp';bt=base.read_text()
 assert 'bin=next;if(same&&previous==out){service.prepare();return;}'in bt
 for p in(arena,writes):
  t=p.read_text();assert 'f.evaluate();changed|=old_system!=f.out;'in t and 'for(unsigned iteration=0;iteration<32;++iteration)'in t
  assert t.index('c.transport->prepare(f.tick)')<t.index('f.system.commit(')<t.index('f.service.commit();')<t.index('c.transport->commit();c.rob.commit();')
  assert 'c.get("io_vec_store_ack_valid")'in t and 'c.rob.evaluate' in t
  assert t.index('if(e.phase==T::Phase::TileD)')<t.index('if(e.phase==T::Phase::VMUResponse)')<t.index('if(c.rob_out.deq_fire)')
  assert 'c.metadata[tag].reset();c.reservation_order.pop_front();'in t and 'c.owners.retire(tag)'in t
 assert 'prepared_.reset()'in service.read_text() and 'auto next=ledger_'in service.read_text() and 'ledger_=std::move(*prepared_)'in service.read_text()
 finding=dict(id='inner-ledger-prepare-before-global-convergence',source=str(base),line=66,callers=[str(arena),str(writes)],fact='Nested Fixture::evaluate calls ServiceV2::prepare after only the inner System/LP fixed point, while Arena::evaluate may still change storefront A/D pins in its outer loop.',observed_wrong_committed_owner=False,actual_passing_fixture_bytes_not_discredited=True,consequence='Staged ledger validation can false-refuse a transient unaccepted AR/AW/W state; exactly-once global prepare contract is not established.',classification='integration/false-refusal boundary; not evidence of early committed memory publication',required_new_epoch='Separate inner control evaluation from prepare; prepare ServiceV2 exactly once after global storefront/System/backing convergence, then commit all peers from held pins.',frozen_sources_not_modified=True)
 report=dict(schema='iris.source_storefront_System_independent_review.v1',status='bounded-positive-owner-path-reviewed-with-global-prepare-finding',artifact_and_external_digest_checks=checked,findings=[finding],positive_source_facts=['real typed VMU/A/D/VMUresponse owner linkage','source preedge VMU ACK drives same-edge ROB completion; D alone does not free ordered ownership','generation metadata survives circular tag wrap and ordered metadata clearing','no evaluate between first and last selected peer commits','explicit physical backing + actual source TL preparation; no flat CPU/cache seed','native System/VMU/arena product remains unavailable'],limitations=['not full AddrGen/SIQ/SIFQ/VRF or native boot','external idle fence checkpoint is not architectural FENCE/coherent earliest visibility proof','arena16resident-lines scope has no AW; separate writeback scope has32 AW/256 W/32 B','no hardware or protected timing labels','this is a read-only source review, no new fixture replay'],input_sha256={str(p):sha(p)for p in[Path(__file__),base,arena,writes,service,transport,boundary,*[c/'manifest.json'for c in caps]]});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
