#!/usr/bin/env python3
"""Source-clock ownership sidecar using the frozen whole-RTL model objects."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
BASE=R/'build/saturn-timing-activity-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def expression(member,width,lo):
 base='iris_root->'+member
 if width<=64:return 'uint64_t('+base+')'
 value='uint64_t('+base+'['+str(lo//32)+'])'
 if min(64,width-lo)>32:value+='|(uint64_t('+base+'['+str(lo//32+1)+'])<<32)'
 return '('+value+')'
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--schema',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py');schema_path=a.schema.resolve();schema=json.loads(schema_path.read_text());old=BASE/'build/saturn-timing-activity-rtl-v1';build=json.loads((old/'build.json').read_text());clocks=build['source_clock_members'];counts=[schema['profiles'][k]['word_count']for k in ['compute','compute','rocket']]
 code='''static gzFile iris_ownership_file=nullptr;
static uint64_t iris_ownership_edge[3]={0,0,0};
static void iris_ownership_write(const void*p,unsigned bytes){if(gzwrite(iris_ownership_file,p,bytes)!=int(bytes))throw std::runtime_error("Ownership sidecar write failed");}
static void iris_ownership_open(int argc,char**argv){const char*path=nullptr;for(int n=1;n<argc;++n)if(!strncmp(argv[n],"+iris-ownership=",16))path=argv[n]+16;if(!path||!*path)throw std::runtime_error("Explicit ownership output path required");iris_ownership_file=gzopen(path,"wb1");if(!iris_ownership_file)throw std::runtime_error("Cannot create ownership sidecar");gzbuffer(iris_ownership_file,1<<20);const uint64_t header[]={0x314e574f54415349ULL,'''+','.join(map(str,counts))+'''};iris_ownership_write(header,sizeof(header));}
'''
 code+='struct IrisOwnershipFrame{bool clocks[3];uint64_t values[3]['+str(max(counts))+'];};\nstatic IrisOwnershipFrame iris_ownership_frame(){return {{'+','.join('bool(iris_root->'+clock+')'for clock in clocks)+'},{'
 for h in range(3):
  key='rocket'if h==2 else'compute';expressions=[]
  for f in schema['profiles'][key]['fields']:
   member=next(g['member']for g in f['whole_members']if g['hart']==h)
   for word in f['words']:expressions.append(expression(member,f['width'],word['lo']))
  code+='{'+','.join(expressions)+'}'+(','if h<2 else'')
 code+='}};}\nstatic void iris_ownership_trace(const IrisOwnershipFrame&before){bool after[]={'+','.join('bool(iris_root->'+clock+')'for clock in clocks)+'};const uint64_t counts[]={'+','.join(map(str,counts))+'};for(unsigned h=0;h<3;++h){if(before.clocks[h]||!after[h]||iris_root->TestDriver__DOT__trace_count<3)continue;const uint64_t header[]={iris_root->TestDriver__DOT__trace_count,iris_ownership_edge[h]++,h,counts[h]};iris_ownership_write(header,sizeof(header));iris_ownership_write(before.values[h],8*counts[h]);}}\n'
 header=out/'ownership_observer.hpp';header.write_text(code);shutil.copy2(old/'activity_observer.hpp',out/'activity_observer.hpp');source=out/'observer.cpp';text=(old/'observer.cpp').read_text();text=text.replace('#include "activity_observer.hpp"','#include "activity_observer.hpp"\n#include "ownership_observer.hpp"').replace('iris_activity_open(argc,argv);','iris_activity_open(argc,argv);\n    iris_ownership_open(argc,argv);').replace('auto iris_saturn_before=iris_activity_frame();','auto iris_saturn_before=iris_activity_frame();\n        auto iris_ownership_before=iris_ownership_frame();').replace('iris_activity_trace(iris_saturn_before);','iris_activity_trace(iris_saturn_before);\n        iris_ownership_trace(iris_ownership_before);').replace('    contextp->statsPrintSummary();','    if(iris_ownership_file){if(gzclose(iris_ownership_file)!=Z_OK)throw std::runtime_error("Ownership close failed");iris_ownership_file=nullptr;}\n    contextp->statsPrintSummary();');source.write_text(text)
 if text.count('iris_ownership_frame();')!=1 or text.count('iris_ownership_trace(iris_ownership_before);')!=1:raise ValueError('Frozen driver phase points changed')
 compile=build['compile_argv'][:];compile[1]='-I'+str(out);compile[compile.index('-c')+1]=str(source);compile[compile.index('-o')+1]=str(out/'observer.o');link=build['link_argv'][:];link[1]=str(out/'observer.o');link[link.index('-o')+1]=str(out/'simulator-ownership')
 # Verify all frozen linked input bytes, including host preload/TSI libraries.
 for name,digest in build['input_sha256'].items():
  if name.endswith(('.o','.a')) and Path(name).name!='observer.o':
   if sha(name)!=digest:raise ValueError('Changed immutable linked input '+name)
 with(out/'compile.log').open('w')as log:subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT,check=True)
 with(out/'link.log').open('w')as log:subprocess.run(link,stdout=log,stderr=subprocess.STDOUT,check=True)
 inputs=[Path(__file__),schema_path,BASE/'report.json',old/'build.json',source,header,out/'activity_observer.hpp']+[Path(x)for x in link if x.endswith(('.o','.a'))];result={'schema':'iris.saturn_ownership_whole_RTL_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(out/'simulator-ownership'),'ownership_words_per_hart':counts,'ownership_binary_magic':0x314e574f54415349,'layout':'gzip little-endian u64 header[magic,count0,count1,count2]; record[tb,source_edge,hart,count]+words; join original activity by exact3identityfields','frozen_source_RTL_model_objects_modified':False,'internal_state_or_clocks_driven':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'binary_sha256':result['binary_sha256'],'sidecar_words':counts}))
if __name__=='__main__':main()
