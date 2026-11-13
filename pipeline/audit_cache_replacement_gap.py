#!/usr/bin/env python3
"""Read-only, source-bound cache replacement counterexample; no runtime edits."""
import argparse, hashlib, json, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASSOCIATED=Path('/scratch/eygao/iris-cy/sims/firesim/deploy/results-build/2026-11-03--03-10-49-corigine_mimicturbo_gt_firesim_iris_tethered_bringup_nocflush/cl_corigine_mimicturbo_gt-firesim-FireSim-IrisFiresimNOCflushCombinedConfig-BaseCorigineMimicTurboGTConfig/design/FireSim-generated.sv')
EXPECTED='c0f972d2a63be8170f7c84a38633fbede855f00d3022e81141fa0bb274397b64'
VERILATOR=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
PERL=VERILATOR.with_name('perl')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def module(s,name):
 m=re.search(r'^module '+name+r'\(.*?^endmodule',s,re.M|re.S)
 if not m:raise ValueError('Missing module '+name)
 return m.group()+'\n'
PATTERNS=[r'wire\s+s1_replaced_way = lfsr\[0\];',r'wire \[1:0\] s1_replaced_way_en = 2\'h1 << s1_replaced_way;',r'assign mshrs_io_req_bits_way_en = s2_tag_match \? s2_tag_match_way : s2_replaced_way_en;',r'assign lfsr_prng_io_increment = mshrs_io_req_ready & mshrs_io_req_valid;']
def guard(s):
 for p in PATTERNS:
  if len(re.findall(p,s))!=1:raise ValueError('Changed source victim/gating expression '+p)
def run(argv,out,label,expected=0):
 p=subprocess.run([str(x)for x in argv],capture_output=True)
 (out/(label+'.stdout')).write_bytes(p.stdout);(out/(label+'.stderr')).write_bytes(p.stderr)
 (out/(label+'.argv.json')).write_text(json.dumps([str(x)for x in argv],indent=2)+'\n')
 if p.returncode!=expected:raise ValueError(label+' exit '+str(p.returncode))
 return p

def main(out):
 out.mkdir(parents=True,exist_ok=False)
 if sha(ASSOCIATED)!=EXPECTED:raise ValueError('Associated SV changed')
 s=ASSOCIATED.read_text();dc=module(s,'ShuttleDCache');prng=module(s,'MaxPeriodFibonacciLFSR');guard(dc)
 (out/'ShuttleDCache.sv').write_text(dc);(out/'MaxPeriodFibonacciLFSR.sv').write_text(prng)
 mutations=[]
 for name,old,new in [('way','s1_replaced_way = lfsr[0]','s1_replaced_way = lfsr[1]'),('victim','s2_tag_match ? s2_tag_match_way : s2_replaced_way_en','s2_tag_match ? s2_tag_match_way : 2\'h1'),('advance','mshrs_io_req_ready & mshrs_io_req_valid','mshrs_io_req_ready | mshrs_io_req_valid')]:
  assert dc.count(old)==1
  try:guard(dc.replace(old,new))
  except ValueError:mutations.append({'name':name,'rejected':True})
  else:raise ValueError('Mutation admitted '+name)
 cpp=ROOT/'pipeline/test_cache_replacement_gap.cpp';obj=out/'obj'
 run([PERL,VERILATOR,'--cc','--exe','-Wno-fatal','--top-module','MaxPeriodFibonacciLFSR','--Mdir',obj,'-CFLAGS','-std=c++20 -I'+str(ROOT/'timing'),out/'MaxPeriodFibonacciLFSR.sv',cpp,ROOT/'timing/empirical_cache_v8.cpp'],out,'verilate')
 run(['/usr/bin/make','-C',obj,'-f','VMaxPeriodFibonacciLFSR.mk','-j4','CXX=/usr/bin/g++','LINK=/usr/bin/g++','AR=/usr/bin/ar'],out,'make')
 p=run([obj/'VMaxPeriodFibonacciLFSR'],out,'check');proof=json.loads(p.stdout)
 assert proof['checks']==10064 and proof['source_retained_nodes']==45 and proof['V8_LRU_ready_nodes']==64
 # Recorded rows are fitting data only. Model hit/miss counts are never physical observations.
 rows=[json.loads(x)for x in (ROOT/'build/memory-routes-current-7bd5-ON-comparison-v1/regions.jsonl').read_text().splitlines()]
 worst=max(rows,key=lambda x:abs(x['signed_error_percent']))
 first_repeats=[x for x in rows if x['parent_case_id']==worst['parent_case_id'] and x['hart']==worst['hart']]
 dram_chase=[x for x in rows if x['target']=='dram'and x['kind']=='chase']
 inputs=[Path(__file__).resolve(),cpp,ASSOCIATED,VERILATOR,PERL,ROOT/'timing/empirical_cache_v8.hpp',ROOT/'timing/empirical_cache_v8.cpp',ROOT/'benchmarks/memory_routes/cases.py',ROOT/'benchmarks/memory_routes/guest.c',ROOT/'build/memory-routes-current-7bd5-ON-comparison-v1/regions.jsonl',ROOT/'build/memory-routes-current-7bd5-ON-comparison-v1/report.json',ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f/manifest.json',ROOT/'build/empirical-read-overlap-response-inputs-v2/on.fixture',ROOT/'hardware/evidence/iris-config.scala',Path('/scratch/eygao/iris-cy/generators/shuttle/src/main/scala/dmem/DCache.scala'),Path('/scratch/eygao/iris-cy/generators/shuttle/src/main/scala/common/Tile.scala'),Path('/scratch/eygao/iris-cy/generators/rocket-chip/src/main/scala/rocket/HellaCache.scala'),Path('/scratch/eygao/iris-cy/generators/rocket-chip/src/main/scala/util/Replacement.scala')]
 report={'schema':'iris.cache_replacement_source_gap_audit.v1','pass':True,'conditional_reference_proof':proof,'source_expression_controls':mutations,'source_model_gap':'actual source uses global miss-driven LFSR victim without invalid-way preference; V8 uses per-set LRU with invalid-way preference','conditional_witness_scope':'reset PRNG; cold2way64sets;64 sequential separated allocating misses at128Bstride; accepted fills complete before next request; no other requests; replacement selector only plus modeled tags','whole_cache_reference_execution':False,'actual_hardware_replacement_history_reproduced':False,'exact_observed_error_cause_proven':False,'native_or_parameters_modified':False,'worst_row':worst,'worst_parent_repeats':[{'case_id':x['case_id'],'hart':x['hart'],'hardware_cycles':x['hardware_cycles'],'native_cycles':x['native_cycles']}for x in first_repeats],'dram_chase_summary':{'regions':len(dram_chase),'model_all_L1_hits_regions':sum(x['actual_model_data_path_features'].get('l1misses',0)==0for x in dram_chase)},'interpretation':{'first_TCM_outlier':'two modeled source-Icache L2 misses; TCM target contenders0; no evidence TCM bank/WRW cause; global outer occupancy includes all harts','DRAM_chase':'model preparation assumes more ready resident lines than source random selection can guarantee; exact observed hardware tags remain unobserved','loader_history':'native HTIF writes do not call empirical CacheHistory; archived driver has_host_mem=false; exact actual loader/L2 history not proved here; no tag priming authorized','required_successor_proof':'optional policy flag; reproduce source accepted-miss sequence incl squash/secondary misses/invalidations; preserve readiness generations/accepted actors; OFF byteparity and new2592/SMP QA; no coefficient qualification transfer'},'image_association':'co-located associated generated SV only; fullsource/loaded-image attestation false','hardware_contacted':False,'global_heldout_timings_consumed':False,'full_2pct_certified':False,'input_sha256':{str(p):sha(p)for p in inputs}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();main(a.output.resolve())
