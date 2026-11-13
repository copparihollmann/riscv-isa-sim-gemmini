#!/usr/bin/env python3
"""Clock-stamped binary physical/activity capture from independent whole RTL."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

R=Path(__file__).resolve().parents[1]
REFERENCE=R/'build/saturn-timing-component-v1-final'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def expression(member,width,lo):
    value='iris_root->'+member
    if width<=64:return 'uint64_t('+value+')'
    result='uint64_t('+value+'['+str(lo//32)+'])'
    if min(64,width-lo)>32:result+='|(uint64_t('+value+'['+str(lo//32+1)+'])<<32)'
    return '('+result+')'

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--schema',type=Path,required=True)
    parser.add_argument('--reference',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(Path(__file__),out/'builder.py')
    reference=args.reference.resolve();schema_path=args.schema.resolve();schema=json.loads(schema_path.read_text())
    if not(reference/'build.json').is_file():raise ValueError('Wait for independent whole-RTL build')
    physical={k:json.loads((REFERENCE/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in['compute','rocket']}
    clocks=['TestDriver__DOT__testHarness__DOT__source__DOT__clk_i']*2+['TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__chipyard_prcictrl_domain__DOT___clock_gater_auto_clock_gater_out_member_allClocks_tileClockGroup_rockettile_2_clock']
    counts=[len(physical[k]['words']['input'])+len(physical[k]['words']['output'])+schema['profiles'][k]['word_count']for k in['compute','compute','rocket']]
    code='''#include <zlib.h>
#include <bit>
#include <array>
static_assert(std::endian::native==std::endian::little);
static gzFile iris_activity_file=nullptr;
static uint64_t iris_activity_edge[3]={0,0,0};
static void iris_activity_write(const void*data,unsigned bytes){if(gzwrite(iris_activity_file,data,bytes)!=int(bytes))throw std::runtime_error("Activity capture write failed");}
static void iris_activity_open(int argc,char**argv){const char*path=nullptr;for(int n=1;n<argc;++n)if(!strncmp(argv[n],"+iris-activity=",15))path=argv[n]+15;if(!path||!*path)throw std::runtime_error("Explicit activity output path required");iris_activity_file=gzopen(path,"wb1");if(!iris_activity_file)throw std::runtime_error("Cannot create activity capture");gzbuffer(iris_activity_file,1<<20);const uint64_t header[]={0x314e494254415349ULL,'''+','.join(map(str,counts))+'''};iris_activity_write(header,sizeof(header));}
'''
    code+='struct IrisActivityFrame{bool clocks[3];uint64_t values[3]['+str(max(counts))+'];};\n'
    code+='static IrisActivityFrame iris_activity_frame(){return {{'+','.join('bool(iris_root->'+c+')'for c in clocks)+'},{'
    bindings=[]
    for hart in range(3):
        key='rocket'if hart==2 else'compute';profile=physical[key];parent='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__tile_prci_domain'+('_'+str(hart)if hart else'')+'__DOT__element_reset_domain_'+('rockettile'if hart==2 else'shuttle_tile')+'__DOT__vector_unit__DOT__';values=[]
        for field in profile['words']['input']+profile['words']['output']:
            member=parent+field['name'];values.append(expression(member,field['width'],field['lo']))
            bindings.append({'hart':hart,'kind':'physical','member':member,'word':field})
        for field in schema['profiles'][key]['fields']:
            member=next(g['member']for g in field['whole_members']if g['hart']==hart)
            for word in field['words']:
                values.append(expression(member,field['width'],word['lo']))
                bindings.append({'hart':hart,'kind':'activity','name':field['name'],'member':member,'word':word})
        assert len(values)==counts[hart]
        code+='{'+','.join(values)+'}'+(','if hart<2 else'')
    code+='}};}\n'
    code+='static void iris_activity_trace(const IrisActivityFrame&before){bool after[]={'+','.join('bool(iris_root->'+c+')'for c in clocks)+'};const uint64_t count[]={'+','.join(map(str,counts))+'};for(unsigned h=0;h<3;++h){if(before.clocks[h]||!after[h]||iris_root->TestDriver__DOT__trace_count<3)continue;const uint64_t header[]={iris_root->TestDriver__DOT__trace_count,iris_activity_edge[h]++,h,count[h]};iris_activity_write(header,sizeof(header));iris_activity_write(before.values[h],8*count[h]);}}\n'
    include=out/'activity_observer.hpp';include.write_text(code)
    old_main=REFERENCE/'timing/saturn_timing_observer.cpp';source=old_main.read_text()
    source=source.replace('#include "saturn_timing_observer.hpp"','#include "activity_observer.hpp"')
    source=source.replace('    uint64_t next_report=10000;','    uint64_t next_report=10000;\n    iris_activity_open(argc,argv);')
    source=source.replace('auto iris_saturn_before=iris_saturn_frame();','auto iris_saturn_before=iris_activity_frame();').replace('iris_saturn_trace(iris_saturn_before);','iris_activity_trace(iris_saturn_before);')
    source=source.replace('    contextp->statsPrintSummary();','    if(iris_activity_file){if(gzclose(iris_activity_file)!=Z_OK)throw std::runtime_error("Activity close failed");iris_activity_file=nullptr;}\n    contextp->statsPrintSummary();')
    mainfile=out/'observer.cpp';mainfile.write_text(source)
    old=json.loads((REFERENCE/'build/saturn-timing-rtl-v1/build.json').read_text());original=str(R/'build/saturn-timing-reference-v1')
    compile=[arg.replace(original,str(reference))for arg in old['compile_argv']]
    compile[compile.index('-c')+1]=str(mainfile);compile[compile.index('-o')+1]=str(out/'observer.o');compile.insert(1,'-I'+str(out))
    with(out/'compile.log').open('w')as log:subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT,check=True)
    link=[arg.replace(original,str(reference))for arg in old['link_argv']]
    link[1]=str(out/'observer.o');link[link.index('-o')+1]=str(out/'simulator-activity');link.append('-lz')
    with(out/'link.log').open('w')as log:subprocess.run(link,stdout=log,stderr=subprocess.STDOUT,check=True)
    (out/'bindings.json').write_text(json.dumps(bindings,indent=2)+'\n')
    inputs=[Path(__file__),schema_path,reference/'build.json',mainfile,include,old_main]+[Path(x)for x in link if x.endswith(('.o','.a'))]
    result={'schema':'iris.saturn_activity_whole_rtl_observer.v1','compile_argv':compile,'link_argv':link,
            'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(out/'simulator-activity'),
            'physical_activity_words_per_hart':counts,'source_clock_members':clocks,
            'binary_format':'little-endian u64 header[magic,words0,words1,words2]; records[tb,source_edge,hart,words]+physical_input+physical_output+activity;gzip',
            'source_RTL_logic_modified':False,'internal_state_or_clocks_driven':False,
            'hardware_contacted':False}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'binary_sha256':result['binary_sha256'],'words':counts}))

if __name__=='__main__':main()
