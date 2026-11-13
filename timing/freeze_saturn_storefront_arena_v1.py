#!/usr/bin/env python3
"""Freeze conditional source vector transport/System/arena integration."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/saturn-storefront-System-arena-component-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir();proof=ROOT/'build/saturn-storefront-System-arena-check-v2/report.json';j=json.loads(proof.read_text());assert j['pass']is True
    inputs={str(proof):sha(proof)}
    for mapping in [j['input_sha256'],j['compiled_dependency_sha256']]:
        for p,h in mapping.items():assert sha(p)==h;inputs[p]=h
    for p,h in j['output_sha256'].items():assert sha(p)==h
    parents={}
    for name in ['fased-write-backing-component-v1','saturn-storefront-typed-component-v1']:
        p=ROOT/'build'/name/'manifest.json';m=json.loads(p.read_text());assert m['pass']is True
        for path,h in m['artifact_sha256'].items():assert sha(p.parent/path)==h
        parents[name]=dict(path=str(p),sha256=sha(p));inputs[str(p)]=sha(p)
    for name in ['saturn_storefront_system_arena_v2.cpp','check_saturn_storefront_system_arena_v2.py','freeze_saturn_storefront_arena_v1.py']:
        p=ROOT/'timing'/name;q=OUT/'src/timing'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[str(p)]=sha(p)
    shutil.copytree(proof.parent,OUT/'proof',ignore=shutil.ignore_patterns('check'))
    records=[json.loads((proof.parent/name).read_text())for name in ['positive.stdout','seed17.stdout']]
    assert records[0]==records[1]
    contract=dict(schema='iris.compute_storefront_System_arena_contract.v1',
       domains='Two physical512-byte DRAM arenas at0x80010000 and0x80011000, plus explicit immutable backing lines; all outside addresses/unknown backing bytes refuse.',
       cache_preparation='Only actual typed source TL prep stores enter coherent System. No CPU/flat-RAM write seeds any cache. Initial backing bytes are explicit external-fixture initial conditions, not a recovered native history.',
       producer='External conditional16B request stimulus, source-qualified circular ROB control and bounded2-entry client queue. It is not full AddrGen/SIQ/SIFQ/VRF or source Core.',
       ownership='Circular reserve creates immutable tag/generation owner before the client queue. Actual VMU request fire precedes source A/D/VMU-response. Actual preedge VMU ACK drives source ROB completion and ordered release on that edge. No D alone frees ordered ownership.',
       port_join='Model auto_atl_out A/d_ready→System shuttle{0,1}_tile _vector_unit_auto_atl_out_*. System canonical _tcm_adjuster_2_auto_in_a_ready/d_*→same Model Aready/D. Exact widths/ID mapping from frozen source, no scalar-port shortcut.',
       fixed_point='All storefronts, System and Service control-evaluate/sample to global fixed point; prepare typed owners only once settled; commit all selected peers from held preedge pins without intervening evaluate.',
       clock='Explicit1GHz master: both compute/uncore every2ticks, Bringup/FASED everytick, Serial10; receipt master_tick==2*source_edge for this phase0 fixture only.',
       checkpoint='After all source stores and ordered owners drain,32quiescent masterticks+idle backing permit explicit external checkpoint. This is not a modeled architectural FENCE or proof of earliest coherent visibility.',
       source_path_included='Actual TLSplit/WidthWidget/TLBuffer, tile/NoC/L2, MBUS/SerialTL/Bringup/FASED LP and explicit functional backing.',
       not_exercised='No outer AW/W/B in this resident16-line test. Separate backing capsule proves source scalar-induced dirty eviction writes; vector-induced eviction remains a next test.',
       native_admission='Still unavailable: must prove actual immutable initial bytes and modeled preparation/history, exclude or model all CPU/peer aliases, preserve upstream fullVMU/VRF leases and ordered ownership, and define full host-token/coherent visibility scope. Capturing a flat RAM snapshot does not supply that history.')
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    report=dict(schema='iris.compute_storefront_System_arena_component.v1',**{'pass':True},parents=parents,proof=dict(path=str(proof),sha256=sha(proof)),seeds=[1,17],per_seed_actual_source_results=records[0],negative_controls=j['negative_controls'],
       actual_vector_port_and_SourceSystem_used=True,initial_bytes_declared_before_clock=True,coherent_cache_initialization_only_actual_TL=True,
       exact_circular_ROB_component_used=True,conditional_client_queue_not_full_VMU=True,ordered_SIFQ_release_surrogate_not_full_SIFQ=True,
       source_LP_parameters_are_explicit_fixture_inputs=True,observed_parameters_admitted_as_CPU_default=False,
       vector_induced_outer_writes_exercised=False,native_ELF_or_CPU_boot_qualified=False,architectural_FENCE_qualified=False,
       hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,old_native_provider_default_changed=False,source_image_association_verified=False,timing_certified=False,input_sha256=inputs)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');artifact={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()};manifest=dict(schema='iris.compute_storefront_System_arena_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),artifact_sha256=artifact,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifact))))
if __name__=='__main__':main()
