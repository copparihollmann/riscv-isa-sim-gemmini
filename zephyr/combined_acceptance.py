#!/usr/bin/env python3
"""Freeze actual OS/compiler/profile gates for the combined experimental epoch."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
NATIVE='35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d'
UART='cc9e38b8df42c0f482f94213a0f58747e1e1c66bd17d54eef154e3ea9748a34b'
SOURCE='ef1214f25a2db5a01b6dd9aa1180b002c0f4da74ec987ac0a5b90bff10ed7088'


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda:stream.read(1024*1024),b''):h.update(part)
    return h.hexdigest()


def check_gate(name,data):
    if name in ('scalar6','mixed9','mixed9-live'):
        if data['exit_status'] or data['timed_out'] or data['errors'] or len(data['regions'])!=(6 if name=='scalar6' else 9):raise ValueError('failed scalar/mixed gate')
    elif name in ('rvv6','rvv6-vme-aware'):
        if data['exit_status'] or len(data['rows'])!=6 or {r['hart'] for r in data['rows']}!={0,1,2} or any(r['rounds']!=12 or r['timer_ticks']<=0 for r in data['rows']):raise ValueError('failed competing RVV context gate')
    elif name=='vme4':
        if data['exit_status'] or len(data['rows'])!=4 or any(r['rounds']!=8 or r['hart_mask']!=3 or not r['saves'] or not r['restores'] for r in data['rows']) or not data['producer'][0]['vme_refused']:raise ValueError('failed migrating VME ownership gate')
    else:
        if not data['pass'] or not data['real_merlin_mlir_executed'] or len(data['runs'])!=2 or any(not r['pass'] or r['full_output_elements']!=12288 or not r['all_int32_and_w8a8_values_match'] for r in data['runs']):raise ValueError('failed actual compiler/golden gate')


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if args.verify:
        report=json.loads((out/'report.json').read_text())
        for rel,digest in report['artifact_sha256'].items():
            p=(out/rel).resolve()
            if not p.is_relative_to(out) or sha(p)!=digest:raise ValueError('acceptance artifact changed/escaped')
        for original,item in report['inputs'].items():
            p=out/item['saved']
            if item['compressed']:
                h=hashlib.sha256()
                with gzip.open(p,'rb') as stream:
                    for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
                actual=h.hexdigest()
            else:actual=sha(p)
            if actual!=item['sha256']:raise ValueError('archived acceptance input changed: '+original)
        for name,item in report['gates'].items():check_gate(name,json.loads((out/item['receipt']).read_text()))
        if report['timing_certified'] or report['rtl_certified'] or report['hardware_contacted']:raise ValueError('experimental acceptance cannot claim full certification')
        print(json.dumps({'verified':True,'gates':len(report['gates']),'regions_profiled':9,'native_sha256':report['binary_sha256']}));return
    out.mkdir(parents=True,exist_ok=False);(out/'inputs').mkdir()
    source=ROOT/'build/combined-frozen-35901887/manifest.json'
    if sha(source)!=SOURCE:raise ValueError('combined source epoch changed')
    inputs={}
    def retain(path,expected=None):
        path=Path(path).resolve();digest=sha(path)
        if expected is not None and digest!=expected:raise ValueError('acceptance input changed: '+str(path))
        compressed=path.stat().st_size>16*1024*1024 and path.suffix=='.json'
        saved=Path('inputs')/(digest+('.gz' if compressed else ''))
        if not (out/saved).exists():
            if compressed:
                with path.open('rb') as src,(out/saved).open('wb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=3) as dst:shutil.copyfileobj(src,dst)
            else:shutil.copyfile(path,out/saved)
        inputs[str(path)]={'sha256':digest,'saved':str(saved),'compressed':compressed}
        return str(saved)
    retain(source,SOURCE);retain(ROOT/'build/combined-candidate-35901887/spike',NATIVE);retain(ROOT/'build/combined-candidate-35901887/libsifive_uart.so',UART)
    for path in (Path(__file__),ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'):retain(path)
    gates={}
    for name in ('scalar6','mixed9','rvv6','rvv6-vme-aware','vme4','mixed9-live','merlin-gemm2'):
        directory=ROOT/('build/combined-os-'+name);path=directory/'results.json';data=json.loads(path.read_text());check_gate(name,data)
        if name=='merlin-gemm2':
            if data['binary_sha256']!=NATIVE or data['uart_sha256']!=UART:raise ValueError('compiler pair mismatch')
            for source_path,digest in data['source_sha256'].items():retain(source_path,digest)
            for run in data['runs']:
                if sha(run['argv'][0])!=NATIVE or '--extlib='+str(ROOT/'build/combined-candidate-35901887/libsifive_uart.so') not in run['argv']:raise ValueError('wrong compiled-run pair')
        else:
            if sha(data['argv'][0])!=NATIVE or '--extlib='+str(ROOT/'build/combined-candidate-35901887/libsifive_uart.so') not in data['argv']:raise ValueError('wrong OS pair')
            for key in ('stdout','stderr'):retain(directory/key,data[key+'_sha256'])
            elf=Path(data['argv'][-1]);retain(elf);build=elf.parents[1]/'build.json';proof=json.loads(build.read_text());retain(build)
            for original,digest in proof['input_sha256'].items():retain(ROOT/original,digest)
            for original,digest in data.get('input_sha256',{}).items():retain(ROOT/original,digest)
        gates[name]={'receipt':retain(path),'receipt_sha256':sha(path)}
        if name=='merlin-gemm2':
            for p in directory.rglob('*'):
                if p.is_file():retain(p)
    profile=ROOT/'build/combined-os-mixed9-profile';summary=json.loads((profile/'summary.json').read_text())
    if len(summary['observed_regions'])!=9 or summary['region_projection']['method']!='captured_counter_reads' or summary['region_projection']['certified'] is not False:raise ValueError('actual counter region profile missing')
    projection=summary['region_projection'];live=ROOT/'build/combined-os-mixed9-live'
    for field,path in [('graph_sha256',live/'graph.json'),('console_sha256',live/'stdout'),('run_receipt_sha256',live/'results.json')]:retain(path,projection[field])
    for path in profile.iterdir():
        if path.is_file():retain(path)
    run=json.loads((live/'results.json').read_text());retired=sum(run['live_fixture']['retired_instructions'])
    report={'schema':'iris.combined_positive_os_compiler_profile_acceptance.v1','pass':True,'binary_sha256':NATIVE,'uart_sha256':UART,
            'source_closure_sha256':SOURCE,'gates':gates,'profiled_regions':9,'actual_captured_counter_boundaries':True,
            'instrumented_mixed_run_speed':{'retired_instructions':retired,'host_seconds':run['host_seconds'],
                'simulated_mips':retired/run['host_seconds']/1e6,'scope':'Experimental source-pipeline/serialized-other-operations integration fixture; includes native graph export, excludes subsequent profile generation. Not calibrated full-SoC MIPS.'},
            'inputs':inputs,'timing_certified':False,'rtl_certified':False,'full_zephyr_or_model_certified':False,'hardware_contacted':False}
    report['artifact_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'gates':len(gates),'profiled_regions':9,'report_sha256':sha(out/'report.json')}))


if __name__=='__main__':main()
