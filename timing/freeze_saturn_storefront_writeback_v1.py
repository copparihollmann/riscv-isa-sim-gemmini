#!/usr/bin/env python3
"""Freeze vector-induced source dirty eviction/backing/reload proof."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/saturn-storefront-System-writeback-component-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir();proof=ROOT/'build/saturn-storefront-System-writeback-check-v2/report.json';j=json.loads(proof.read_text());assert j['pass']is True;inputs={str(proof):sha(proof)}
    for mapping in [j['input_sha256'],j['compiled_dependency_sha256']]:
        for p,h in mapping.items():assert sha(p)==h;inputs[p]=h
    for p,h in j['output_sha256'].items():assert sha(p)==h
    parents={}
    for name in ['fased-write-backing-component-v1','saturn-storefront-typed-component-v1','saturn-storefront-System-arena-component-v1']:
        p=ROOT/'build'/name/'manifest.json';m=json.loads(p.read_text());assert m['pass']is True
        for path,h in m['artifact_sha256'].items():assert sha(p.parent/path)==h
        parents[name]=dict(path=str(p),sha256=sha(p));inputs[str(p)]=sha(p)
    for name in ['saturn_storefront_system_writeback_v2.cpp','check_saturn_storefront_system_writeback_v2.py','saturn_storefront_system_writeback_v1.cpp','check_saturn_storefront_system_writeback_v1.py','saturn_storefront_system_writeback_diagnostic_v1.cpp','check_saturn_storefront_system_writeback_diagnostic_v1.py','freeze_saturn_storefront_writeback_v1.py']:
        p=ROOT/'timing'/name;q=OUT/'src/timing'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[str(p)]=sha(p)
    shutil.copytree(proof.parent,OUT/'proof',ignore=shutil.ignore_patterns('check'))
    failures=[]
    for name in ['saturn-storefront-System-writeback-check-v1','saturn-storefront-System-writeback-diagnostic-v1']:
        p=ROOT/'build'/name;q=OUT/'preserved'/name;shutil.copytree(p,q,ignore=shutil.ignore_patterns('check','*.d'));report=json.loads((p/'report.json').read_text());assert report['pass']is False;inputs[str(p/'report.json')]=sha(p/'report.json');failures.append(dict(path=str(p/'report.json'),sha256=sha(p/'report.json'),status='preserved unqualified high-window client; explicit external-fence policy refusal'))
    records=[json.loads((proof.parent/name).read_text())for name in ['positive.stdout','seed17.stdout']];assert records[0]==records[1]
    assert records[0]['AW']==32 and records[0]['W']==256 and records[0]['B']==32
    contract=dict(schema='iris.compute_storefront_System_writeback_contract.v1',
       stimulus='Two compute-hart source storefronts.16conflict lines/hart at0x80020000+h*4096+n*128KiB; each line written by four actual16B source PutPartial requests. Exactly one4fragment line group is pending perhart; ordered completion precedes next group.',
       missing_broader_scope='The earlier16-reservation client reread a written-back line during prep and hit the frozen EXTERNAL_FENCE_REQUIRED guard. It remains unqualified; this proof does not relax or resolve that visibility envelope.',
       initial_memory='Every prep/clean line has explicitly defined initial external backing bytes before clocks. No CPU writes or private state seeding. Fifteen subsequent source Get conflicts/hart evict remaining dirty ways.',
       writeback_proof='All32dirty lines must produce actual32AW/256W/32B. Every2048prep byte is checked in B-published external backing before checkpoint/reload; a deliberately corrupted W payload refuses.',
       reload_proof='After source owners/ordered queues drain and32quiet masterticks with idle backing, explicit external checkpoint permits actual own+peer source readbacks;4096data bytes checked plus480clean-conflict bytes.',
       byte_pattern='Distinct per-line,per-hart pattern with varied within-line bytes; every strobed byte independently checked. Architectural request16B versus physicalATL256 versus outerAXI64 remain separate units.',
       clock='Unchanged source1GHz master: compute/uncore2,Bringup/FASED1,Serial10. Phase0 receipt equality checked. Source LP30/30/16/16 are explicit caller inputs, not CPUcycle latency or admitted hardware defaults.',
       actual_path='Typed source TLSplit/width/buffer→actual Systemv6 ATL/NoC/L2→actual MBUS/SerialTL/Bringup→unchanged source LP plus finite ideal-host backing. No source-ready/state replay, arbitrary ACK timing or scalar shortcut.',
       producer_scope='External physical client with source-qualified circular ROB+conditional bounded request queue; not full AddrGen/SIQ/SIFQ/VRF/Core, not an executed ELF.',
       visibility_scope='Explicit postdrain external checkpoint, not architectural FENCE or earliest coherent visibility. Full FASED functional ingress/egress/host tokens remain outside the finite backing.',
       native_scope='Production backend remains unavailable until real initial arena bytes, actual preparation/history, CPU/peer alias isolation and conservative publication/IRQ/context semantics are proved in a NEW native epoch.')
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    report=dict(schema='iris.compute_storefront_System_writeback_component.v1',**{'pass':True},parents=parents,proof=dict(path=str(proof),sha256=sha(proof)),seeds=[1,17],per_seed_actual_source_results=records[0],all_prepared_backing_bytes_checked_per_seed=2048,negative_controls=j['negative_controls'],preserved_failures=failures,
       source_RTL_control_changed=False,frozen_visibility_policy_relaxed=False,latency_parameters_changed=False,client_line_serialization_explicit=True,
       actual_vector_induced_dirty_eviction_AW_W_B_and_reload=True,all_data_from_declared_initial_bytes_or_actual_source_writes=True,private_cache_or_flat_CPU_seeding=False,
       native_ELF_or_CPU_boot_qualified=False,architectural_FENCE_qualified=False,production_native_backend_available=False,
       hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,old_native_provider_default_changed=False,source_image_association_verified=False,timing_certified=False,input_sha256=inputs)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');artifacts={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()};manifest=dict(schema='iris.compute_storefront_System_writeback_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),artifact_sha256=artifacts,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifacts))))
if __name__=='__main__':main()
