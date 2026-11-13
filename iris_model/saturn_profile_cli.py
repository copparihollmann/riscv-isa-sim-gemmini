"""Generate source-qualified component profiles from a frozen Saturn capsule."""
import argparse
from contextlib import contextmanager
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import time

from .saturn_profile import profile


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


class Capsule:
    def __init__(self, root, expected, expected_schema='iris.saturn_qualified_activity_frozen_capsule.v1'):
        self.root=Path(root).resolve();self.used={}
        if not re.fullmatch('[0-9a-f]{64}',expected) or digest(self.root/'report.json')!=expected:
            raise ValueError('Frozen component receipt SHA256 mismatch')
        self.manifest=json.loads((self.root/'report.json').read_text())
        if self.manifest.get('schema')!=expected_schema or self.manifest.get('pass') is not True:
            raise ValueError('Qualified activity component receipt required')
        self.entries={e['path']:e for e in self.manifest['artifacts']}
        if len(self.entries)!=len(self.manifest['artifacts']):raise ValueError('Duplicate capsule artifact')
        self.used[str(self.root/'report.json')]=expected

    def path(self, relative):
        name=PurePosixPath(relative)
        if name.is_absolute() or '..' in name.parts or relative not in self.entries:
            raise ValueError('Uninventoried/unsafe component path')
        entry=self.entries[relative];p=self.root/relative
        info=p.lstat()
        if (self.root not in p.resolve().parents or not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode)!=entry['mode'] or info.st_size!=entry['bytes']
                or digest(p)!=entry['sha256']):raise ValueError('Frozen component artifact changed: '+relative)
        self.used[str(p)]=entry['sha256'];return p

    def by_digest(self, expected):
        matches=[name for name,e in self.entries.items() if e['sha256']==expected]
        if not matches:raise ValueError('Referenced input absent from frozen capsule')
        return self.path(sorted(matches)[0])

    def document(self, relative):return json.loads(self.path(relative).read_text())


def timebase(capsule, proof, case):
    # Follow the actual whole-capture observer's reference build, rather than
    # borrowing a frequency from a different elaboration or the FPGA host.
    matches=[h for p,h in proof['input_sha256'].items() if p.endswith('/'+case+'/report.json')]
    if len(matches)!=1:raise ValueError('Unique actual whole-RTL capture receipt required')
    capture=json.loads(capsule.by_digest(matches[0]).read_text())
    if (capture.get('exit_status')!=0 or capture.get('timed_out') is not False
            or capture.get('same_architectural_signature_as_frozen_guest') is not True):
        raise ValueError('Actual reference guest did not complete independently')
    observers=[]
    for name,h in capture['input_sha256'].items():
        if name.endswith('/build.json'):
            candidate=json.loads(capsule.by_digest(h).read_text())
            if candidate.get('schema')=='iris.saturn_activity_whole_rtl_observer.v1':observers.append(candidate)
    if len(observers)!=1:raise ValueError('Unique source observer build required')
    builds=[]
    for name,h in observers[0]['input_sha256'].items():
        if name.endswith('/build.json'):
            candidate=json.loads(capsule.by_digest(h).read_text())
            if 'verilate_argv' in candidate:builds.append(candidate)
    if len(builds)!=1:raise ValueError('Actual reference clock build required')
    build=builds[0];argv=build['verilate_argv']
    if argv.count('--timescale')!=1 or argv[argv.index('--timescale')+1]!='1ns/1ps':
        raise ValueError('Unqualified TestDriver timescale')
    periods=[x.split('=',1)[1] for x in argv if x.startswith('+define+CLOCK_PERIOD=')]
    if len(periods)!=1:raise ValueError('Unique compiled TestDriver period required')
    period=Decimal(periods[0])
    if not period.is_finite() or period<=0:raise ValueError('Invalid TestDriver period')
    drivers=[h for p,h in build['source_sha256'].items() if p.endswith('/TestDriver.v')]
    if len(drivers)!=1:raise ValueError('Source clock/counter implementation required')
    driver=capsule.by_digest(drivers[0]);text=driver.read_text()
    if ('always #(`CLOCK_PERIOD/2.0) clock = ~clock;' not in text
            or 'always @(posedge clock)' not in text
            or text.count('trace_count = trace_count + 1;')!=1):
        raise ValueError('TestDriver trace counter convention changed')
    return float(Decimal(10**9)/period),{'source':str(driver),'source_sha256':drivers[0],
        'compiled_CLOCK_PERIOD_ns':str(period),'timescale':'1ns/1ps',
        'coordinate':'TestDriver.trace_count increments once per TestDriver clock period; distinct from per-hart mcycle'}


def _signature(info):return info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns


@contextmanager
def projection_rows(path, expected):
    path=Path(path);initial=path.lstat()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as raw:
        before=os.fstat(raw.fileno())
        if not stat.S_ISREG(before.st_mode) or _signature(initial)!=_signature(before):raise ValueError('Projection input changed')
        h=hashlib.sha256()
        for block in iter(lambda:raw.read(1024*1024),b''):h.update(block)
        if h.hexdigest()!=expected:raise ValueError('Projection SHA256 mismatch')
        raw.seek(0);finished=[False]
        def rows(stream):
            while True:
                line=stream.readline(65537)
                if not line:finished[0]=True;return
                if len(line)>65536:raise ValueError('Oversized projection row')
                yield json.loads(line)
        try:
            with gzip.GzipFile(fileobj=raw,mode='rb') as stream:
                yield rows(stream)
                if not finished[0]:raise ValueError('Complete projection consumption required')
        finally:
            if _signature(before)!=_signature(os.fstat(raw.fileno())) or _signature(before)!=_signature(path.lstat()):
                raise ValueError('Projection changed while profiling')


def run(component, expected, case, output, regions_path=None):
    started=time.monotonic()
    component,output=Path(component).resolve(),Path(output).resolve()
    if output.exists() or output==component or component in output.parents:
        raise ValueError('Fresh output directory outside frozen component required')
    output.mkdir(parents=True)
    capsule=Capsule(component,expected)
    proof=capsule.document(capsule.manifest['proof'])
    if (proof.get('schema')!='iris.saturn_internal_activity_actual_rtl_proof.v1'
            or proof.get('only_physical_inputs_drive_model') is not True
            or proof.get('all_internal_state_computed_continuously_from_actual_reset') is not True):
        raise ValueError('Continuous independent source-replay evidence required')
    selected=[r for r in proof['positive_replays'] if r['case']==case]
    if {r['seed'] for r in selected}!={0,17,91} or len(selected)!=3:
        raise ValueError('All three independently qualified source-reset seeds required')
    expected_counts=[h['source_edges'] for h in selected[0]['harts']]
    if any([h['source_edges'] for h in row['harts']]!=expected_counts for row in selected):
        raise ValueError('Qualified source clock coverage differs by seed')
    schema_path=capsule.path(capsule.manifest['projection_schema']);schema=json.loads(schema_path.read_text())
    contract_path=capsule.path(capsule.manifest['contract']);contract=json.loads(contract_path.read_text())
    if schema['contract_sha256']!=digest(contract_path):raise ValueError('Projection/contract binding differs')
    relative=str(PurePosixPath(capsule.manifest['proof']).parent/(case+'-projection.ndjson.gz'))
    projection=capsule.path(relative)
    if proof['artifact_sha256'].get(projection.name)!=digest(projection):raise ValueError('Projection is not bound by replay proof')
    hz,clock_source=timebase(capsule,proof,case)
    regions=[] if regions_path is None else json.loads(Path(regions_path).read_text())
    with projection_rows(projection,digest(projection)) as rows:
        summary,trace=profile(rows,schema,contract,hz,clock_source,regions)
    if summary['frames_per_hart']!=expected_counts:raise ValueError('Profile omitted qualified source edges')
    summary.update(component_receipt_sha256=expected,source_identity=capsule.manifest['source_identity'],case=case,
        producer_qualification='Finite saved-RTL reference activity, three reset seeds; no FPGA/full-model/numeric-knownness certification',
        input_sha256=dict(capsule.used))
    summary['input_sha256'].update({str(p):digest(p) for p in [Path(__file__).resolve(),Path(__file__).with_name('saturn_profile.py').resolve()]})
    if regions_path is not None:summary['input_sha256'][str(Path(regions_path).resolve())]=digest(regions_path)
    tool_sources=output/'tool-source';tool_sources.mkdir()
    for p in [Path(__file__).resolve(),Path(__file__).with_name('saturn_profile.py').resolve()]:
        data=p.read_bytes();h=hashlib.sha256(data).hexdigest()
        if summary['input_sha256'][str(p)]!=h:raise ValueError('Profiler source changed during run')
        (tool_sources/h).write_bytes(data)
    for name,value in [('summary.json',summary),('timeline.json',trace)]:
        (output/name).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    report={'schema':'iris.saturn_source_profile_run.v1','pass':True,'hardware_contacted':False,
        'component_receipt_sha256':expected,'case':case,'frames_per_hart':summary['frames_per_hart'],
        'artifact_sha256':{name:digest(output/name) for name in ('summary.json','timeline.json')},
        'input_sha256':summary['input_sha256'],'FPGA_or_full_timing_certified':False,'calibration_usable':False}
    report['profile_host_seconds']=time.monotonic()-started
    report['observed_source_frames_per_host_second']=sum(summary['frames_per_hart'])/report['profile_host_seconds']
    report['speed_scope']='Projection decoding/profiling only; not simulation MIPS or whole-SoC runtime'
    report['artifact_sha256'].update({str(p.relative_to(output)):digest(p) for p in tool_sources.iterdir()})
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--component',type=Path,required=True)
    p.add_argument('--component-sha256',required=True);p.add_argument('--case',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--regions',type=Path)
    a=p.parse_args();r=run(a.component,a.component_sha256,a.case,a.output,a.regions)
    print(json.dumps({'pass':r['pass'],'case':r['case'],'frames_per_hart':r['frames_per_hart']}))
