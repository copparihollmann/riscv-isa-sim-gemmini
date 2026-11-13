"""Profile exact ELF owners from independently qualified source Saturn replay."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import shutil
import sys
import time

from .guest_regions import Instructions
from .report import symbols
from .saturn_profile_cli import Capsule,digest,projection_rows
from .saturn_owned_profile import profile


class Inventories:
    def __init__(self,root,expected):
        self.capsules={};self.load(root,expected,'iris.saturn_causal_ownership_frozen_capsule.v1')
        self.root=self.capsules[Path(root).resolve()]

    def load(self,root,expected,schema=None):
        root=Path(root).resolve()
        if root in self.capsules:
            if self.capsules[root].used[str(root/'report.json')]!=expected:
                raise ValueError('Conflicting dependency identity')
            return
        if digest(root/'report.json')!=expected:raise ValueError('Dependency receipt changed')
        document=json.loads((root/'report.json').read_text())
        capsule=Capsule(root,expected,schema or document['schema']);self.capsules[root]=capsule
        for dependency in document.get('dependencies',[]):
            self.load(dependency['path'],dependency['report_sha256'])

    def by_digest(self,expected):
        for capsule in self.capsules.values():
            if any(e['sha256']==expected for e in capsule.entries.values()):return capsule.by_digest(expected)
        raise ValueError('Referenced source absent from pinned dependency inventories')

    def used(self):
        return {name:sha for capsule in self.capsules.values()for name,sha in capsule.used.items()}


def timebase(inventory,capture):
    pending=[h for p,h in capture['input_sha256'].items()if p.endswith('/build.json')]
    visited=set();builds=[]
    while pending:
        sha=pending.pop()
        if sha in visited:continue
        visited.add(sha);doc=json.loads(inventory.by_digest(sha).read_text())
        if 'verilate_argv'in doc:builds.append(doc)
        else:pending.extend(h for p,h in doc.get('input_sha256',{}).items()if p.endswith('/build.json'))
    if len(builds)!=1:raise ValueError('Unique compiled source reference timebase required')
    build=builds[0];argv=build['verilate_argv']
    if argv.count('--timescale')!=1 or argv[argv.index('--timescale')+1]!='1ns/1ps':
        raise ValueError('Unqualified reference timescale')
    periods=[v.split('=',1)[1]for v in argv if v.startswith('+define+CLOCK_PERIOD=')]
    if len(periods)!=1:raise ValueError('Unique compiled TestDriver clock required')
    period=Decimal(periods[0])
    if not period.is_finite()or period<=0:raise ValueError('Invalid compiled period')
    drivers=[h for p,h in build['source_sha256'].items()if p.endswith('/TestDriver.v')]
    if len(drivers)!=1:raise ValueError('Exact source TestDriver required')
    text=inventory.by_digest(drivers[0]).read_text()
    if ('always #(`CLOCK_PERIOD/2.0) clock = ~clock;'not in text
            or text.count('trace_count = trace_count + 1;')!=1 or 'always @(posedge clock)'not in text):
        raise ValueError('Compiled source timestamp convention changed')
    return float(Decimal(10**9)/period),{'TestDriver_sha256':drivers[0],'CLOCK_PERIOD_ns':str(period),
        'coordinate':'Actual TestDriver trace_count; separate from per-hart mcycle.'}


def run(component,expected,case,output,nm):
    started=time.monotonic();component=Path(component).resolve();output=Path(output).resolve()
    inventory=Inventories(component,expected)
    if output.exists()or any(root==output or root in output.parents for root in inventory.capsules):
        raise ValueError('Fresh output outside every frozen dependency required')
    proof=inventory.root.document(inventory.root.manifest['proof'])
    if (proof.get('schema')!='iris.saturn_causal_ownership_numeric_proof.v1'or proof.get('pass')is not True
            or proof.get('continuous_state_replay')is not True
            or proof.get('numeric_payload_knownness_inferred')is not False
            or len(proof.get('negative_controls',[]))!=6
            or any(r.get('meaningful_refusal')is not True for r in proof['negative_controls'])):
        raise ValueError('Continuous source ownership replay and independent corruption refusals required')
    selected=[r for r in proof['positive_runs']if r['case']==case]
    if len(selected)!=3 or {r['seed']for r in selected}!={0,17,91}or any(r['exit_status']!=0 for r in selected):
        raise ValueError('Three independently qualified source reset seeds required')
    if any(r['result']!=selected[0]['result']for r in selected):raise ValueError('Source replay results differ across seeds')
    selected.sort(key=lambda r:r['seed'])
    stream_shas=[proof['artifact_sha256'][case+'-seed'+str(r['seed'])+'-events.ndjson.gz']for r in selected]
    if len(set(stream_shas))!=1:raise ValueError('Owned streams differ across independently replayed seeds')
    event_path=inventory.by_digest(stream_shas[0])
    receipts=[h for p,h in proof['input_sha256'].items()if p.endswith('/'+case+'/report.json')]
    if len(receipts)!=1:raise ValueError('Exact whole-RTL guest capture required')
    capture=json.loads(inventory.by_digest(receipts[0]).read_text())
    if (capture.get('schema')!='iris.saturn_ownership_actual_whole_RTL_run.v1'
            or capture.get('exit_status')!=0 or capture.get('timed_out')is not False
            or capture.get('same_architectural_signature_as_frozen_activity_run')is not True):
        raise ValueError('Actual source guest signature did not complete')
    elf_name=capture['argv'][-1];elf=inventory.by_digest(capture['input_sha256'][elf_name])
    hz,clock=timebase(inventory,capture)
    nm_path=Path(shutil.which(nm)or nm).resolve();nm_sha=digest(nm_path)
    table=symbols(elf,str(nm_path));instructions=Instructions(elf)
    counts={r['hart']:r['events']for r in selected[0]['result']['harts']}
    with projection_rows(event_path,stream_shas[0])as rows:
        summary,trace=profile(rows,instructions,table,hz,counts)
    inputs=inventory.used()
    source_paths=[Path(__file__),Path(__file__).with_name('saturn_owned_profile.py'),
        Path(__file__).with_name('saturn_profile_cli.py'),Path(__file__).with_name('guest_regions.py'),
        Path(__file__).with_name('report.py'),nm_path,Path(sys.executable).resolve()]
    inputs.update({str(p.resolve()):digest(p)for p in source_paths})
    if digest(nm_path)!=nm_sha:raise ValueError('Symbol reader changed during execution')
    if any(digest(name)!=sha for name,sha in inputs.items()):raise ValueError('Profile inputs changed')
    summary.update(case=case,source_timebase=clock,elf_sha256=digest(elf),ownership_stream_sha256=stream_shas[0],
        qualification='Exact owned physical events from this standalone source capture and ELF; not a native CPU graph or Ethan-image/timing certification.')
    output.mkdir(parents=True);snap=output/'inputs';snap.mkdir()
    for name,sha in inputs.items():
        if not(snap/sha).exists():shutil.copyfile(name,snap/sha)
        if digest(snap/sha)!=sha:raise ValueError('Profile input snapshot changed')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (output/'timeline.json').write_text(json.dumps(trace)+'\n')
    receipt={'schema':'iris.saturn_owned_profile_run.v1','pass':True,'input_sha256':inputs,
        'component_sha256':expected,'case':case,'host_seconds':time.monotonic()-started,
        'artifact_sha256':{name:digest(output/name)for name in ('summary.json','timeline.json')},
        'hardware_contacted':False,'whole_model_certified':False}
    (output/'report.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'pass':True,'case':case,'function_groups':len(summary['functions']),
        'physical_TL_transactions':len(summary['transport_transactions']),'host_seconds':receipt['host_seconds']}))


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--component',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--case',choices=['vme','rvv','fpcomp','shared-fpu'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--nm',default='nm');a=p.parse_args()
    try:run(a.component,a.sha256,a.case,a.output,a.nm)
    except(OSError,ValueError,KeyError,TypeError)as error:p.exit(2,'iris-owned-profile: '+str(error)+'\n')


if __name__=='__main__':main()
