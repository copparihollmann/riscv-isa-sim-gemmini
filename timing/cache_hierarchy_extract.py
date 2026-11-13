#!/usr/bin/env python3
"""Extract exact saved scalar L1D and four-bank inclusive L2 RTL; add no logic."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
RTL=CAP/'build/rtl-verilator/gen-collateral'
PIN='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c'
COMPONENTS={'shuttle':'ShuttleDCache','rocket':'DCache','l2':'InclusiveCache'}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ports(text):
    module=re.search(r'^module\s+(\w+)\(',text,re.M)
    if not module:raise ValueError('plain saved module declaration required')
    stop=text.index('\n);',module.end())
    result=[]
    for direction,width,name in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',text[module.end():stop],re.M):
        bits=int(width.split(':')[0])+1 if width else 1
        if width and int(width.split(':')[1])!=0:raise ValueError('nonzero lower physical port bound')
        result.append({'name':name,'direction':direction,'width':bits})
    return result

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-source-v1')
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('fresh extraction directory required')
    if sha(CAP/'report.json')!=PIN:raise ValueError('saved whole-SoC source capsule identity changed')
    files={}
    for directory in (RTL,ROOT/'build/rtl-verilator/gen-collateral'):
        for path in sorted(directory.iterdir()):
            if path.suffix not in ('.sv','.v'):continue
            for name in re.findall(r'^module\s+(\w+)',path.read_text(),re.M):
                files.setdefault(name,path)
    selected={};components={}
    for kind,top in COMPONENTS.items():
        todo=[top];closure={}
        while todo:
            name=todo.pop()
            if name in closure:continue
            path=files[name];text=path.read_text();closure[name]=path;selected[path.name]=path
            children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',text,re.M))
            children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?^\s*\)\s*\w+\s*\(',text,re.M))
            todo.extend(sorted(children&files.keys()-closure.keys()))
        physical=ports(files[top].read_text())
        assert sum(p['name']=='clock'and p['direction']=='input'for p in physical)==1
        assert sum(p['name']=='reset'and p['direction']=='input'for p in physical)==1
        for direction in ('input','output'):
            for index,port in enumerate(p for p in physical if p['direction']==direction and p['name']!='clock'):
                port['index']=index
        components[kind]={'top':top,'modules':sorted(closure),'physical_ports':[p for p in physical if p['name']!='clock'],
                          'input_count':sum(p['direction']=='input'and p['name']!='clock'for p in physical),
                          'output_count':sum(p['direction']=='output'for p in physical)}
    out.mkdir();(out/'rtl').mkdir()
    for name,path in selected.items():shutil.copyfile(path,out/'rtl'/name)
    manifest=json.loads((CAP/'report.json').read_text())
    report={'schema':'iris.cache_hierarchy_source_cut.v1','components':components,
        'source_capsule':str(CAP/'report.json'),'source_capsule_sha256':PIN,
        'source_fir_sha256':manifest['source_fir_sha256'],'source_design':manifest['source_design'],
        'source_memory_lowering':manifest['source_memory_lowering'],
        'source_files':{str(p):sha(p)for p in selected.values()},
        'extracted_files':{name:sha(out/'rtl'/name)for name in selected},
        'extractor_sha256':sha(Path(__file__)),'clock_edges_added':0,'RTL_logic_changed':False,
        'input_service_inferred':False,'deployed_image_association_verified':False,
        'full_rtl_certified':False,'timing_certified':False,'hardware_contacted':False}
    (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'components':{k:{'modules':len(v['modules']),'inputs':v['input_count'],'outputs':v['output_count']}for k,v in components.items()},
        'total_modules':len(selected),'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
