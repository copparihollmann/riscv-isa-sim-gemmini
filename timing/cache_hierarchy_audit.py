#!/usr/bin/env python3
"""Bind cache integration facts to exact saved RTL and explicitly scoped source pins."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOCAL=Path('/scratch/eygao/iris-cy')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=ROOT/'build/cache-hierarchy-source-v1');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-audit-v1');a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh audit output required')
    out.mkdir();j=json.loads((source/'extraction.json').read_text());manifest=json.loads((ROOT/'hardware/manifest.json').read_text());records={}
    snapshots={
        'shuttle-cache':'generators/shuttle/src/main/scala/dmem/DCache.scala',
        'shuttle-mshr':'generators/shuttle/src/main/scala/dmem/MSHR.scala',
        'rocket-cache':'generators/rocket-chip/src/main/scala/rocket/DCache.scala',
        'rocket-tlb':'generators/rocket-chip/src/main/scala/rocket/TLB.scala',
        'rocket-memory-commands':'generators/rocket-chip/src/main/scala/rocket/Consts.scala',
        'inclusive-parameters':'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/Parameters.scala',
        'inclusive-mshr':'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/MSHR.scala',
        'inclusive-directory':'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/Directory.scala',
        'inclusive-source-b':'generators/rocket-chip-inclusive-cache/design/craft/inclusivecache/src/SourceB.scala',
    }
    for name,relative in snapshots.items():
        path=LOCAL/relative
        if not path.exists():
            if name=='shuttle-mshr':path=LOCAL/'generators/shuttle/src/main/scala/dmem/MSHRs.scala'
            if not path.exists():raise ValueError('required source absent '+str(path))
        destination=out/(name+'.scala');destination.write_bytes(path.read_bytes());records[name]={'path':str(path),'sha256':sha(path),'snapshot':destination.name,'saved_FIR_generated_from_these_working_tree_bytes_verified':False}
    def cite(module,needle):
        path=source/'rtl'/(module+'.sv');lines=path.read_text().splitlines();hits=[n+1 for n,line in enumerate(lines)if needle in line]
        if not hits:raise ValueError('missing source fact '+module+' '+needle)
        return {'path':str(path),'sha256':sha(path),'matching_lines':hits,'expression':needle}
    facts=[
        {'id':'shuttle-external-S1-physical-address','value':35,'evidence':cite('ShuttleDCache','input  [34:0] io_s1_paddr')},
        {'id':'shuttle-TL-data-width','value':64,'evidence':cite('ShuttleDCache','output [63:0] auto_out_a_bits_data')},
        {'id':'rocket-TL-cache-data-width','value':256,'evidence':cite('DCache','output [255:0] auto_out_a_bits_data')},
        {'id':'rocket-Hella-data-width','value':256,'evidence':cite('DCache','io_cpu_s1_data_data')},
        {'id':'rocket-passthrough-supervisor-PMP','value':'PTW response or passthrough forces mpu privilege1','evidence':cite('DCache','tlb_mpu_priv = io_ptw_resp_valid | s1_tlb_req_passthrough ? 3\'h1')},
        {'id':'l2-three-coherent-client-source-domains','value':['0x2e0..0x2e3','0x2a0..0x2a3','0x240'],'evidence':cite('MSHR','req_clientBit = {request_source == 10\'h240')},
        {'id':'l2-probe-client-addressing','value':'configured source0x2e0/0x2a0/0x240; individual source IDs preserved','evidence':cite('SourceB','io_enq_bits_source  ((_GEN[0] ? 10\'h2E0')},
        {'id':'l2-reset-directory-sweep','value':'wipeCount gates reads; data storage is not claimed resetzero','evidence':cite('Directory','wipeCount')},
    ]
    receipt={'schema':'iris.cache_hierarchy_source_audit.v1','extraction_sha256':sha(source/'extraction.json'),'source_FIR_sha256':j['source_fir_sha256'],'facts':facts,'local_source_snapshots':records,
        'declared_local_repository_pins':{k:v['commit']for k,v in manifest['repositories'].items()if k in ['chipyard','saturn','rocket-chip','shuttle']},
        'pin_to_saved_FIR_build_association_verified':False,'working_tree_source_state':'exact named file snapshots; no claim that current source generated saved FIR',
        'external_unknowns':['tile arbiter/crossbar/buffer/source-ID/width/CDC composition','serial link controller/clock composition','external DRAM/FASED runtime settings','full closed-loop hart/interrupt/PTW interactions'],
        'source_geometry_reference':{'path':'hardware/memory-paths.json','sha256':sha(ROOT/'hardware/memory-paths.json'),'separate_firesim_elaboration_association_verified':False},
        'no_fixed_memory_latencies_installed':True,'hardware_contacted':False,'loaded_image_verified':False,'full_rtl_certified':False,'timing_certified':False,
        'input_sha256':{str(Path(__file__)):sha(Path(__file__)),str(ROOT/'hardware/manifest.json'):sha(ROOT/'hardware/manifest.json')}}
    (out/'audit.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'facts':len(facts),'source_snapshots':len(records),'audit_sha256':sha(out/'audit.json')}))
if __name__=='__main__':main()
