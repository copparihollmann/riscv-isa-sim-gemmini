#!/usr/bin/env python3
"""Verify the isolated UART candidate, actual processes and Zephyr/compiler output."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def make_record():
    snapshot=ROOT/'build/uart-device-snapshot';manifest=json.loads((snapshot/'manifest.json').read_text())
    versions=[item for values in manifest.get('artifact_versions',{}).values() for item in values]
    for item in [*manifest['artifacts'].values(),*versions]:
        if sha(snapshot/item['snapshot_path'])!=item['sha256']:raise ValueError('UART snapshot changed')
    def archived(path,digest):
        key=str(Path(path).resolve());item=manifest['artifacts'].get(key)
        if item and item['sha256']==digest:return
        for version in manifest.get('artifact_versions',{}).get(key,[]):
            if version['sha256']==digest:return
        if sha(path)!=digest:raise ValueError('Missing UART evidence/source: '+key)
    build_path=ROOT/'build/uart-device/build.json';build=json.loads(build_path.read_text())
    if build['status']!='built_and_unit_passed' or build['binary_sha256']!=manifest['native_sha256'] or build['uart_sha256']!=manifest['uart_sha256']:raise ValueError('Wrong UART build identity')
    for name,digest in build['input_sha256'].items():archived(name,digest)
    process_path=ROOT/'build/uart-device-qualified-check/results.json';process=json.loads(process_path.read_text())
    if process['status']!='passed_uart_process_cases' or len(process['cases'])!=12 or not process['native_plugin_mismatch_refused']:raise ValueError('Incomplete UART process coverage')
    for name,digest in process['input_sha256'].items():archived(name,digest)
    for case in process['cases']:
        if not case['pass']:raise ValueError('UART guest failed')
        for stream in ('stdout','stderr'):archived(process_path.parent/(case['name']+'.'+stream),case[stream+'_sha256'])
        archived(case['argv'][-1],case['elf_sha256'])
        if case['graph_sha256']:archived(process_path.parent/(case['name']+'.graph.json'),case['graph_sha256'])
    rows={}
    for name,path in [('scalar','build/uart-zephyr-scalar-final/results.json'),('mixed','build/uart-zephyr-mixed-final/results.json'),('mixed-live','build/uart-zephyr-mixed-live-final/results.json')]:
        record=json.loads((ROOT/path).read_text())
        if not record['status'].startswith('passed_') or record['binary_sha256']!=manifest['native_sha256'] or record['uart_sha256']!=manifest['uart_sha256']:raise ValueError('Wrong Zephyr UART execution')
        for stream in ('stdout','stderr'):archived((ROOT/path).parent/stream,record[stream+'_sha256'])
        rows[name]={'path':path,'sha256':sha(ROOT/path),'regions':len(record['regions'])}
    path=ROOT/'build/uart-compiled-gemm-h2-final/results.json';compiled=json.loads(path.read_text())
    if not compiled['pass'] or not compiled['real_merlin_mlir_executed'] or compiled['workers']!=2 or compiled['binary_sha256']!=manifest['native_sha256'] or compiled['uart_sha256']!=manifest['uart_sha256']:raise ValueError('Wrong compiled UART execution')
    for run in compiled['runs']:
        if not run['all_int32_and_w8a8_values_match'] or not any(run['producer']['overlap_masks']):raise ValueError('Compiled numerical/producer failure')
        folder=path.parent/(run['kind']+'-run')
        for stream in ('stdout','stderr'):archived(folder/stream,run[stream+'_sha256'])
        golden=path.parent/'generated/golden.json';archived(golden,compiled['source_sha256'][str(golden)])
        values=[json.loads(line.split(' ',1)[1]) for line in (folder/'stdout').read_text().splitlines() if line.startswith('IRIS_COMPILER_RESULT ')]
        if values!=json.loads(golden.read_text()):raise ValueError('Full compiled output no longer matches independent golden')
    rows['real-mlir-gemm']={'path':str(path.relative_to(ROOT)),'sha256':sha(path),'full_output_elements_per_kind':12288}
    drained=ROOT/'build/uart-device-drained-runtime-qualified/results.json';drain=json.loads(drained.read_text())
    if drain['status']!='passed_uart_process_cases' or len(drain['cases'])!=12:raise ValueError('Drained runtime cases failed')
    header=str(ROOT/'benchmarks/uart_drain.h')
    if header not in drain['input_sha256']:raise ValueError('Drained runtime header was not bound')
    for name,digest in drain['input_sha256'].items():archived(name,digest)
    rows['drained-runtime']={'path':str(drained.relative_to(ROOT)),'sha256':sha(drained),'actual_process_cases':12,'uart_drain_header_sha256':drain['input_sha256'][header]}
    clock=ROOT/'hardware/evidence/firesim-clocks.freq-summary';uart=ROOT/'board/uart-source-evidence.json'
    return {'schema':'iris.uart.integration_acceptance.v1','status':'passed_isolated_uart_integration','generator_sha256':sha(Path(__file__)),'snapshot_manifest_sha256':sha(snapshot/'manifest.json'),'native_sha256':manifest['native_sha256'],'uart_sha256':manifest['uart_sha256'],'base_native_sha256':build['base_native_binary_sha256'],'native_device_abi':1,'helper_cases':10,'clock_adapter_cases':9,'actual_guest_processes':12,'drained_runtime_process_cases':12,'mismatched_native_refused':True,'physical_uart_hz':500000000,'rtc_hz':500000,'live_fixture_base_hz':[100000000,500000000],'clock_source':{'path':str(clock.relative_to(ROOT)),'sha256':sha(clock),'locator':'Output clock uart_clock requested/actual500.0MHz'},'register_source':{'path':str(uart.relative_to(ROOT)),'sha256':sha(uart),'locator':'facts and full40-character source revisions: FIFO256,wm9,resetDIV135,64bitport'},'zephyr_compiler_evidence':rows,'empty_rx_data':'fail closed while selected FIFO cell is unknown; status-byte reads remain defined','rx_stimulus':'explicit start/completion frame boundaries; pin sampling unmodeled','same_edge_arbitration':'ordered model calls; cycle-accurate TL pipeline unqualified','source_image_association_verified':False,'primary_modified':False,'primary_published':False,'rtl_certified':False,'timing_accuracy_certified':False,'remaining':['Coordinated primary runtime/native/device publication with full epoch gates','UARTRx pin sampling and safe unused-undefined-bit handling for fullword empty-poll drivers','RTL bus/FIFO simultaneous-edge timing and deployed image association','Hardware calibration and held-out accuracy']}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();data=make_record();path=ROOT/'board/uart-device/acceptance.json'
    if a.verify:
        if json.loads(path.read_text())!=data:raise ValueError('UART integration audit is stale')
    else:path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'status':data['status'],'actual_guest_processes':12,'primary_published':False,'rtl_certified':False}))
if __name__=='__main__':main()
