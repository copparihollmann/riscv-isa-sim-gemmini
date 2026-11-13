#!/usr/bin/env python3
"""Actual native malformed-directive / explicit-mode admission controls."""
import argparse,json,os,subprocess
from pathlib import Path
from scalar_l2_hit_run import ROOT,sha
def main(cap,out):
    base=(ROOT/'build/scalar-L2hit-inputs-v1/OFF.fixture').read_text();argv=json.loads((ROOT/'build/scalar-outer-guard-v2-0-OFF/run.json').read_text())['argv'];argv[0]=str(cap/'spike');argv=['--extlib='+str(cap/'libsifive_uart.so')if x.startswith('--extlib=')else x for x in argv];out.mkdir(exist_ok=False,parents=True)
    valid='empirical_scalar_outer_response 0 1 SYNTHETIC '+('0'*64)+' core_cycles\n'
    cases={
        'hart':'empirical_scalar_outer_response 3 1 SYNTHETIC '+('0'*64)+' core_cycles\n',
        'negative':valid.replace('0 1 SYNTHETIC','0 -1 SYNTHETIC'),
        'nonfinite':valid.replace('0 1 SYNTHETIC','0 nan SYNTHETIC'),
        'units':valid.replace('core_cycles','base_cycles'),
        'provenance':valid.replace('0'*64,'unbound'),
        'duplicate':valid+valid,
        'horizon':valid.replace('0 1 SYNTHETIC','0 100000000001 SYNTHETIC'),
        'no-profile':valid,
        'random-selector':'empirical_dcache_random not-a-source-selector\n',
    };results=[]
    for name,extra in cases.items():
        d=out/name;d.mkdir();text=base
        if name=='no-profile':text='\n'.join(l for l in base.splitlines()if not l.startswith('empirical_'))+'\n'
        f=d/'fixture';f.write_text(text+'\n'+extra)
        cmd=[('--iris-timing-fixture='+str(f))if x.startswith('--iris-timing-fixture=')else('--iris-timing-trace='+str(d/'summary.json'))if x.startswith('--iris-timing-trace=')else x for x in argv]
        r=subprocess.run(cmd,capture_output=True,timeout=15);(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
        if r.returncode==0 or not r.stderr or b'IRIS_SCALAR_OUTER_GUARD 'in r.stdout:raise ValueError('Malformed directive admitted '+name)
        results.append({'name':name,'exit_status':r.returncode,'stderr':r.stderr.decode().strip(),'refused_before_guest':True,'fixture_sha256':sha(f)})
    paths=[Path(__file__).resolve(),cap/'manifest.json',cap/'spike',cap/'libsifive_uart.so',ROOT/'build/scalar-L2hit-inputs-v1/OFF.fixture'];report={'schema':'iris.scalar_outer_response_native_parser_guards.v2','pass':True,'refusals':results,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in paths}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'refusals':len(results),'sha256':sha(out/'report.json')}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--capsule',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.capsule.resolve(),a.output.resolve())
