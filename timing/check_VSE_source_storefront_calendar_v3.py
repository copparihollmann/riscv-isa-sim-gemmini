#!/usr/bin/env python3
"""Refuse clock mappings that the native/source edge join does not represent."""
from pathlib import Path
import argparse,json
from check_VSE_live_boundary_native_v1 import R,F,execute,sha
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir();b=R/'build/spike-VSE-source-storefront-v2';cases=[]
 for name,old,new in[('wrong-base','base_hz 500000000','base_hz 1000000000'),('wrong-hart-period','hart 0 1 source','hart 0 2 source'),('overflow-master-tick','max_cycles 100000000000','max_cycles 18446744073709551615')]:
  text=F.read_text();assert text.count(old)==1;text=text.replace(old,new);f=o/(name+'.fixture');f.write_text(text+'\nexperimental_vse_boundary SOURCE-STOREFRONT-SYNTHETIC-D-ONLY-v2 0 20 core_edges\n');d=o/name;r=execute(d,b/'spike',b/'libsifive_uart.so',f,R/'build/VSE-live-boundary-guest-h0-v1/guest.elf');passed=r['exit_status']not in(None,0)and not r['timed_out']and(('invalid timing parameter: 18446744073709551615'if name=='overflow-master-tick'else'IRIS_VSE_SOURCE_REQUIRES_BASE500MHZ_HART500MHZ_MASTER1GHZ')in(d/'stderr').read_text())and not(d/'stdout').read_bytes();cases.append(dict(name=name,**{'pass':passed},run=r))
 report=dict(schema='iris.VSE_source_storefront_calendar_guards.v2',**{'pass':all(x['pass']for x in cases)},cases=cases,input_sha256={str(x):sha(x)for x in[Path(__file__),b/'pipeline-build.json']});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
