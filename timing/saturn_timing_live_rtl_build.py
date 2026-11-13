#!/usr/bin/env python3
"""Read-only K1 trace prefix; unchanged whole-SoC RTL/runtime/preload objects."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
CAP=R/'build/saturn-timing-ownership-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py');old=CAP/'build/saturn-timing-ownership-rtl-v7';receipt=json.loads((old/'build.json').read_text());ports_path=R/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/ports.json';ports=json.loads(ports_path.read_text());ni=len(ports['words']['input']);ready=next(w['word_index']for w in ports['words']['input']if w['word_name']=='io_resp_ready');valid=ni+next(w['word_index']for w in ports['words']['output']if w['word_name']=='io_resp_valid');clock='TestDriver__DOT__testHarness__DOT__source__DOT__clk_i'
 for name in ['activity_observer.hpp','ownership_observer.hpp']:shutil.copy2(old/name,out/name)
 source=out/'observer.cpp';text=(old/'observer.cpp').read_text();original='''        auto iris_saturn_before=iris_activity_frame();
        auto iris_ownership_before=iris_ownership_frame();
        topp->eval();
        iris_activity_trace(iris_saturn_before);
        iris_ownership_trace(iris_ownership_before);''';replacement='''        if(!iris_prefix_complete){
            auto iris_saturn_before=iris_activity_frame();
            auto iris_ownership_before=iris_ownership_frame();
            topp->eval();
            iris_activity_trace(iris_saturn_before);
            iris_ownership_trace(iris_ownership_before);
            // Stop observation after this ELF's second actual scalar-vector
            // response. Continue every RTL eval/time slot through UART/HTIF.
            if(!iris_saturn_before.clocks[0] && iris_root->'''+clock+''' &&
               iris_root->TestDriver__DOT__trace_count>=3 && !iris_saturn_before.values[0][0] &&
               iris_saturn_before.values[0]['''+str(ready)+'''] && iris_saturn_before.values[0]['''+str(valid)+''']){
                if(++iris_observed_scalar_responses==2){iris_prefix_complete=true;
                    if(gzclose(iris_activity_file)!=Z_OK||gzclose(iris_ownership_file)!=Z_OK)throw std::runtime_error("Completed prefix close failed");
                    iris_activity_file=nullptr;iris_ownership_file=nullptr;
                    fprintf(stderr,"IRIS_OBSERVATION_PREFIX_COMPLETE tb=%lu h0_edges=%lu h1_edges=%lu h2_edges=%lu responses=2\\n",iris_root->TestDriver__DOT__trace_count,iris_activity_edge[0],iris_activity_edge[1],iris_activity_edge[2]);}
            }
        }else topp->eval();'''
 if text.count(original)!=1:raise ValueError('Qualified host phase points changed')
 text=text.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\nstatic bool iris_prefix_complete=false;\nstatic unsigned iris_observed_scalar_responses=0;').replace(original,replacement);source.write_text(text)
 compile=receipt['compile_argv'][:];compile[1]='-I'+str(out);compile[compile.index('-c')+1]=str(source);compile[compile.index('-o')+1]=str(out/'observer.o');compile += ['-MD','-MF',str(out/'observer.d'),'-save-temps=obj'];link=receipt['link_argv'][:];link[1]=str(out/'observer.o');link[link.index('-o')+1]=str(out/'simulator-k1')
 for name,digest in receipt['input_sha256'].items():
  if name.endswith(('.o','.a'))and Path(name).name!='observer.o'and sha(name)!=digest:raise ValueError('Changed qualified model/runtime/preload object '+name)
 with(out/'compile.log').open('w')as log:subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT,check=True)
 with(out/'link.log').open('w')as log:subprocess.run(link,stdout=log,stderr=subprocess.STDOUT,check=True)
 dependencies=[Path(x)for x in(out/'observer.d').read_text().replace('\\\n',' ').split(':',1)[1].split()];tools=[Path(compile[0]),Path(link[0])];
 for compiler in [compile[0],link[0]]:
  for name in ['cc1plus','as','collect2','ld']:
   raw=subprocess.check_output([compiler,'-print-prog-name='+name],text=True).strip();tools.append(Path(raw if '/'in raw else shutil.which(raw)).resolve())
 runtime=subprocess.check_output(['ldd',str(out/'simulator-k1')],text=True);(out/'ldd.txt').write_text(runtime);libraries=[Path(x)for x in re.findall(r'(?:=>\s+)?(/[^\s()]+)',runtime)if Path(x).is_file()];inputs=[*dependencies,*tools,*libraries,Path(__file__),CAP/'report.json',old/'build.json',source,ports_path,*[out/x for x in ['activity_observer.hpp','ownership_observer.hpp']],*[Path(x)for x in link if x.endswith(('.o','.a'))]];report={'schema':'iris.saturn_K1_whole_RTL_prefix_reference.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(out/'simulator-k1'),'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','all_target_RTL_runtime_preload_objects_unchanged':True,'model_eval_call_count_or_time_modified':False,'observation_prefix_stop':'After second actual h0 scalar-vector response; all subsequent RTL eval/time slots execute without activity dump.','physical_source_response_indices':{'ready':ready,'valid':valid,'source_clock_member':clock},'two_state_saved_FIR_native_RAM_reference':True,'target_state_or_readiness_injected':False,'FPGA_or_timing_calibration_claimed':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'binary_sha256':report['binary_sha256']}))
if __name__=='__main__':main()
