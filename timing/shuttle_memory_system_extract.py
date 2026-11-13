#!/usr/bin/env python3
"""Extract exact Shuttle tile memory/PTW/TCM paths; retain parent glue and state."""
import argparse,collections,hashlib,json,re,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
CAP=R/'build/rtl-memory-return-path-v1-final'
SRC=CAP/'build/rtl-verilator/gen-collateral'
PIN='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c'
EXCLUDED={'core','frontend','dcache','vector_unit'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(s):
    head=s[:s.index('\n);')];return{n:{'direction':d,'width':int(w)+1 if w else 1}for d,w,n in re.findall(r'^\s*(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)',head,re.M)}
def instances(s):
    result=[]
    for m in re.finditer(r'^  (\w+) (\w+) \(',s,re.M):
        end=s.index('\n  );',m.end())+6;block=s[m.start():end]
        connections={}
        for pin in re.finditer(r'^\s*\.(\w+)\s*\(',block,re.M):
            depth=1;pos=pin.end();begin=pos
            while depth:
                assert pos<len(block),'unbalanced source connection'
                if block[pos]=='(':depth+=1
                elif block[pos]==')':depth-=1
                pos+=1
            connections[pin[1]]=block[begin:pos-1].strip()
        result.append({'module':m[1],'name':m[2],'block':block,'connections':connections,'source_line':s[:m.start()].count('\n')+1})
    return result
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('fresh source cut required')
    assert sha(CAP/'report.json')==PIN
    modules={}
    for directory in [SRC,R/'build/rtl-verilator/gen-collateral']:
        for q in directory.iterdir():
            if q.suffix in ['.sv','.v']:
                for name in re.findall(r'^module\s+(\w+)',q.read_text(),re.M):modules.setdefault(name,q)
    cuts={};sources={};wrappers={}
    plans=[('tile','ShuttleTile',None,'IrisShuttleMemoryTile'),('prci','TilePRCIDomain',{'buffer','buffer_1'},'IrisShuttleMemoryPRCI'),('uncore','DigitalTop',{'sbus_coupler_to_shuttle_tile'},'IrisShuttleMemoryUncore')]
    for kind,parent,chosen,top in plans:
        path=modules[parent];text=path.read_text();pp=ports(text)
        decls={n:int(w)+1 if w else 1 for w,n in re.findall(r'^\s*(?:input|output|wire|reg)\s+(?:\[(\d+):0\]\s+)?(\w+)',text,re.M)}
        regs={n for n in re.findall(r'^\s*reg\s+(?:\[[^]]+\]\s+)?(\w+)',text,re.M)}
        exprs={n:expr.strip()for n,expr in re.findall(r'^\s*assign\s+(\w+)\s*=\s*([\s\S]*?);',text,re.M)}
        exprs.update({n:expr.strip()for n,expr in re.findall(r'^\s*wire\s+(?:\[[^]]+\]\s+)?(\w+)\s*=\s*([\s\S]*?);',text,re.M)})
        all_instances=instances(text);selected=[x for x in all_instances if x['name']not in EXCLUDED]if chosen is None else[x for x in all_instances if x['name']in chosen]
        assert chosen is None or len(selected)==len(chosen)
        produced={};needed=set();consumed=collections.defaultdict(list);outside=set();clocknets=set();resetnets=set()
        def names(expr):return set(re.findall(r'\b[A-Za-z_]\w*\b',expr))&decls.keys()
        for inst in all_instances:
            info=ports(modules[inst['module']].read_text());assert inst['connections'].keys()==info.keys(),(parent,inst['name'],info.keys()-inst['connections'].keys())
            if inst not in selected:
                for n,expr in inst['connections'].items():
                    if info[n]['direction']=='input':outside.update(names(expr))
                continue
            inst['physical_ports']=info
            for n,expr in inst['connections'].items():
                fields=names(expr);needed.update(fields)
                if n=='clock'or n.endswith('_clock'):clocknets.update(fields)
                if n=='reset'or n.endswith('_reset'):resetnets.update(fields)
                if info[n]['direction']=='output':
                    if not re.sub(r'/\*.*?\*/','',expr).strip():continue
                    assert re.fullmatch(r'[A-Za-z_]\w*',expr),(parent,inst['name'],n,expr);assert expr not in produced;produced[expr]=(inst['name'],n)
                else:
                    for field in fields:consumed[field].append((inst['name'],n))
        # Preserve all original parent sequential glue in the tile cut. Its
        # four PTW address registers must never become external state inputs.
        sequential=''
        if kind=='tile':
            start=text.index('  always @');stop=text.index(all_instances[0]['block']);assert start<stop;sequential=text[start:stop];needed.update(regs);needed.update(names(sequential));assert len(regs)==4
        else:assert not(regs&needed),(kind,'unexpected parent state dependency')
        # Parent outputs remain source-declared observable boundaries; resolve
        # their expressions instead of asking a caller for their ready/state.
        needed.update(n for n,v in pp.items()if v['direction']=='output'and n in exprs and names(exprs[n])&produced.keys())
        owned_expr={};pending=list(needed)
        while pending:
            n=pending.pop()
            if n in produced or n in regs or n not in exprs or n in owned_expr:continue
            owned_expr[n]=exprs[n];dependencies=names(exprs[n]);pending.extend(dependencies-needed);needed.update(dependencies)
        assert len(clocknets)==1,(kind,clocknets)
        external=sorted(needed-produced.keys()-owned_expr.keys()-regs-clocknets)
        # Keep selected submodule output boundaries consumed by excluded peers,
        # original top-level outputs, and exact TCM request/response pins for
        # a read-only byte-definedness observer. No observer is an input.
        observer={}
        if kind=='tile':
            for inst in selected:
                if inst['name']in ['tcm','tcm_1']:
                    for pin,expr in inst['connections'].items():
                        if pin not in ['clock','reset']:observer[expr]=(inst['name'],pin)
        exported=set(n for n in produced if n in outside or n not in consumed or n in pp and pp[n]['direction']=='output')
        exported.update(n for n in pp if pp[n]['direction']=='output'and n in owned_expr);exported.update(observer)
        # Width declarations are inherited from the actual parent, including
        # widths prior to source part-selects/concatenations in child inputs.
        schema=[]
        for direction,ns in [('input',external),('output',sorted(exported))]:
            for index,n in enumerate(ns):schema.append({'name':n,'width':decls[n],'direction':direction,'index':index,'port':('i_'if direction=='input'else'o_')+str(index),'producer':produced.get(n),'parent_expression':owned_expr.get(n),'TCM_observer':observer.get(n),'reset':n in resetnets})
        preamble=text[:re.search(r'^module\s',text,re.M).start()]
        wrapper=preamble+'\n// Exact selected instances, original parent expressions and PTW sequential glue.\nmodule '+top+'(\n  input edge_clock,\n'+',\n'.join('  '+f['direction']+' '+('['+str(f['width']-1)+':0] 'if f['width']>1 else'')+f['port']for f in schema)+'\n);\n'
        wrapper+=''.join('  '+('reg'if n in regs else'wire')+' '+('['+str(decls[n]-1)+':0] 'if decls[n]>1 else'')+n+';\n'for n in sorted(needed))
        wrapper+='  assign '+next(iter(clocknets))+' = edge_clock;\n'
        for f in schema:wrapper+='  assign '+(f['name']+' = '+f['port']if f['direction']=='input'else f['port']+' = '+f['name'])+';\n'
        wrapper+=''.join('  assign '+n+' = '+expr+';\n'for n,expr in sorted(owned_expr.items()))
        wrapper+='\n'.join(x['block']for x in selected)+'\n'+sequential+'\nendmodule\n';wrappers[top]=wrapper
        closure={};todo=[x['module']for x in selected];unknown=set()
        while todo:
            name=todo.pop()
            if name in closure:continue
            q=modules[name];closure[name]=q;sources[str(q)]=sha(q);body=q.read_text();children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',body,re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?\)\s+\w+\s*\(',body,re.M));todo.extend(children&modules.keys()-closure.keys());unknown.update(children-modules.keys()-{'module','end','if','else','case','for','while','always','always_ff','always_comb','assign'})
        assert not unknown,(kind,unknown)
        cuts[kind]={'parent':parent,'parent_source':str(path),'parent_sha256':sha(path),'top':top,'selected_instances':selected,'physical_ports':schema,'parent_expression_nodes':owned_expr,'retained_parent_registers':sorted(regs)if kind=='tile'else[],'retained_parent_sequential_sha256':hashlib.sha256(sequential.encode()).hexdigest(),'retained_parent_preamble_sha256':hashlib.sha256(preamble.encode()).hexdigest(),'modules':sorted(closure),'input_count':len(external),'output_count':len(exported),'source_clock_net':next(iter(clocknets)),'wrapper_sha256':hashlib.sha256(wrapper.encode()).hexdigest()}
    out.mkdir();(out/'rtl').mkdir()
    for name,digest in sources.items():q=Path(name);shutil.copy2(q,out/'rtl'/q.name);assert sha(out/'rtl'/q.name)==digest
    for top,body in wrappers.items():(out/'rtl'/(top+'.sv')).write_text(body)
    for name in ['ShuttleTile','TilePRCIDomain','DigitalTop']:shutil.copy2(modules[name],out/(name+'-parent.sv'))
    report={'schema':'iris.shuttle_memory_paths_source.v1','source_capsule':str(CAP/'report.json'),'source_capsule_sha256':PIN,'source_FIR_sha256':json.loads((CAP/'report.json').read_text())['source_fir_sha256'],'cuts':cuts,'source_files':sources,'extracted_files':{q.name:sha(q)for q in sorted((out/'rtl').iterdir())},'extractor_sha256':sha(__file__),'clock_policy':'Actual Shuttle tile/PRCI/uncore memory paths use synchronous TLBuffers on the qualified uncore clock; no invented Rocket-style asynchronous crossing. Memory/coherence continues while CPU pipeline sleeps.','width_policy':'CPU/cache64; frontend64; SaturnATL256; tile crossbar256; source tile system-master64; slaveTCM256; preserve every instantiated width widget.','cache_policy':'ShuttleDCache remains separate frozen guarded SDK; RefuseUse default, no assumed seeded initialization.','hardware_contacted':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False}
    (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'cuts':{k:{'inputs':v['input_count'],'outputs':v['output_count'],'modules':len(v['modules']),'parent_regs':v['retained_parent_registers']}for k,v in cuts.items()},'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
