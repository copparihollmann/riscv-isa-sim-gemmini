#!/usr/bin/env python3
"""Mechanically extract both complete NoC fabrics and every TL adaptor."""
import argparse,collections,hashlib,json,re,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';SRC=CAP/'build/rtl-verilator/gen-collateral'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(text):
 result={}
 for direction,width,name in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)[, \t]*//',text,re.M):result[name]={'direction':direction,'width':int(width.split(':')[0])+1 if width else 1}
 return result
def identifiers(expression):
 expression=re.sub(r"\b\d+'[sS]?[hHdDbBoO][0-9a-fA-FxXzZ_?]+",'0',expression)
 return set(re.findall(r'\b[A-Za-z_][A-Za-z0-9_$]*\b',expression))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/noc-network-source-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh extraction output required')
 assert sha(CAP/'report.json')=='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c'
 parent=SRC/'DigitalTop.sv';text=parent.read_text();decls={n:int(w.split(':')[0])+1 if w else 1 for w,n in re.findall(r'^\s*(?:input|output|wire|reg)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',text,re.M)};instances=[];produced={};consumed=collections.defaultdict(list);allnets=set();clocknets=set();resetnets=set()
 for m in re.finditer(r'^  (\w+) (sbus_system_bus_noc_\w+) \(',text,re.M):
  end=text.find('\n  );',m.end());assert end>0;block=text[m.start():end+6];mod=m[1];name=m[2];info=ports((SRC/(mod+'.sv')).read_text());connections={}
  for line in block.splitlines()[1:]:
   line=line.split('//')[0].strip();c=re.fullmatch(r'\.(\w+)\s*\((.*)\),?',line)
   if not c:continue
   port,expression=c.groups();assert port in info,(mod,port);connections[port]={'expression':expression,**info[port]};nets=identifiers(expression);assert nets<=decls.keys(),(mod,port,nets-decls.keys());allnets|=nets
   if port=='clock'or port.endswith('_clock'):clocknets|=nets
   if port=='reset'or port.endswith('_reset'):resetnets|=nets
   if info[port]['direction']=='output':
    assert re.fullmatch(r'\w+',expression),('Nontrivial selected output',mod,port,expression);assert expression not in produced,('Multiple selected drivers',expression);produced[expression]=(name,port)
   else:
    for net in nets:consumed[net].append((name,port))
  assert connections.keys()==info.keys(),('Incomplete selected instance',name,info.keys()-connections.keys());instances.append({'module':mod,'name':name,'source_start_line':text[:m.start()].count('\n')+1,'connections':connections,'source_block':block})
 assert len(instances)==40 and len(clocknets)==len(resetnets)==1
 inputs=sorted(allnets-produced.keys()-clocknets);outputs=sorted(n for n in produced if n not in consumed or any('tilelink' in port for inst in instances if inst['name']==produced[n][0]for port in [produced[n][1]]));internal=sorted(allnets-set(inputs)-set(outputs)-clocknets)
 schema=[]
 for direction,nets in [('input',inputs),('output',outputs)]:
  for index,name in enumerate(nets):schema.append({'direction':direction,'index':index,'name':name,'port':('i_'if direction=='input'else'o_')+str(index),'width':decls[name],'producer':produced.get(name),'consumers':consumed.get(name,[]),'reset':name in resetnets})
 assert max(x['width']for x in schema)<=64
 out.mkdir();rtl=out/'rtl';rtl.mkdir();selected={x['module']for x in instances};pending=list(selected);sources={}
 while pending:
  name=pending.pop()
  if name in sources:continue
  file=SRC/(name+'.sv')
  if not file.exists():file=R/'build/rtl-verilator/gen-collateral'/(name+'.v')
  assert file.is_file(),name;sources[name]=file;source=file.read_text();children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',source,re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?^\s*\)\s*\w+\s*\(',source,re.M))
  for child in children:
   if (SRC/(child+'.sv')).exists()or(R/'build/rtl-verilator/gen-collateral'/(child+'.v')).exists():pending.append(child)
 for name,file in sources.items():shutil.copyfile(file,rtl/file.name)
 top='// Mechanical connectivity cut from exact saved DigitalTop; no added state.\nmodule IrisNoCNetwork(\n  input clock,\n'+',\n'.join('  '+x['direction']+' '+('['+str(x['width']-1)+':0] 'if x['width']>1 else'')+x['port']for x in schema)+'\n);\n'
 top+=''.join('  wire '+('['+str(decls[n]-1)+':0] 'if decls[n]>1 else'')+n+';\n'for n in sorted(allnets))
 top+='  assign '+next(iter(clocknets))+' = clock;\n'
 for x in schema:top+='  assign '+(x['name']+' = '+x['port']if x['direction']=='input'else x['port']+' = '+x['name'])+';\n'
 top+='\n'.join(x['source_block']for x in instances)+'\nendmodule\n';(rtl/'IrisNoCNetwork.sv').write_text(top)
 root=(CAP/'build/rtl-verilator/model/VTestDriver___024root.h').read_text();prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';members=set(re.findall(r'\s(\w+);',root));visibility=[]
 for x in schema:visibility.append({**{k:v for k,v in x.items()if k in['direction','index','name','port','width','reset']},'cached_whole_rtl_member':prefix+x['name'],'directly_public':prefix+x['name']in members})
 report={'schema':'iris.complete_noc_source_cut.v1','source_parent':str(parent),'source_parent_sha256':sha(parent),'source_capsule_sha256':sha(CAP/'report.json'),'source_files':{str(p):sha(p)for p in sources.values()},'wrapper_sha256':sha(rtl/'IrisNoCNetwork.sv'),'instances':instances,'physical_ports':schema,'internal_net_count':len(internal),'clock_source_net':next(iter(clocknets)),'reset_source_net':next(iter(resetnets)),'router_clock_domains':sum('router_'in x['module']for x in instances),'TL_network_adaptors':sum('ToNoC'in x['module']for x in instances),'modules':len(sources),'cached_visibility':visibility,'hardware_contacted':False,'timing_certified':False}
 (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'instances':len(instances),'routers':report['router_clock_domains'],'TL_adaptors':report['TL_network_adaptors'],'modules':len(sources),'input_fields':len(inputs),'output_fields':len(outputs),'direct_public':sum(x['directly_public']for x in visibility),'missing_public':sum(not x['directly_public']for x in visibility),'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
