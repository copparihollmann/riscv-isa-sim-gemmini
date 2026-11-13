#!/usr/bin/env python3
"""Bind source control/state and protocol ports to real read-only native members."""
import argparse
from collections import defaultdict, deque
import hashlib
import json
import re
from pathlib import Path
from saturn_timing_activity_extract import cpp_fields, modules

R=Path(__file__).resolve().parents[1]
REFERENCE=R/'build/saturn-timing-component-v1-final'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def aliases(definitions,top):
    graph=defaultdict(set)
    def connect(a,b):
        graph[a].add(b);graph[b].add(a)
    def visit(module,path):
        info=definitions[module];text=info['path'].read_text()
        for match in re.finditer(r'^  assign (\w+) = (\w+);',text,re.M):
            connect('.'.join([*path,match[1]]),'.'.join([*path,match[2]]))
        for match in re.finditer(r'^  (\w+) (\w+) \((.*?)^  \);',text,re.M|re.S):
            child,instance,body=match.groups()
            if child not in definitions:continue
            for port in re.finditer(r'^\s*\.(\w+)\s*\((\w+)\)',body,re.M):
                connect('.'.join([*path,instance,port[1]]),'.'.join([*path,port[2]]))
        for instance,child in info['instances'].items():
            if child in definitions:visit(child,[*path,instance])
    visit(top,[])
    return graph

def resolve(name,top,prefix,available,width,graph,preferred=None):
    if preferred in available and available[preferred]==width:return preferred
    queue=deque([name]);seen={name}
    while queue:
        logical=queue.popleft();member=prefix+'__DOT__'.join(logical.split('.'))
        if member in available and available[member]==width:return member
        for other in sorted(graph[logical]):
            if other not in seen:seen.add(other);queue.append(other)
    return None

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--state-schema',type=Path,required=True)
    parser.add_argument('--protocol-ports',type=Path,required=True)
    parser.add_argument('--compute-model',type=Path,required=True)
    parser.add_argument('--rocket-model',type=Path,required=True)
    parser.add_argument('--whole-header',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=json.loads(args.state_schema.read_text());ports=json.loads(args.protocol_ports.read_text())
    whole=cpp_fields(args.whole_header)
    result={'schema':'iris.saturn_typed_internal_activity.v1','profiles':{},
            'reference_sha256':sha(REFERENCE/'report.json'),
            'input_sha256':{str(p.resolve()):sha(p)for p in[Path(__file__),args.state_schema,args.protocol_ports,args.whole_header]},
            'only_source_simple_aliases_resolved':True,'internal_state_inputs_added':False,
            'raw_payload_is_not_automatically_known':True,'hardware_contacted':False}
    for key,model,prefix in [('compute',args.compute_model,'VSaturnCompute'),('rocket',args.rocket_model,'VSaturnRocket')]:
        top=state['profiles'][key]['top_module'];header=model/(prefix+'___024root.h')
        result['input_sha256'][str(header.resolve())]=sha(header)
        native=cpp_fields(header);definitions=modules(REFERENCE/'build/saturn-timing-source-v1'/key/'rtl');graph=aliases(definitions,top)
        combined={}
        for field in state['profiles'][key]['fields']:
            combined[field['name']]={**field,'roles':[field['role']]}
        for field in ports['profiles'][key]['fields']:
            name=field['name']
            if name in combined:combined[name]['roles'].append('protocol')
            else:combined[name]={**field,'roles':['protocol']}
        fields=[];missing=[];word=0
        for name,item in sorted(combined.items()):
            width=item['width'];member=resolve(name,top,top+'__DOT__',native,width,graph,item.get('fast_member'))
            gold=[]
            for hart in([0,1]if key=='compute'else[2]):
                parent='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain'+('_'+str(hart)if hart else'')+'__DOT__element_reset_domain_'+('rockettile'if hart==2 else'shuttle_tile')+'__DOT__vector_unit__DOT__'
                gold.append({'hart':hart,'member':resolve(name,top,parent,whole,width,graph)})
            if member is None or any(g['member']is None for g in gold):
                missing.append({'name':name,'roles':item['roles'],'native_missing':member is None,'whole_missing_harts':[g['hart']for g in gold if g['member']is None]})
                continue
            words=[]
            for lo in range(0,width,64):
                words.append({'lo':lo,'width':min(64,width-lo),'index':word});word+=1
            fields.append({**item,'member':member,'whole_members':gold,'words':words})
        result['profiles'][key]={'top_module':top,'prefix':prefix,'fields':fields,'unresolved':missing,'word_count':word}
        if any('protocol'in f['roles']for f in missing):
            (out/'unresolved.json').write_text(json.dumps(result,indent=2)+'\n')
            raise ValueError('Required real protocol port could not be bound '+key)
    (out/'schema.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'profiles':{k:{'fields':len(v['fields']),'words':v['word_count'],'unresolved':len(v['unresolved'])}for k,v in result['profiles'].items()},'schema_sha256':sha(out/'schema.json')}))

if __name__=='__main__':main()
