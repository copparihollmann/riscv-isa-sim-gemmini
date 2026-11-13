#!/usr/bin/env python3
"""Inventory exact candidate image/driver collateral without executing hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from urllib.parse import unquote, urlparse


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def inventory(archive):
    rows=[]
    with tarfile.open(archive) as stream:
        for member in stream:
            if member.isdir():continue
            if not member.isfile():raise ValueError('nonregular artifact tar member')
            h=hashlib.sha256();source=stream.extractfile(member)
            for block in iter(lambda:source.read(1024*1024),b''):h.update(block)
            rows.append({'name':member.name,'bytes':member.size,'sha256':h.hexdigest()})
    return rows


def bridges(text):
    rows=[]
    for number,line in enumerate(text.splitlines(),1):
        match=re.fullmatch(r'\s*registry\.add_widget\(new ([A-Za-z_][A-Za-z_0-9]*)\(\s*',line)
        if match:rows.append({'class':match[1],'line':number})
    if not rows or not any(r['class']=='uart_t' for r in rows):raise ValueError('generated bridge constructors missing')
    return rows


def fased_registers(text):
    marker='registry.add_widget(new FASEDMemoryTimingModel('
    if text.count(marker)!=1:raise ValueError('one exact FASED constructor required')
    block=text.split(marker,1)[1].split('#endif',1)[0]
    vectors=re.findall(r'std::vector<std::pair<std::string,\s*uint32_t>>\{(.*?)\n\s*\}',block,re.S)
    if len(vectors)!=2:raise ValueError('unrecognized FASED readable/writable map')
    maps=[]
    for vector in vectors:
        pairs=re.findall(r'\{ R"ESC\(([^)]+)\)ESC", (\d+) \}',vector)
        if not pairs or len(dict(pairs))!=len(pairs):raise ValueError('invalid FASED register map')
        maps.append({key:int(value) for key,value in pairs})
    read,write=maps
    if not set(write)<=set(read) or any(read[k]!=v for k,v in write.items()):raise ValueError('FASED RW map disagrees')
    return {'readable':read,'writable':write,
            'periodic_stats_registers':[key for key in read if key not in write],
            'selected_latency_values_in_periodic_stats':False,
            'latency_histogram_data_available':'hostReadLatencyHist_enable' in write,
            'address_range_counters_available':'readRanges_enable' in write}


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--prepared',type=Path,required=True,help='Read artifact identities only; no execution/verification bypass')
    parser.add_argument('--header',type=Path,required=True)
    parser.add_argument('--driver',type=Path,required=True)
    parser.add_argument('--driver-top',type=Path)
    parser.add_argument('--fased-driver',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    prepared=json.loads((args.prepared/'run.json').read_text())
    files={};archives={}
    for key in ('image','driver'):
        uri=urlparse(prepared[key]['uri'])
        if uri.scheme!='file':raise ValueError('exact local artifact required')
        path=Path(unquote(uri.path));digest=sha(path)
        if digest!=prepared[key]['sha256']:raise ValueError('artifact changed: '+key)
        files[str(path.resolve())]=digest;archives[key]=inventory(path)
    driver_digest=sha(args.driver)
    if not any(r['sha256']==driver_digest for r in archives['driver']):raise ValueError('driver binary differs from bundle')
    constructors=bridges(args.header.read_text())
    memory=fased_registers(args.header.read_text())
    classes={r['class'] for r in constructors}
    nm=Path(shutil.which('nm')).resolve()
    run=subprocess.run([nm,'-C',args.driver],capture_output=True,text=True,timeout=30)
    (out/'nm.stdout').write_text(run.stdout);(out/'nm.stderr').write_text(run.stderr)
    if run.returncode or not run.stdout.strip():raise ValueError('driver symbol inventory unavailable')
    symbols={name:len(re.findall(r'\b'+re.escape(name)+r'::',run.stdout)) for name in
             ('uart_t','clockmodule_t','tracerv_t','autocounter_t','synthesized_prints_t')}
    for path in (args.header,args.driver,args.prepared/'run.json',Path(__file__),nm):files[str(path.resolve())]=sha(path)
    for path in (args.driver_top,args.fased_driver):
        if path:files[str(path.resolve())]=sha(path)
    (out/'inputs').mkdir()
    # Large original image/driver archives remain hash-addressed inputs; exact
    # binaries/header and raw inventories are retained locally for inspection.
    for path,digest in files.items():
        if path.endswith(('.tar.gz','.tar')):continue
        shutil.copyfile(path,out/'inputs'/digest)
    absent=[]
    for label,kind in [('instruction_commit_trace','tracerv_t'),('autocounter_events','autocounter_t'),
                       ('synthesized_print_stream','synthesized_prints_t')]:
        if kind not in classes:absent.append(label)
    report={'schema':'iris.candidate_image_observability.v2','candidate_only':True,'input_sha256':files,
            'image_members':archives['image'],'driver_members':archives['driver'],'driver_binary_sha256':driver_digest,
            'generated_header_sha256':sha(args.header),'generated_bridge_constructors':constructors,
            'driver_defined_symbol_occurrences':symbols,
            'fased':memory,
            'proposed_private_capture_settings':{'profile_interval_target_cycles':1000000,
                'purpose':'periodic aggregate FASED counters; not instruction trace or exact per-region traffic attribution',
                'source_supported_profile_interval':bool(args.driver_top and '+profile-interval=' in args.driver_top.read_text()),
                'required_output':'memory_stats0.csv',
                'empty_histogram_file_is_not_latency_measurement':not memory['latency_histogram_data_available'],
                'do_not_write_clock_or_memory_timing_parameters':True},
            'collateral_unavailable_instrumentation':absent,
            'planned_capture':{'guest':['raw UART','per-region mcycle/minstret/checksums','explicit trial IDs','completion/failure markers'],
                              'host':['separate phase stdout/stderr','actual configs/plusargs','phase host timing','programming/transfer logs','driver clock reports'],
                              'memory_model':['FASED selected runtime settings only if authorized readback is valid; source defaults are not measurements']},
            'do_not_enable_without_instantiated_bridge':absent,
            'loaded_image_verified':False,'header_matches_programmed_image_verified':False,
            'complete_source_image_provenance':False,'timing_calibrated':False,'hardware_contacted':False,
            'qualification':'Generated-header constructors and exact matching candidate driver bundle inventory only. Not a loaded-image attestation. Missing target hardware bridges cannot be created with runtime flags; driver global cycles are not per-run timing.'}
    report['artifact_sha256']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'constructors':[r['class'] for r in constructors],'unavailable_from_collateral':absent,
                      'symbol_counts':symbols,'hardware_contacted':False,'report':str(out/'report.json')}))


if __name__=='__main__':main()
