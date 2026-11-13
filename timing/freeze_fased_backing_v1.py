#!/usr/bin/env python3
"""Freeze finite source-LP backing proof, preserving all existing SDKs."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/fased-write-backing-component-v1'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def main():
    OUT.mkdir()
    reports=[ROOT/f'build/{x}/report.json'for x in ['fased-write-backing-plan-v1','fased-backing-ledger-closure-v4','fased-backing-service-check-v5','shuttle-write-backing-check-v5','shuttle-write-backing-guards-v1']]
    inputs={str(p):sha(p)for p in reports};proofs=[]
    for p in reports:
        j=json.loads(p.read_text());assert j['pass'] is True
        for name,digest in j['input_sha256'].items():
            # Earlier bound source plan intentionally names no in-progress
            # implementation, so all its inputs remain byte-identical too.
            assert sha(name)==digest,(name,digest)
            inputs[name]=digest
        for name,digest in j.get('compiled_dependency_sha256',{}).items():assert sha(name)==digest;inputs[name]=digest
        for name,digest in j.get('output_sha256',{}).items():assert sha(name)==digest
        proofs.append(dict(path=str(p),sha256=sha(p),schema=j['schema']))
    sources=[ROOT/'timing'/n for n in ['fased_backing_ledger_v1.hpp','fased_backing_service_v1.hpp','fased_backing_service_v2.hpp','fased_backing_ledger_v1_check.cpp','fased_backing_service_v1_check.cpp','fased_backing_service_v2_check.cpp','check_fased_backing_v1.py','check_fased_backing_v2.py','shuttle_memory_system_write_v1.cpp','check_shuttle_write_backing_v1.py','shuttle_write_backing_guards_v1.cpp','check_shuttle_write_backing_guards_v1.py','freeze_fased_backing_v1.py']]
    for p in sources:inputs[str(p)]=sha(p)
    rtl=ROOT/'build/serial-memory-native-v4/rtl';fased=ROOT/'build/fased-service-source-v2/rtl';facts=[]
    def fact(name,value,anchors):
        citations=[]
        for p,needle in anchors:
            lines=p.read_text().splitlines();found=[i+1 for i,line in enumerate(lines)if needle in line];assert found,(p,needle)
            inputs[str(p)]=sha(p);citations.append(dict(path=str(p),line=found[0],source=needle))
        facts.append(dict(name=name,value=value,citations=citations))
    fact('physical_AXI_cut','AW/AR addresses are33bits; this finite ledger indexes that external physical address directly. It does not infer a guestPA-to-hostallocation mapping.',[(rtl/'IrisSerialMemoryPath.sv','output [32:0] fased_axi4_mem_0_bits_aw_bits_addr'),(rtl/'IrisSerialMemoryPath.sv','output [32:0] fased_axi4_mem_0_bits_ar_bits_addr')])
    fact('source_AXI_address_forwarding','Exact source TLToAXI FIFO address flows through UserYanker and ChipTop unchanged at these named boundaries; no hostbase subtraction is implemented by this adapter.',[(rtl/'TLToAXI4.sv','assign auto_out_aw_bits_addr = queue_arw_deq_q_io_deq_bits_addr;'),(rtl/'TLToAXI4.sv','assign auto_out_ar_bits_addr = queue_arw_deq_q_io_deq_bits_addr;'),(rtl/'AXI4UserYanker.sv','assign auto_out_aw_bits_addr = auto_in_aw_bits_addr;'),(rtl/'AXI4UserYanker.sv','assign auto_out_ar_bits_addr = auto_in_ar_bits_addr;'),(rtl/'ChipTop_1.sv','assign axi4_mem_0_bits_aw_bits_addr = system_mem_axi4_0_aw_bits_addr;'),(rtl/'ChipTop_1.sv','assign axi4_mem_0_bits_ar_bits_addr = system_mem_axi4_0_ar_bits_addr;')])
    fact('FASED_ingress_address_context','Archived full FASED ingress retains33-bit addresses through its FIFO. That does not qualify omitted hostmemory/token/ingress behavior as equivalent to this finite backing.',[(fased/'IngressModule.sv','input  [32:0] io_nastiInputs_hBits_aw_bits_addr'),(fased/'IngressModule.sv','assign awQueue_io_enq_bits_addr = io_nastiInputs_hBits_aw_bits_addr;'),(fased/'IngressModule.sv','assign io_nastiOutputs_aw_bits_addr = awQueue_io_deq_bits_addr;'),(fased/'FASEDMemoryTimingModel.sv','assign auto_to_host_dram_out_aw_bits_addr = ingress_io_nastiOutputs_aw_bits_addr;')])
    contract=dict(schema='iris.FASED_write_backing_contract.v1',component='finite ideal-host external backing',
      headers=['sdk/fased_backing_ledger_v1.hpp','sdk/fased_backing_service_v2.hpp'],namespace='iris::fased_backing',class_name='ServiceV2',
      required_upstream_SDK='build/serial-memory-context-sdk-v2/fased/sdk',source_LP_identity='1d1d497a614cda9e0076368589246bceaeb2cb5dcc20c82d951c6f2566257f85',source_System_identity='453fad48afb9a1c9172c57969d50a9aae6a9654df30cb663d3fa0250f68e791b',
      constructor='ServiceV2(explicit iris::fased::Parameters,unsigned seed,explicit source args,vector<Domain>,Visibility::ExternalFencedDisjoint)',
      phase=['initialize explicit bytes+per-bit knownness before any evaluate','evaluate_control(Inputs) and sample() repeatedly until global fixed point','prepare() once after all peers settle','commit() exactly once from held preedge inputs on supplied FASED target edge'],
      invalid_phase='commit without settled prepare refuses; failed prepare invalidates sample/commit; repeated evaluate makes no edge and accepts no owner',
      geometry=dict(address_bits=33,id_bits=4,data_bits=64,strobe_bits=8,burst='INCR',size=3,beats=[1,8],alignment_bytes=8,max_boundary_bytes=4096),
      knownness='control/active metadata and every strobed byte must be known; full64 reads require every returned byte known; uninitialized mapped bytes remain unknown',
      ownership='AR data snapshot at actual acceptance; independent AW and W FIFO, nth AW pairs nth complete WLAST burst; repeated IDs retain FIFO ownership; source LP chooses egress, registered R/B visible next target edge',
      visibility='Staged accepted writes update declared backing only on actual B acceptance. All subsequent line access requires an explicit idle acknowledge_external_fence(). This is a caller checkpoint, not proof of RISC-V FENCE or coherent cache flush.',
      conflicts='live write/read and write/write line overlap refuse; read/read allowed; unowned partial or complete W data forbids read admission; pending reset refuses',
      events='No public cross-component event API in this epoch. Internal accepted owner sequence is not a hart ID. Future source TL/VMU owner joins must be derived from actual accepted adapters, not AXI ID guesses.',
      clocks='Caller supplies FASED target edges. Source calendar is1GHz master/Bringup/FASED,500MHz Iris/uncore,100MHz Serial, periods1/2/10. Observed30 is FASED ticks, not CPU cycles.',
      System_fixture_domain=dict(physical_base='0x80000000',bytes=0x400000,initialization='explicit list of defined64B lines only; no implicit bytes'),
      mapping_unknowns=['general guestPA→externalAXI/hostDRAMoffset','runtime hostDRAM allocation/remap','full hosttoken/ingress/egress/backpressure targetFire'],
      unavailable=['native or executed-ELF integration','Saturn VMU/VRF/TLWidthWidget/TLBuffer producer join','AXI B⇒coherent TL D/SIFQ/VRF completion equivalence','overlapping RAW/atomics/narrow reads','CPU/Zephyr timing or physical memory latency certification'])
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    sdk=OUT/'sdk';sdk.mkdir()
    for p in sources:
        q=OUT/'src'/p.relative_to(ROOT);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    for n in ['fased_backing_ledger_v1.hpp','fased_backing_service_v2.hpp']:shutil.copy2(ROOT/'timing'/n,sdk/n)
    for p in reports:
        q=OUT/'proofs'/p.parent.name;q.mkdir(parents=True)
        for source in p.parent.iterdir():
            if source.is_file() and (source.suffix in {'.json','.stdout','.stderr','.d'}or source.name=='check'):shutil.copy2(source,q/source.name)
    report=dict(schema='iris.FASED_write_backing_component.v1',**{'pass':True},proofs=proofs,source_facts=facts,
       functional_ledger=dict(checks=39910,write_read_roundtrips=1000,byte_checks=16384,typed_refusals=1031),
       actual_LP_differential=dict(profiles=24,target_edges=58120,checks=945744,byte_checks=393216,corruption_refusals=7),
       actual_System_source_fixture=dict(seeds=[1,17],checks=393594,per_seed=dict(AXI_AR=40,AW=24,W=192,R=320,B=24,evicted_lines_independently_checked=24,master_ticks=59079),extra_refusals=['cold RPQ store queue3slot0','undefined mapped read line','outside physical domain']),
       old_v1_preserved=True,new_split_phase_v2=True,source_LP_control_changed=False,explicit_physical_domains=True,
       all_knownness_or_ready_from_declared_source=True,full_FASED_host_token_bridge=False,native_CPU_or_ELF_qualification=False,
       hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,native_provider_or_default_modified=False,
       observed_30_admitted_as_CPU_default=False,source_image_association_verified=False,calibration_usable=False,timing_certified=False,input_sha256=inputs)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    artifact={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()}
    manifest=dict(schema='iris.FASED_write_backing_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),contract_sha256=sha(OUT/'contract.json'),artifact_sha256=artifact,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifact))))
if __name__=='__main__':main()
