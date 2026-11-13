#!/usr/bin/env python3
"""Cut the archived MBUS/SerialTL/BringupSoC path at real physical ports."""
import argparse,hashlib,json,re,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fields(body):
    head=body[:body.index('\n);')]
    return [{'direction':d,'width':int(w.split(':')[0])+1 if w else 1,'name':n}for d,w,n in re.findall(r'^\s*(input|output)\s+(?:\[(\d+:\d+)\]\s+)?(\w+)',head,re.M)]
def instance(body,kind,name):
    m=re.search(r'^  '+re.escape(kind)+r' '+re.escape(name)+r' \([\s\S]*?^  \);',body,re.M);assert m,(kind,name)
    return {n:v.strip() for n,v in re.findall(r'^\s*\.(\w+)\(([\s\S]*?)\)(?:,|\s|$)',m[0],re.M)}
def assignments(body):return {a:b.strip()for a,b in re.findall(r'^  assign (\w+)\s*=\s*(.*?);',body,re.M|re.S)}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/fased-service-source-v2');p.add_argument('--output',type=Path,required=True);a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh source extraction required')
    base=json.loads((source/'extraction.json').read_text());sv=source/'FireSim-generated.sv';assert sha(sv)==base['archived_SV_sha256'];s=sv.read_text()
    modules={m[1]:s[m.start():s.index('\nendmodule',m.end())+len('\nendmodule')]+'\n'for m in re.finditer(r'^module\s+(\w+)',s,re.M)}
    helper=R/'build/rtl-verilator/gen-collateral/plusarg_reader.v';helper_text=helper.read_text();current_helper=Path('/scratch/eygao/iris-cy/generators/rocket-chip/src/main/resources/vsrc/plusarg_reader.v')
    assert helper_text.strip()==current_helper.read_text().strip()
    assert sha(helper)=='08de6a683d07eb22091e793d97fdcfa74b14ec35cac33ad0e2efce0a8e0337bc'
    modules['plusarg_reader']=helper_text
    digital=modules['DigitalTop'];mbus=instance(digital,'MemoryBus','mbus');serial=instance(digital,'SerialTL1ClockSinkDomain','serial_tl_domain_1');alias=assignments(digital)
    def reduced(expr):
        seen=set()
        while expr in alias:
            assert expr not in seen;seen.add(expr);expr=alias[expr]
        return expr
    top_ports=[];wiredecl=[];inst=[];joins=[];exports=[]
    def port(d,n,w):top_ports.append({'direction':d,'name':n,'width':w});return n
    def wire(n,w):wiredecl.append('  wire '+('['+str(w-1)+':0] 'if w>1 else'')+n+';');return n
    # External reset values are the actual Iris uncore reset at these cut
    # ports and BringupSoC reset_io, not an inferred common reset waveform.
    for n in ['iris_clock','bringup_clock','serial_clock','iris_reset','bringup_reset']:port('input',n,1)
    allpins={};mbfields=fields(modules['MemoryBus']);serfields=fields(modules['SerialTL1ClockSinkDomain']);brfields=fields(modules['ChipTop_1'])
    mbby={x['name']:x for x in mbfields};sprefix='auto_serdesser_manager_in_';mprefix='auto_coupler_to_port_named_serial_tl_1_out_blocker_out_'
    for f in serfields:
        n=f['name']
        if n.startswith(sprefix):
            other=mprefix+n[len(sprefix):];g=mbby[other];assert f['width']==g['width']and f['direction']!=g['direction']
            assert reduced(serial[n])==reduced(mbus[other]),(n,serial[n],mbus[other])
            value=wire('join_'+n[len(sprefix):],f['width']);allpins['serial.'+n]=value;allpins['mbus.'+other]=value
            joins.append({'from':('serial.'+n)if f['direction']=='output'else('mbus.'+other),'to':('mbus.'+other)if f['direction']=='output'else('serial.'+n),'width':f['width'],'parent_serial_binding':serial[n],'parent_mbus_binding':mbus[other],'source_assignment_reduction':reduced(serial[n])})
    for f in mbfields:
        n=f['name'];key='mbus.'+n
        if key in allpins:continue
        if n=='auto_mbus_clock_groups_in_member_mbus_0_clock':allpins[key]='iris_clock'
        elif n=='auto_mbus_clock_groups_in_member_mbus_0_reset':allpins[key]='iris_reset'
        else:allpins[key]=port(f['direction'],'iris_mbus_'+n,f['width']);exports.append({'component':'mbus','port':n,'wrapper':allpins[key],**f})
    for f in serfields:
        n=f['name'];key='serial.'+n
        if key in allpins:continue
        if n=='auto_clock_in_clock':allpins[key]='iris_mbus_auto_fixedClockNode_anon_out_clock'
        elif n=='auto_clock_in_reset':allpins[key]='iris_mbus_auto_fixedClockNode_anon_out_reset'
        elif n=='serial_tl_1_clock_in':allpins[key]=wire('iris_serial_tl_1_clock_in',1)
        elif n.startswith('serial_tl_1_'):allpins[key]=wire('iris_'+n,f['width'])
        else:allpins[key]=port(f['direction'],'iris_serial_'+n,f['width']);exports.append({'component':'serial','port':n,'wrapper':allpins[key],**f})
    # Retain the actual complete Iris pad network, rather than hand-folding
    # bit concatenations or treating Arbiter.ready as an unproved data alias.
    arbiter=modules['Arbiter1_Bool'];assert not re.search(r'\b(?:always|reg)\b',arbiter);assert re.search(r'assign io_in_0_ready = io_out_ready;',arbiter)
    chip=modules['ChipTop'];chipassign=assignments(chip);iopad_proofs=[]
    for m in re.finditer(r'^  Arbiter1_Bool (iocell_serial_tl_1_\w+) \(',chip,re.M):
        pins=instance(chip,'Arbiter1_Bool',m[1]);iopad_proofs.append({'instance':m[1],'pins':pins,'reduced_inputs':{k:chipassign.get(v,v)for k,v in pins.items()if k.startswith('io_in_')}})
    assert len(iopad_proofs)==18
    system_pins=instance(chip,'DigitalTop','system');chipfields=fields(chip);sysfields=fields(modules['DigitalTop'])
    cutfields=[{'direction':'input'if f['direction']=='output'else'output','width':f['width'],'name':'cut_'+f['name']}for f in sysfields]
    padbody=chip[chip.index('\n);')+4:chip.index('\nendmodule')]
    padbody=re.sub(r'^  DigitalTop system \([\s\S]*?^  \);','',padbody,flags=re.M)
    assert not re.search(r'\b(?:always|reg)\b',padbody)
    for f in sysfields:
        pin=system_pins[f['name']]
        padbody+='\n  assign '+('cut_'+f['name']+' = '+pin if f['direction']=='input'else pin+' = cut_'+f['name'])+';'
    modules['IrisSerialPad']='module IrisSerialPad(\n'+',\n'.join('  '+f['direction']+' '+('['+str(f['width']-1)+':0] 'if f['width']>1 else'')+f['name']for f in chipfields+cutfields)+'\n);'+padbody+'\nendmodule\n'
    for f in chipfields+cutfields:
        n=f['name'];key='pad.'+n
        if n=='clock_uncore' or n=='clock_tileClockGroup_rockettile_2':allpins[key]='iris_clock'
        elif n=='serial_tl_1_clock_in':allpins[key]=wire('bringup_serial_clock_out',1)
        elif n.startswith('serial_tl_1_'):allpins[key]=wire('pad_'+n,f['width'])
        elif n.startswith('cut_serial_tl_1_'):allpins[key]='iris_'+n[len('cut_'):]
        else:allpins[key]=port(f['direction'],'iris_pad_'+n,f['width']);exports.append({'component':'pad','port':n,'wrapper':allpins[key],**f})
    for f in brfields:
        n=f['name'];key='bringup.'+n
        if n=='clock_uncore':allpins[key]='bringup_clock'
        elif n=='clock_serial_tl_0_clock_0':allpins[key]='serial_clock'
        elif n=='reset_io':allpins[key]='bringup_reset'
        elif n=='serial_tl_0_clock_out':allpins[key]='bringup_serial_clock_out'
        elif n=='serial_tl_0_in_valid':allpins[key]='pad_serial_tl_1_out_valid'
        elif n=='serial_tl_0_in_bits_phit':allpins[key]='pad_serial_tl_1_out_bits_phit'
        elif n=='serial_tl_0_in_ready':allpins[key]='pad_serial_tl_1_out_ready'
        elif n=='serial_tl_0_out_ready':allpins[key]='pad_serial_tl_1_in_ready'
        elif n=='serial_tl_0_out_valid':allpins[key]='pad_serial_tl_1_in_valid'
        elif n=='serial_tl_0_out_bits_phit':allpins[key]='pad_serial_tl_1_in_bits_phit'
        else:allpins[key]=port(f['direction'],'fased_'+n,f['width']);exports.append({'component':'bringup','port':n,'wrapper':allpins[key],**f})
    # Verify the actual top-level serialized link endpoint pairing. No credit,
    # phit, ready or reset behavior is supplied by this extraction script.
    sim=modules['FireSim'];simassign=assignments(sim)
    top_link={
        'chiptop1_serial_tl_0_in_valid':'chiptop0_serial_tl_1_out_valid',
        'chiptop1_serial_tl_0_in_bits_phit':'chiptop0_serial_tl_1_out_bits_phit',
        'chiptop0_serial_tl_1_out_ready':'chiptop1_serial_tl_0_in_ready',
        'chiptop0_serial_tl_1_in_valid':'chiptop1_serial_tl_0_out_valid',
        'chiptop0_serial_tl_1_in_bits_phit':'chiptop1_serial_tl_0_out_bits_phit',
        'chiptop1_serial_tl_0_out_ready':'chiptop0_serial_tl_1_in_ready',
        'chiptop0_serial_tl_1_clock_in':'chiptop1_serial_tl_0_clock_out'}
    for lhs,rhs in top_link.items():assert simassign[lhs].split('//')[0].strip()==rhs,(lhs,simassign.get(lhs),rhs)
    # Preserve the actual MBUS fixed-clock output -> serial domain binding,
    # rather than replacing that source node with an assumed clock/reset alias.
    for dimension in ['clock','reset']:
        assert mbus['auto_fixedClockNode_anon_out_'+dimension]==reduced(serial['auto_clock_in_'+dimension])
    for component,kind,fs in [('mbus','MemoryBus',mbfields),('serial','SerialTL1ClockSinkDomain',serfields),('pad','IrisSerialPad',chipfields+cutfields),('bringup','ChipTop_1',brfields)]:
        inst.append('  '+kind+' '+component+' (\n'+',\n'.join('    .'+f['name']+'('+allpins[component+'.'+f['name']]+')'for f in fs)+'\n  );')
    wrapper='module IrisSerialMemoryPath(\n'+',\n'.join('  '+f['direction']+' '+('['+str(f['width']-1)+':0] 'if f['width']>1 else'')+f['name']for f in top_ports)+'\n);\n'+'\n'.join(wiredecl+inst)+'\nendmodule\n'
    selected=set();todo=['MemoryBus','SerialTL1ClockSinkDomain','IrisSerialPad','ChipTop_1'];unknown=set()
    while todo:
        name=todo.pop()
        if name in selected:continue
        selected.add(name);body=modules[name];children=set(re.findall(r'^\s*(\w+)\s+\w+\s*\(',body,re.M));children.update(re.findall(r'^\s*(\w+)\s*#\([\s\S]*?\)\s+\w+\s*\(',body,re.M));todo.extend(children&modules.keys()-selected);unknown.update(children-modules.keys()-{'module','end','if','else','for','while','case','assign','always','always_ff','always_comb','always_latch'})
    out.mkdir();(out/'rtl').mkdir()
    for name in sorted(selected):(out/'rtl'/(name+'.sv')).write_text(modules[name])
    (out/'rtl/IrisSerialMemoryPath.sv').write_text(wrapper)
    for name in ['DigitalTop','ChipTop','FireSim']:(out/(name+'-wiring.sv')).write_text(modules[name])
    report={'schema':'iris.archived_serial_memory_path_source.v1','archived_SV_sha256':sha(sv),'archived_SV':str(sv),'source_extraction_sha256':sha(source/'extraction.json'),'extractor_sha256':sha(__file__),'source_repositories':base['repositories'],'top':'IrisSerialMemoryPath','modules':sorted(selected),'module_count':len(selected),'unresolved_candidate_leaves':sorted(unknown),'physical_ports':top_ports,'joined_TL_ports':joins,'top_serial_connections':top_link,'iris_pad_identity_proof':{'module_sha256':hashlib.sha256(arbiter.encode()).hexdigest(),'statement':'Actual Arbiter1_Bool has no state and io_in_0_ready is exactly io_out_ready. Full original ChipTop pad body, instances and concatenations are retained after exposing the DigitalTop boundary; no data alias simplification.','instances':iopad_proofs,'derived_pad_module_sha256':hashlib.sha256(modules['IrisSerialPad'].encode()).hexdigest()},'physical_exports':exports,'clock_policy':{'iris_clock_relative_period':2,'bringup_clock_relative_period':1,'serial_clock_relative_period':10,'source':'archived RationalClockTokenGenerator and FireSim wiring; copied source boundaries retain all original internal CDCs','Iris_uncore_reset':'explicit physical cut input, not guessed global reset waveform','Bringup_reset':'original ChipTop_1.reset_io; original PRCI/reset synchronization remains inside'},'source_sha256':{str(q.relative_to(out)):sha(q)for q in sorted((out/'rtl').iterdir())},'outer_functional_service':'external AXI64/address33/ID4 responses; no default latency, data backing, readiness or observed state supplied','hardware_contacted':False,'loaded_image_verified':False,'source_image_association_verified':False,'whole_soc_timing_certified':False,'calibration_usable':False}
    report['external_blackbox_source']={'module':'plusarg_reader','source':str(helper),'source_sha256':sha(helper),'current_source':str(current_helper),'current_source_sha256':sha(current_helper),'equivalence':'Exact text apart from trailing newline. Saved standalone FIR inline helper, used by archived TLMonitor assertions; not claimed as loaded-image readback.','plusargs':'original parameterized source semantics and caller-supplied arguments, no synthesized timing readiness'}
    (out/'extraction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'module_count':len(selected),'physical_ports':len(top_ports),'TL_joins':len(joins),'unresolved':sorted(unknown),'report_sha256':sha(out/'extraction.json')}))
if __name__=='__main__':main()
