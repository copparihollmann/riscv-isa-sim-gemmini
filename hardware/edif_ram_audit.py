#!/usr/bin/env python3
"""Audit explicit synthesized RPQ RAM INIT properties and containing hierarchy.

The supported writer format is the decoded Vivado EDIF text. Physical RAM
slice properties are retained verbatim, never treated as original RTL bit
positions or as loaded-FPGA initialization evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from checkpoint_edif import digest


TOKEN=re.compile(r'\s*(\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+)')
NAME=re.compile(r'\s*(?:\(rename\s+([^\s()"]+)\s+"((?:\\.|[^"\\])*)"\)|([^\s()"]+))',re.IGNORECASE)
REFERENCE=re.compile(r'\(cellref\s+([^\s()]+)\s*(?:\(libraryref\s+([^\s()]+)\))?\)',re.IGNORECASE)
QUOTED=re.compile(r'"(?:\\.|[^"\\])*"')


def delta(line):
    masked=QUOTED.sub('""',line)
    if masked.count('"')%2:raise ValueError('Unsupported multiline EDIF string')
    return masked.count('(')-masked.count(')')


def expression(text):
    tokens=[];position=0
    while position<len(text):
        match=TOKEN.match(text,position)
        if match is None:
            if text[position:].strip():raise ValueError('Unsupported EDIF token')
            break
        tokens.append(match.group(1));position=match.end()
    stack=[];root=None
    for token in tokens:
        if token=='(':
            node=[]
            if stack:stack[-1].append(node)
            elif root is not None:raise ValueError('Multiple EDIF expressions')
            else:root=node
            stack.append(node)
        elif token==')':
            if not stack:raise ValueError('Unmatched EDIF close')
            stack.pop()
        else:
            if not stack:raise ValueError('EDIF atom outside expression')
            stack[-1].append(token[1:-1]if token.startswith('"')else token)
    if stack or root is None:raise ValueError('Truncated EDIF expression')
    def keywords(node):
        if node and isinstance(node[0],str):node[0]=node[0].lower()
        for child in node:
            if isinstance(child,list):keywords(child)
    keywords(root)
    return root


def name(text):
    match=NAME.match(text)
    if not match:raise ValueError('Unsupported EDIF name definition')
    return match.group(1)or match.group(3),match.group(2)or match.group(3)


def identifier(value):
    if isinstance(value,str):return value,value
    if isinstance(value,list)and len(value)==3 and value[0]=='rename':return value[1],value[2]
    raise ValueError('Unsupported EDIF name')


def ram_instance(text,cell,start,end):
    node=expression(text)
    if len(node)<3 or node[0]!='instance':raise ValueError('Exact instance expression required')
    raw,display=identifier(node[1]);view=[n for n in node[2:]if isinstance(n,list)and n and n[0]=='viewref']
    if len(view)!=1:raise ValueError('Unique instance view required')
    refs=[n for n in view[0][2:]if isinstance(n,list)and n and n[0]=='cellref']
    if len(refs)!=1:raise ValueError('Unique primitive reference required')
    primitive=refs[0][1];properties={}
    for prop in node[2:]:
        if not isinstance(prop,list)or not prop or prop[0]!='property':continue
        if len(prop)!=3 or not isinstance(prop[2],list)or len(prop[2])!=2:
            raise ValueError('Unsupported primitive property form')
        if prop[1]in properties:raise ValueError('Duplicate primitive property')
        properties[prop[1]]={'type':prop[2][0],'value':prop[2][1]}
    if 'RTL_RAM_NAME'not in properties or '/rpq/ram_flattened_reg'not in properties['RTL_RAM_NAME']['value']:
        raise ValueError('Selected instance does not identify RPQ RAM')
    initials={k:v['value']for k,v in properties.items()if k=='INIT'or k.startswith('INIT_')}
    values={};widths={}
    for key,literal in initials.items():
        match=re.fullmatch(r"([0-9]+)'([bBhHdD])([0-9a-fA-F_]+)",literal)
        if not match:raise ValueError('Unknown/unsupported explicit RAM INIT literal')
        width=int(match.group(1));base={'b':2,'h':16,'d':10}[match.group(2).lower()]
        value=int(match.group(3).replace('_',''),base)
        if width<=0 or value>=2**width:raise ValueError('RAM INIT literal exceeds declared width')
        values[key]=value;widths[key]=width
    complete=primitive=='RAM32M16'and set(initials)=={'INIT_'+letter for letter in'ABCDEFGH'}and set(widths.values())=={64}
    return {'cell_library':cell[0],'cell':cell[1],'instance':raw,'display_instance':display,
        'primitive':primitive,'source_lines':[start,end],'instance_expression_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'properties':properties,'explicit_INIT_literals':initials,
        'all_explicit_INIT_values_zero':bool(values)and all(v==0 for v in values.values()),
        'all_RAM32M16_INIT_parameters_explicit':complete,
        'logical_RTL_cmd_INIT_certified':False,'loaded_FPGA_INIT_certified':False}


class HierarchyError(ValueError):
    def __init__(self,message,diagnostic):
        super().__init__(message);self.diagnostic=diagnostic


def hierarchy_paths(top,targets,edges,limit=10000):
    result={target:[]for target in targets}
    def walk(cell,path,active):
        if cell in active:raise ValueError('Recursive EDIF cell hierarchy')
        if cell in result:
            if len(result[cell])>=limit:raise ValueError('Hierarchy path bound exceeded')
            result[cell].append(path)
        for instance,child in edges.get(cell,[]):
            walk(child,path+[instance],active|{cell})
    walk(top,[],set())
    if any(not paths for paths in result.values()):
        missing={cell for cell,paths in result.items()if not paths}
        raise HierarchyError('RPQ RAM cell is unreachable from actual design root',{
            'top':list(top),'path_counts':{'/'.join(cell):len(paths)for cell,paths in result.items()},
            'incoming_references_to_unreachable':[{'parent':list(parent),'instance':instance,'child':list(child)}
                for parent,children in edges.items()for instance,child in children if child in missing],
            'root_children':[{'instance':instance,'child':list(child)}for instance,child in edges.get(top,[])]})
    return result


def scan(stream):
    library=None;cell=None;pending=None;design=None;definitions=set();edges={};records=[];markers=0;sha=hashlib.sha256()
    for number,raw in enumerate(stream,1):
        sha.update(raw);line=raw.decode('utf-8');stripped=line.lstrip();indent=len(line)-len(stripped)
        head=stripped[:12].lower()
        if 'RTL_RAM_NAME'in line and '/rpq/ram_flattened_reg'in line:markers+=1
        if pending is not None:
            pending['lines'].append(line);pending['bytes']+=len(raw)
            pending['depth']+=delta(line)
            if pending['bytes']>8*1024**2:raise ValueError('EDIF instance block bound exceeded')
            if pending['depth']<0:raise ValueError('EDIF block closes outside its expression')
            if pending['depth']==0:
                block=''.join(pending['lines'])
                if pending['kind']=='design':
                    if design is not None:raise ValueError('Multiple EDIF designs')
                    design=expression(block)
                elif '/rpq/ram_flattened_reg'in block:
                    records.append(ram_instance(block,pending['cell'],pending['start'],number))
                pending=None
            continue
        if head.startswith('(library ')or head.startswith('(external '):
            library=name(stripped.split(' ',1)[1])[0]
        elif head.startswith('(cell '):
            if library is None:raise ValueError('Cell outside known library')
            cell=(library,name(stripped[len('(cell '):])[0])
            if cell in definitions:raise ValueError('Duplicate EDIF cell definition')
            definitions.add(cell)
        elif head.startswith('(instance '):
            if cell is None:raise ValueError('Instance outside known cell')
            instance=name(stripped[len('(instance '):])[0];reference=REFERENCE.search(stripped)
            if reference is None:raise ValueError('Unsupported multiline instance-reference header')
            child=(reference.group(2)or library,reference.group(1))
            if child[0]!='hdi_primitives':edges.setdefault(cell,[]).append((instance,child))
            depth=delta(line)
            if depth<0:raise ValueError('Invalid inline instance expression')
            if depth==0:
                if '/rpq/ram_flattened_reg'in line:records.append(ram_instance(line,cell,number,number))
            else:pending={'kind':'instance','lines':[line],'bytes':len(raw),'depth':depth,'cell':cell,'start':number}
        elif head.startswith('(design '):
            pending={'kind':'design','lines':[line],'bytes':len(raw),'depth':delta(line),'cell':None,'start':number}
    if pending is not None or design is None:raise ValueError('Unfinished instance or missing design root')
    refs=[v for v in design[2:]if isinstance(v,list)and v and v[0]=='cellref']
    if len(refs)!=1:raise ValueError('Unique actual design root required')
    libraries=[v for v in refs[0][2:]if isinstance(v,list)and v and v[0]=='libraryref']
    if len(libraries)!=1:raise ValueError('Explicit design-root library required')
    top=(libraries[0][1],refs[0][1])
    if top not in definitions:raise ValueError('Design root has no cell definition')
    if markers!=len(records)or not records:raise ValueError('Not every RPQ RAM property belongs to one complete captured instance')
    targets={(r['cell_library'],r['cell'])for r in records}
    paths=hierarchy_paths(top,targets,edges)
    for record in records:record['cell_instance_paths']=paths[(record['cell_library'],record['cell'])]
    return {'top_cell':list(top),'cell_definitions':len(definitions),'nonprimitive_hierarchy_edges':sum(map(len,edges.values())),
        'RPQ_property_count':markers,'instances':records,'edif_sha256':sha.hexdigest()}


def audit(receipt,expected,output):
    if output.exists():raise ValueError('Fresh audit directory required')
    if digest(receipt)!=expected:raise ValueError('Pinned decode receipt digest required')
    decoded=json.loads(receipt.read_text());edif=receipt.parent/'netlist.edf'
    if decoded.get('status')!='decoded_text_and_lexical_balance_verified':raise ValueError('Complete decoded text required')
    started=time.monotonic();output.mkdir(parents=True)
    report={'schema':'iris.synthesized_RPQ_RAM_INIT_audit.v1','status':'running',
        'decode_receipt_sha256':expected,'checkpoint_sha256':decoded['checkpoint_sha256'],
        'source_sha256':digest(Path(__file__)),'hardware_contacted':False,
        'logical_RTL_cmd_INIT_certified':False,'loaded_FPGA_INIT_certified':False}
    try:
        with edif.open('rb')as source:result=scan(source)
        if result['edif_sha256']!=decoded['decoded_edif_sha256']:raise ValueError('Decoded netlist bytes changed')
        if digest(receipt)!=expected:raise ValueError('Decode receipt changed during audit')
        report.update(status='explicit_synthesized_primitive_properties_audited',**result)
        report['scope']='Exact synthesized physical INIT properties and actual root-to-cell paths. RTL packing may be optimized/reordered; no logical command value, implementation preservation or loaded-image state is inferred.'
    except(OSError,ValueError,KeyError,TypeError)as error:
        report.update(status='failed',error=str(error))
        if isinstance(error,HierarchyError):report['hierarchy_diagnostic']=error.diagnostic
    report['host_seconds']=time.monotonic()-started
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k)for k in('status','RPQ_property_count','error','host_seconds')}))
    return 0 if report['status']=='explicit_synthesized_primitive_properties_audited'else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--decode-receipt',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();raise SystemExit(audit(a.decode_receipt.resolve(),a.sha256,a.output.resolve()))
