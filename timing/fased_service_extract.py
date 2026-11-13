#!/usr/bin/env python3
"""Extract FASED timing units from the exact archived image RTL, not defaults."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
OBS=R/'build/firesim-observability-archived-driver-v3/report.json'
SRC=Path('/scratch/eygao/iris-cy/sims/firesim/sim')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ports(text):
    head=text[:text.index('\n);')]
    return [{'direction':direction,'name':name,'width':int(width.split(':')[0])+1 if width else 1} for direction,width,name in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',head,re.M)]
def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--output',type=Path,default=R/'build/fased-service-source-v1');args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise ValueError('fresh source audit required')
    inventory=json.loads(OBS.read_text());original=next(Path(p)for p in inventory['input_sha256']if p.endswith('/design/FireSim-generated.sv'));assert sha(original)==inventory['input_sha256'][str(original)]
    text=original.read_text();decls=list(re.finditer(r'^module\s+(\w+)',text,re.M));modules={}
    for i,match in enumerate(decls):
        end=text.find('\nendmodule',match.end());assert end>=0
        modules[match[1]]=text[match.start():end+len('\nendmodule')]+'\n'
    assert len(modules)==len(decls)
    selections={};missing={}
    for top in ['LatencyPipe','FASEDMemoryTimingModel']:
        todo=[top];closure=set();unknown=set()
        while todo:
            name=todo.pop()
            if name in closure:continue
            body=modules[name];closure.add(name)
            children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',body,re.M))
            children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?^\s*\)\s*\w+\s*\(',body,re.M))
            todo.extend(children & modules.keys()-closure)
            unknown.update(children-modules.keys()-{'module','end','if','else','while','case','for','assign','always','always_ff','always_comb','always_latch'})
        schema=ports(modules[top])
        for direction in ['input','output']:
            for index,field in enumerate(f for f in schema if f['direction']==direction and f['name']!='clock'):field['index']=index
        selections[top]={'modules':sorted(closure),'physical_ports':[f for f in schema if f['name']!='clock'],'unresolved_candidate_leaves':sorted(unknown)}
    out.mkdir();(out/'rtl').mkdir();shutil.copy2(original,out/'FireSim-generated.sv')
    selected=set().union(*(set(s['modules'])for s in selections.values()))
    for name in sorted(selected):(out/'rtl'/(name+'.sv')).write_text(modules[name])
    sourcefiles=[SRC/'midas/src/main/scala/midas/models/dram'/name for name in ['LatencyBandwidthPipe.scala','TimingModel.scala','Util.scala','EgressUnit.scala','IngressUnit.scala','FASEDMemoryTimingModel.scala']]+[SRC/'firesim-lib/src/main/scala/bridges/FASEDBridge.scala',SRC/'midas/src/main/cc/bridges/fased_memory_timing_model.cc',SRC/'midas/src/main/cc/bridges/fased_memory_timing_model.h']
    for p in sourcefiles:
        dest=out/'scala-driver-snapshot'/p.relative_to(SRC);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    repositories={}
    for name,path in [('firesim',SRC.parent),('chipyard',SRC.parents[2])]:
        prefix=['git','--no-optional-locks','-c','safe.directory='+str(path),'-C',str(path)]
        result=subprocess.run(prefix+['rev-parse','HEAD'],text=True,capture_output=True)
        diff=subprocess.run(prefix+['diff','--binary','HEAD'],capture_output=True)
        if result.returncode or diff.returncode:raise RuntimeError('read-only source pin failed: '+str(path))
        (out/(name+'-working-tree.patch')).write_bytes(diff.stdout)
        repositories[name]={'path':str(path),'HEAD':result.stdout.strip(),'dirty_diff_sha256':hashlib.sha256(diff.stdout).hexdigest(),'meaning':'Current source context only; complete association with archived image is unverified.'}
    report={'schema':'iris.archived_FASED_service_source.v1','source_image_observability_inventory':str(OBS),'source_image_observability_inventory_sha256':sha(OBS),'archived_SV':str(original),'archived_SV_sha256':sha(original),'archived_bitstream_sha256':next(v for p,v in inventory['input_sha256'].items()if p.endswith('/firesim.bit')),'archived_driver_sha256':inventory['driver_binary_sha256'],'image_source_units':selections,'selected_modules':len(selected),'extracted_files':{str(p.relative_to(out)):sha(p)for p in sorted((out/'rtl').iterdir())},'source_context_sha256':{str(p):sha(p)for p in sourcefiles},'repositories':repositories,'extractor_sha256':sha(__file__),'runtime_parameter_policy':'All timing values must be explicit provenance-bound inputs; observed startup30 is not a default admitted calibration.','interface_observation':{'target_AXI_data_bits':64,'target_AXI_address_bits':33,'target_AXI_ID_bits':4,'LatencyPipe_metadata_egress_external':True,'whole_FASED_token_and_functional_host_ports_external':True},'clock_policy':'LatencyPipe edges are model-target edges. FullFASED host edge advances target timing only when original targetFire accepts a token. CPU/uncore/serial conversion remains an external source-qualified gap.','hardware_contacted':False,'image_readback_attested':False,'complete_source_image_association':False,'calibration_usable':False,'timing_certified':False}
    (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'selected_modules':len(selected),'units':{k:len(v['modules'])for k,v in selections.items()},'unresolved_candidates':{k:v['unresolved_candidate_leaves']for k,v in selections.items()},'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
