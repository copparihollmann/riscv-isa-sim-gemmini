#!/usr/bin/env python3
"""Read-only typed activity API on context-safe, source-unchanged timing cuts."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

R=Path(__file__).resolve().parents[1]
CONTEXT=R/'build/saturn-timing-context-component-v1-final'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_expression(member,width,lo):
    base='root.'+member
    if width<=64:return 'std::uint64_t('+base+')'
    value='std::uint64_t('+base+'['+str(lo//32)+'])'
    if min(64,width-lo)>32:value+='|(std::uint64_t('+base+'['+str(lo//32+1)+'])<<32)'
    return '('+value+')'

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--schema',type=Path,required=True)
    parser.add_argument('--compute',type=Path,required=True)
    parser.add_argument('--rocket',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),out/'builder.py')
    schema_path=args.schema.resolve();schema=json.loads(schema_path.read_text())
    if any(p['unresolved']for p in schema['profiles'].values()):raise ValueError('Unresolved activity source boundary')
    compute=args.compute.resolve();rocket=args.rocket.resolve()
    for native in[compute,rocket]:
        if not(native/'build.json').is_file():raise ValueError('Wait for visibility-only native build')
    base=CONTEXT/'build/saturn-timing-context-fast-v1';local=out/'source';local.mkdir()
    for name in['saturn_timing.cpp','saturn_timing.hpp','saturn_timing_driver.cpp']:
        shutil.copy2(base/'source'/name,local/name)
    api=local/'saturn_timing.hpp';header=api.read_text().replace('#include <string>','#include <string>\n#include <optional>')
    declaration='''struct ActivitySnapshot {
 unsigned hart;std::uint64_t source_edge;std::string_view source_clock_id;
 std::optional<std::uint64_t> uncore_tick;
 // Raw source bits. Knownness/valid/operation qualifiers are mandatory.
 std::vector<std::uint64_t> words;
};
struct DispatchRegisters {
 std::uint64_t source_edge;std::uint16_t next_debug_id;
 unsigned vat_head,vat_tail;std::uint32_t allocated_mask;
};
'''
    header=header.replace('class SaturnTimingCut {',declaration+'class SaturnTimingCut {')
    header=header.replace(' ReferenceOutputs sample()const;', ''' ReferenceOutputs sample()const;
 // Pre-edge only; no state/edge/readiness injection. Caller timestamp is metadata.
 ActivitySnapshot sample_activity(std::optional<std::uint64_t> uncore_tick={})const;
 static std::span<const Field> activity_fields(Profile);
 // Raw registered state, also available after commit for dispatch generations.
 DispatchRegisters inspect_dispatch_registers()const;''')
    api.write_text(header);implementation=local/'saturn_timing.cpp';text=implementation.read_text()
    text=text.replace('#include "VSaturnCompute.h"','#include "VSaturnCompute.h"\n#include "VSaturnCompute___024root.h"')
    text=text.replace('#include "VSaturnRocket.h"','#include "VSaturnRocket.h"\n#include "VSaturnRocket___024root.h"')
    extension='''ActivitySnapshot SaturnTimingCut::sample_activity(std::optional<std::uint64_t> tick)const{
 SaturnContextScope owner(impl_->context.get());
 if(!impl_->evaluated)throw std::logic_error("Activity snapshot requires fresh pre-edge evaluate");
 ActivitySnapshot out{impl_->hart,impl_->edge_count,source_clock_id(impl_->profile,impl_->hart),tick,{}};
 out.words.resize(activity_fields(impl_->profile).size());
'''
    for key,p in schema['profiles'].items():
        kind='Compute128'if key=='compute'else'Rocket256'
        extension+='if(impl_->profile==Profile::'+kind+'){const auto&root=*impl_->'+key+'->rootp;\n'
        for field in p['fields']:
            for word in field['words']:
                extension+='out.words['+str(word['index'])+']='+read_expression(field['member'],field['width'],word['lo'])+';\n'
        extension+='}\n'
    extension+='return out;}\nstd::span<const Field> SaturnTimingCut::activity_fields(Profile p){\n'
    for key,p in schema['profiles'].items():
        fields=[]
        for field in p['fields']:
            for word in field['words']:
                name=field['name']+('@'+str(word['lo'])if field['width']>64 else'')
                fields.append('{'+json.dumps(name)+','+str(field['width'])+','+str(word['lo'])+','+str(word['width'])+'}')
        extension+='static constexpr Field '+key+'[]={'+','.join(fields)+'};\n'
    extension+='if(p==Profile::Compute128)return compute;if(p==Profile::Rocket256)return rocket;throw std::invalid_argument("Unknown activity profile");}\n'
    extension+='''DispatchRegisters SaturnTimingCut::inspect_dispatch_registers()const{
 SaturnContextScope owner(impl_->context.get());DispatchRegisters out{impl_->edge_count,0,0,0,0};
'''
    for key,p in schema['profiles'].items():
        kind='Compute128'if key=='compute'else'Rocket256';by_name={f['name']:f for f in p['fields']}
        extension+='if(impl_->profile==Profile::'+kind+'){const auto&root=*impl_->'+key+'->rootp;\n'
        for logical,target in [('dis.debug_id_ctr','next_debug_id'),('dis.vat_head','vat_head'),('dis.vat_tail','vat_tail')]:
            field=by_name[logical];extension+='out.'+target+'='+read_expression(field['member'],field['width'],0)+';\n'
        valids=[f for f in p['fields']if f['name'].startswith('dis.vat_valids_')]
        if len(valids)!=(32 if key=='compute'else 8):raise ValueError('Wrong source VAT dimensions')
        for field in valids:
            slot=int(field['name'].rsplit('_',1)[1]);extension+='out.allocated_mask|=std::uint32_t('+read_expression(field['member'],field['width'],0)+')<<'+str(slot)+';\n'
        extension+='}\n'
    extension+='return out;}\n';at=text.rfind('\n}');implementation.write_text(text[:at]+'\n'+extension+text[at:])
    inputs=[Path(__file__),schema_path,compute/'build.json',rocket/'build.json',base/'build.json',base/'sdk/libiris_saturn_timing.a',implementation,api,local/'saturn_timing_driver.cpp',CONTEXT/'report.json',Path('/usr/bin/g++'),Path('/usr/bin/ar')]
    identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in inputs},sort_keys=True).encode()).hexdigest();identity_header=local/'saturn_timing_identity.hpp';identity_header.write_text('#pragma once\n#define IRIS_SATURN_TIMING_SOURCE_ID "'+identity+'"\n');inputs.append(identity_header)
    sdk=out/'sdk';sdk.mkdir();library=sdk/'libiris_saturn_timing.a';shutil.copy2(base/'sdk/libiris_saturn_timing.a',library)
    members=subprocess.check_output(['/usr/bin/ar','t',str(library)],text=True).splitlines()
    removed=[m for m in members if m.startswith(('VSaturnCompute','VSaturnRocket'))]
    subprocess.run(['/usr/bin/ar','d',str(library),*removed],check=True)
    model_objects=sorted((compute/'model').glob('VSaturnCompute*.o'))+sorted((rocket/'model').glob('VSaturnRocket*.o'))
    tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
    common=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(local),'-I'+str(tool),'-I'+str(tool/'vltstd'),'-I'+str(compute/'model'),'-I'+str(rocket/'model')]
    commands=[common+['-c',str(implementation),'-o',str(out/'saturn_timing.o')],
              ['/usr/bin/ar','rcs',str(library),str(out/'saturn_timing.o'),*map(str,model_objects)],
              common+[str(local/'saturn_timing_driver.cpp'),str(library),'-latomic','-o',str(out/'saturn-timing')]]
    with(out/'build.log').open('w')as log:
        for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    shutil.copy2(api,sdk/api.name);shutil.copy2(schema_path,sdk/'activity-schema.json');inputs+=model_objects
    result={'schema':'iris.saturn_context_safe_activity_sdk.v1','source_identity':identity,
            'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},
            'native_sha256':sha(out/'saturn-timing'),'library_sha256':sha(library),
            'physical_unit_inputs_unchanged':True,'internal_state_inputs_added':False,
            'activity_is_readonly_preedge':True,'caller_context_scoped':True,
            'knownness_is_not_inferred_from_raw_bits':True,'hardware_contacted':False}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'source_identity':identity,'native_sha256':result['native_sha256'],
                      'activity_words':{k:p['word_count']for k,p in schema['profiles'].items()}}))

if __name__=='__main__':main()
