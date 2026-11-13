#!/usr/bin/env python3
"""Freeze unchanged compute source transport, with explicit raw-API limits."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/saturn-storefront-component-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    OUT.mkdir();source=ROOT/'build/saturn-storefront-source-v2';sdk=OUT/'sdk';sdk.mkdir();objects=OUT/'objects';objects.mkdir()
    report_paths=[source/'build.json',ROOT/'build/saturn-storefront-whole-check-v2/report.json',ROOT/'build/saturn-storefront-payload-check-v1/report.json'];inputs={};proofs=[]
    for p in report_paths:
        j=json.loads(p.read_text());assert j['pass']is True
        for name,digest in j['input_sha256'].items():assert sha(name)==digest;inputs[name]=digest
        for name,digest in j.get('compiled_dependency_sha256',{}).items():assert sha(name)==digest;inputs[name]=digest
        inputs[str(p)]=sha(p);proofs.append(dict(path=str(p),sha256=sha(p)))
    extraction=json.loads((source/'extraction.json').read_text());inputs[str(source/'extraction.json')]=sha(source/'extraction.json')
    old=ROOT/'build/saturn-timing-ownership-sdk-v7/sdk/libiris_saturn_timing.a';inputs[str(old)]=sha(old);inputs[str(Path(__file__).resolve())]=sha(Path(__file__).resolve())
    for n in ['saturn_storefront_build_v1.py','saturn_storefront_unit_check_v1.cpp','saturn_storefront_check_v1.py','saturn_storefront_payload_check_v1.cpp','saturn_storefront_payload_check_v1.py','freeze_saturn_storefront_v1.py']:
        p=ROOT/'timing'/n;q=OUT/'src/timing'/n;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q);inputs[str(p)]=sha(p)
    shutil.copytree(source/'rtl',OUT/'rtl');shutil.copy2(source/'extraction.json',OUT/'extraction.json');shutil.copy2(source/'model/VComputeStorefront.h',sdk/'VComputeStorefront.h')
    library=sdk/'libiris_compute_storefront.a';shutil.copy2(source/'model/VComputeStorefront__ALL.a',library);runtime={};commands=[]
    for name in ['verilated.o','verilated_threads.o','verilated_dpi.o']:
        cmd=['/usr/bin/ar','p',str(old),name];data=subprocess.check_output(cmd);q=objects/name;q.write_bytes(data);runtime[name]=sha(q);commands.append(cmd)
        cmd=['/usr/bin/ar','q',str(library),str(q)];subprocess.run(cmd,check=True);commands.append(cmd)
    cmd=['/usr/bin/ar','s',str(library)];subprocess.run(cmd,check=True);commands.append(cmd)
    # Relink and rerun arbitrary-payload proof using ONLY the new library.
    exe=OUT/'standalone-payload-check';v='/scratch/eygao/iris-cy/.conda-env/share/verilator/include'
    cmd=['/usr/bin/g++','-O2','-std=c++20','-I'+str(sdk),'-I'+v,str(ROOT/'timing/saturn_storefront_payload_check_v1.cpp'),str(library),'-pthread','-latomic','-o',str(exe)];commands.append(cmd)
    with(OUT/'compile.stdout').open('wb')as so,(OUT/'compile.stderr').open('wb')as se:subprocess.run(cmd,stdout=so,stderr=se,check=True,timeout=60)
    cmd=[str(exe)];commands.append(cmd)
    with(OUT/'standalone.stdout').open('wb')as so,(OUT/'standalone.stderr').open('wb')as se:subprocess.run(cmd,stdout=so,stderr=se,check=True,timeout=60)
    assert(OUT/'standalone.stdout').read_bytes()==(report_paths[2].parent/'positive.stdout').read_bytes()
    for p in report_paths:
        q=OUT/'proofs'/p.parent.name;shutil.copytree(p.parent,q,ignore=shutil.ignore_patterns('check','executed-inputs'))
    contract=dict(schema='iris.compute_Saturn_storefront_contract.v1',raw_class='VComputeStorefront',ports=extraction['ports'],
       scope='Exact associated compute-hart source TLSplitInterface→TLWidthWidget16→TLBuffer; scalarL1D bypass. No separate SaturnDCache/cachehit path is added.',
       source_inputs='VMU dmem load/store request addr40/tag4, store data128/mask16; finite mapped physical addresses must be qualified before40→35 truncation',
       source_outputs='ATL A address35/source5/size4/data256/mask32; one accepted16B request stays one physical A beat with appropriate half-mask',
       IDs='Writer tag0..15 maps source0..15; reader tag0..15 maps16..31. Source generation/command/hart provenance is external and never encoded into extra physical bits.',
       clock='One explicitly supplied compute/uncore edge per commit. System master1GHz invokes this compute slice every2 ticks; it must remain in the common evaluate/sample/commit fixed point.',
       busy='io_mem_busy is the source OR of two4-bit inflight counters. It can be0 at16outstanding. Upstream circularROB/maybe_full/SIFQ/VMU and complete owned-request ledger remain mandatory for drain.',
       availability='Raw source model only. No typed lifecycle/definedness/fault/duplicate-response host wrapper is provided in this epoch; native production backend remains unavailable.',
       mandatory_next_guards=['fully defined active addresses/masks/strobed bytes and returned load bytes','validate declared physical35 address domain; no silent highbit truncation','generation-keyed accepted VMU→physical A→D→VMU response ownership','matching size/opcode/source and reject denied/corrupt/unknown/duplicate D','source circularROB and orderedSIFQ release independent of response arrival','caller-context restore across construction/evaluate/commit/destruction/error','System/FASED/initial arena history before native availability'],
       exclusions=['VMU AddrGen/SIQ/SIFQ/ROB and VRF','CPU queues/COM/IRQ','coherent System/NoC/L2/Serial/FASED joining','native/ELF/Zephyr timing or numerical qualification'])
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2)+'\n')
    report=dict(schema='iris.compute_Saturn_storefront_component.v1',**{'pass':True},proofs=proofs,
       whole_unit_differential=dict(profiles=30,source_edges=6290,checks=59710,accepted_A=480,accepted_D=480,scrub_zero_byte_checks=7200),
       independent_payloads=dict(source_edges=14912,checks=145590,Get=2000,Put=4000,strobed_bytes=53230,full16_tag_windows=8518),
       semantic_corruption_refusals=['wrong halfword mask','wrong physical source','wrong returned halfword','wrong response tag'],
       copied_runtime_object_sha256=runtime,library_sha256=sha(library),standalone_relink_payload_output_byte_equal=True,
       commands=commands,input_sha256=inputs,source_RTL_modules_modified=False,parent_three_instances_modified=False,
       no_separate_compute_SaturnDCache=True,scalar_L1D_bypassed=True,raw_source_API_only=True,typed_native_backend_available=False,
       hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,parameters_fitted=False,current_native_provider_default_changed=False,source_image_association_verified=False,timing_certified=False)
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');artifacts={str(p.relative_to(OUT)):sha(p)for p in OUT.rglob('*')if p.is_file()}
    manifest=dict(schema='iris.compute_Saturn_storefront_capsule.v1',**{'pass':True},report_sha256=sha(OUT/'report.json'),artifact_sha256=artifacts,external_input_sha256=inputs)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(OUT/'report.json'),manifest_sha256=sha(OUT/'manifest.json'),artifacts=len(artifacts))))
if __name__=='__main__':main()
