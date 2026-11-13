#!/usr/bin/env python3
"""Freeze corrected typed source transport and all finite admission evidence."""
from pathlib import Path
import hashlib
import json
import shutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/saturn-storefront-typed-component-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir();sdkbuild=ROOT/'build/saturn-storefront-typed-sdk-v2';raw=ROOT/'build/saturn-storefront-component-v1'
    reports=[sdkbuild/'build.json',ROOT/'build/saturn-storefront-payload-fullmask-v2/report.json',ROOT/'build/saturn-storefront-payload-zerofull-v3/report.json',ROOT/'build/saturn-storefront-raw-porttrace-v1/report.json',ROOT/'build/saturn-storefront-typed-porttrace-v1/report.json']
    inputs={};proofs=[]
    for p in reports:
        j=json.loads(p.read_text());assert j['pass']is True
        for name,digest in j['input_sha256'].items():assert sha(name)==digest,(name,digest);inputs[name]=digest
        for name,digest in j.get('compiled_dependency_sha256',{}).items():assert sha(name)==digest;inputs[name]=digest
        for name,digest in j.get('output_sha256',{}).items():assert sha(name)==digest
        inputs[str(p)]=sha(p);proofs.append(dict(path=str(p),sha256=sha(p)))
    a=ROOT/'build/saturn-storefront-raw-porttrace-v1/positive.ports.bin';b=ROOT/'build/saturn-storefront-typed-porttrace-v1/payload.ports.bin';assert a.read_bytes()==b.read_bytes();inputs[str(a)]=sha(a);inputs[str(b)]=sha(b)
    source=ROOT/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/rtl/TLInterface.sv';literal="  assign auto_out_a_bits_opcode = io_req_bits_store ? 3'h1 : 3'h4;";lines=source.read_text().splitlines();line=next(i+1 for i,s in enumerate(lines)if s.startswith(literal));inputs[str(source)]=sha(source)
    rawmanifest=json.loads((raw/'manifest.json').read_text());assert sha(raw/'manifest.json')=='fa3fef57b9606273a207e4a429d81ddda72b115264c09df7468857eb3f07c715';inputs[str(raw/'manifest.json')]=sha(raw/'manifest.json')
    shutil.copytree(sdkbuild/'sdk',OUT/'sdk');shutil.copytree(sdkbuild/'source',OUT/'source')
    for name in ['saturn_storefront_v1.hpp','saturn_storefront_v1.cpp','saturn_storefront_sdk_build_v1.py','saturn_storefront_payload_check_v2.cpp','saturn_storefront_payload_check_v3.cpp','saturn_storefront_payload_check_v4.cpp','saturn_storefront_payload_check_v2.py','saturn_storefront_payload_check_v3.py','saturn_storefront_payload_check_v4.py','saturn_storefront_typed_check_v4.py','saturn_storefront_typed_guards_v2.cpp','freeze_saturn_storefront_typed_v1.py']:
        p=ROOT/'timing'/name;q=OUT/'src/timing'/name;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[str(p)]=sha(p)
    for p in reports:
        target=OUT/'proofs'/p.parent.name;shutil.copytree(p.parent,target,ignore=shutil.ignore_patterns('payload','guards','check','*.o','*.a','executed-inputs','sdk','source'))
    sdkreport=json.loads((sdkbuild/'build.json').read_text());assert sha(OUT/'sdk/libiris_saturn_storefront.a')==sdkreport['library_sha256']
    contract=dict(schema='iris.compute_Saturn_storefront_typed_contract.v1',namespace='iris::saturn_storefront',class_name='Model',
       constructor='Model(hart0|1,seed,source_plusargs,Calendar{period_master_ticks=2,phase_master_ticks=0|1},explicit vector<Domain>{physical35 base,bytes})',
       input_api='input_fields()/input_index(name); vector<Input>{Bits value,known}, four64bit limbs. Same raw source cut, explicit clock excluded.',
       phase='evaluate_control(inputs,optional load Owner,optional store Owner) and sample() repeatedly to global fixed point; prepare(master_tick) once settled; commit() exactly one consecutive selected source edge.',
       owner_fields=['hart','tag','epoch','command','generation','pc','raw'],owner_note='Tag4 physical; all remaining fields are immutable host audit metadata. Reset epoch increments once per reset assertion. Generation increases per direction/tag and can restart only after new reset epoch.',
       receipt_phases=['VMURequest','TileA','TileD','VMUResponse'],receipt_fields=['complete immutable Owner','load/store','physical source','mask16','physical address','data16+known16','source_edge','master_tick'],
       clock_domains='source_edge names the given compute-hart/uncore source domain; master_tick names the explicit1GHz reference calendar. Caller supplies every2tick source edge; odd master phases are preserved. No CPU/FASED latency conversion guessed.',
       publication='Receipts become visible only after commit. VMUResponse releases transport ownership, not circularROB credit or orderedSIFQ. Preedge ACK valid/tag remain in sample() for a same-edge upstream controller join.',
       store_opcode='Always PutPartialData1, including full mask0xffff, per saved TLInterface.sv. No PutFull inference.',
       knownness='Active controls/address/mask/tag and strobed store bytes must be known; load D requires its original requested16B half known. Unmasked bytes remain uncredited/unknown in receipts. No memory is seeded or mutated by this transport.',
       guard_scope=['compute hart0/1 only','explicit physical35 domains and16B alignment; no implicit40→35 alias','one live transport owner per source/tag; generation/epoch checks','offered owner and enabled payload immutable under backpressure','accepted VMU→actual A→owned D→later VMUresponse phase','exact D size4/opcode/param and no denied/corrupt/duplicate/unowned return','no reset with owned or blocked work','source4bit busy wrap cannot release host ownership','caller context preserved across constructor/phase errors/destructor','no commit without settled prepare; no skipped/stale/wrapped clock edge'],
       finite_refusals=['zero-mask store offer (raw source supports it; masked/drop VMU lifecycle not modeled here)','denied/corrupt D','unmapped/unknown/unaligned physical requests','narrow/larger than16B requests','native product System backend until arena/queue history is qualified'],
       same_edge_caveat='Source components use their preedge pins. Do not process postcommit receipts as an excuse for a new ACK→ROB handoff cycle; semantic RAM publication stays after successful source commit.',
       unavailable=['VMU AddrGen/SIQ/SIFQ/circularROB implementation','CPU/IRQ/context/preemption timing','actual System/NoC/L2/FASED/arena join','native coherent mirror or overlapping peer visibility','full internal four-state or source/FPGA image attestation'])
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    typed=json.loads(reports[-1].read_text());positive=next(r['result']for r in typed['checks']if r['name']=='payload');guards=next(r['result']for r in typed['checks']if r['name']=='guards')
    report=dict(schema='iris.compute_Saturn_storefront_typed_component.v1',**{'pass':True},proofs=proofs,
       actual_source_payload=positive,typed_guards=guards,
       raw_typed_preedge_port_trace=dict(bytes=a.stat().st_size,sha256=sha(a),byte_equal=True,scope='Every postreset active/qualified raw physical output at each source edge, masked payload only; no unused-state credit'),
       source_store_opcode=dict(path=str(source),line=line,literal=lines[line-1]),
       preserved_development_failure='Typed SDK v1 incorrectly inferred PutFull for full mask; corrected only host guard. Frozen raw v1 random oracle branch for fullmask was unexercised; source/model library unchanged. New forced0/full/random source controls explicitly cover it.',
       input_sha256=inputs,library_sha256=sha(OUT/'sdk/libiris_saturn_storefront.a'),header_sha256=sha(OUT/'sdk/saturn_storefront_v1.hpp'),raw_source_manifest_sha256=sha(raw/'manifest.json'),
       source_RTL_or_runtime_modified=False,standalone_transport_available=True,production_native_or_System_backend_available=False,
       hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,current_native_provider_default_changed=False,source_image_association_verified=False,timing_certified=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');artifacts={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()}
    manifest=dict(schema='iris.compute_Saturn_storefront_typed_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),artifact_sha256=artifacts,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifacts))))
if __name__=='__main__':main()
