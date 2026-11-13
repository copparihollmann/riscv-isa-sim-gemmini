#!/usr/bin/env python3
"""Freeze the source-coupled memory component and exact qualification evidence."""
import hashlib,json,os,shutil,stat
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/memory-fabric-component-v1'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def main():
 if O.exists():raise ValueError('never overwrite a component closure')
 replay=R/'build/memory-fabric-replay-v2';model=R/'build/memory-fabric-coupled-native-v4';ctx=R/'build/memory-fabric-context-sdk-v2';whole=R/'build/memory-fabric-rtl-v1';ref=R/'build/memory-fabric-reference-v1';obs=R/'build/memory-fabric-observer-v1'
 positive=read(replay/'replay.stdout');assert positive['status']=='passed_closed_boundary_source_coupling'and positive['frames']==74903 and positive['compared_words']==23703753
 semantic=[json.loads(line)for line in(model/'check.stdout').read_text().splitlines()];assert semantic[-1]['status']=='passed'and semantic[-1]['checks']==1805
 assert read(whole/'run.json')['checks']==252
 cache=read(ctx/'cache/check.stdout');assert cache['checks']==10912 and cache['default_unknown_control_refusal_tested']is True
 order=read(ctx/'noc/order.stdout');assert order['physical_word_comparisons']==73443582 and order['caller_context_restoration_checks']==1626552
 assert (ctx/'noc/old-host-negative.stderr').read_text().strip()=='caller context not restored'
 assert 'SDK_IDENTITY_MISMATCH'in(model/'wrong-sdk.stderr').read_text()
 for name,message in [('wrong-output','MEMORY_FABRIC_MISMATCH'),('wrong-data','MEMORY_FABRIC_MISMATCH'),('truncated','truncated fabric frame'),('active-aux','active auxiliary TLB request')]:assert message in(replay/(name+'.stderr')).read_text()
 noc=read(R/'build/memory-fabric-context-checks-v3/report.json');assert noc['status']=='passed'
 files={};checked_inputs={};metadata=[]
 def add(path,expected=None):
  path=Path(path).absolute()
  if not path.is_file():raise ValueError('missing required closure input '+str(path))
  digest=sha(path)
  if expected is not None and digest!=expected:raise ValueError('changed closure input '+str(path))
  if str(path)in files:assert files[str(path)]['sha256']==digest;return
  files[str(path)]={'sha256':digest,'bytes':path.stat().st_size,'mode':stat.S_IMODE(path.stat().st_mode)}
 def tree(path,patterns=('*',)):
  for pattern in patterns:
   for p in Path(path).rglob(pattern):
    if p.is_file():add(p)
 def meta(path):
  path=Path(path);add(path);x=read(path);metadata.append(str(path))
  for key in ['input_sha256','source_sha256','source_files']:
   mapping=x.get(key,{})
   if isinstance(mapping,dict):
    for name,digest in mapping.items():
     if not isinstance(digest,str)or len(digest)!=64:continue
     p=Path(name)
     if not p.is_absolute():p=R/p
     add(p,digest);checked_inputs[str(p)]=digest
  return x
 for p in sorted((R/'timing').glob('memory_fabric*')):
  if p.is_file():add(p)
 for path in [replay,model,whole,obs,ctx,R/'build/memory-fabric-context-checks-v3']:
  tree(path)
 for path in [ref/'build.json',R/'build/memory-fabric-adapters-source-v2/extraction.json',R/'build/memory-fabric-graph-v1/graph.json',model/'build.json',obs/'build.json',whole/'run.json',replay/'build.json',R/'build/memory-fabric-adapters-native-v2/build.json',R/'build/cache-hierarchy-native-v5/build.json',R/'build/noc-network-native-v3/build.json',R/'build/noc-network-sdk-v1/build.json',R/'build/memory-fabric-context-checks-v3/report.json',ctx/'report.json']:
  meta(path)
 # The native model objects are independently source-bound in the old builds.
 # Keep both exact old archives and headers/code used by the host-only rebuild.
 for path in [R/'build/cache-hierarchy-native-v5',R/'build/noc-network-native-v3/model',R/'build/noc-network-sdk-v1/sdk',R/'build/memory-fabric-adapters-native-v2']:
  tree(path,('*.h','*.hpp','*.cpp','*.a'))
 for path in [R/'build/cache-hierarchy-source-v1',R/'build/noc-network-source-v2',R/'build/noc-network-graph-v2',R/'build/memory-fabric-adapters-source-v2',ref/'rtl']:
  tree(path)
 for name in ['cache_hierarchy.hpp','cache_hierarchy.cpp','cache_hierarchy_build.py','cache_hierarchy_extract.py','cache_hierarchy_check.cpp','noc_network.hpp','noc_network.cpp','noc_network_identity.hpp','noc_network_schema.hpp','noc_network_bench.cpp']:
  p=R/'timing'/name
  if p.exists():add(p)
 for p in [ref/'model/VTestDriver__ALL.a',ref/'model/VTestDriver___024root.h',ref/'memory-fabric-ports-readonly.vlt',ref/'verilate-command.json',ref/'compile-command.json',ref/'verilate.log',ref/'compile.log',R/'build/rtl-verilator/manifest.json',R/'build/rtl-memory-return-path-v1-final/report.json',R/'build/cache-hierarchy-component-v2/report.json',R/'build/noc-network-component-v1-final/report.json',R/'hardware/manifest.json',R/'hardware/dtypes.json']:
  add(p)
 # Include exact input FIR/annotations, not just a branch name or generated RTL.
 base=read(R/'build/rtl-verilator/manifest.json')
 add(base['source_fir'],base['source_fir_sha256']);add(base['source_annotations'],base['source_annotations_sha256'])
 for kind in ['cache','noc','adapters']:
  item=meta(ctx/kind/'build.json')
  for name,digest in item['unchanged_object_sha256'].items():add(ctx/kind/'objects'/name,digest)
  add(item['base_wrapper'],item['base_wrapper_sha256']);add(item['base_library'],item['base_library_sha256'])
 # Preserve the first strict idle-ready mismatch and its exact old checker.
 tree(R/'build/memory-fabric-replay-v1')
 O.mkdir();(O/'cas').mkdir();(O/'snapshot').mkdir();artifacts=[]
 for name,entry in sorted(files.items()):
  src=Path(name);blob=O/'cas'/(entry['sha256']+'-'+oct(entry['mode'])[2:]);target=O/'snapshot'/name.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
  if not blob.exists():shutil.copyfile(src,blob);blob.chmod(entry['mode']);assert sha(blob)==entry['sha256']
  os.link(blob,target);artifacts.append({'original':name,'snapshot':str(target.relative_to(O)),**entry})
 report={'schema':'iris.memory_fabric_component_capsule.v1','status':'passed_source_coupled_Rocket_NoC_L2_component','source_FIR_sha256':base['source_fir_sha256'],'SDK_source_identity':read(model/'build.json')['source_identity'],'SDK_library_sha256':sha(model/'sdk/libiris_memory_fabric.a'),'context_derivatives':{name:read(ctx/name/'build.json')['source_identity']for name in ['cache','noc','adapters']},'source_adapter_extraction_sha256':sha(R/'build/memory-fabric-adapters-source-v2/extraction.json'),'source_graph_sha256':sha(R/'build/memory-fabric-graph-v1/graph.json'),'independent_whole_RTL':{'run_sha256':sha(whole/'run.json'),'trace_sha256':sha(whole/'fabric-ports.bin.gz'),'guest_checks':252,'harts':3,'FIR_native_memories':True,'loaded_image_association_verified':False},'closed_boundary_replay':positive,'coupled_independent_semantics':semantic,'preserved_cache_semantics':cache,'host_context_order':order,'host_context_reference_replays':noc,'negative_controls':{'wrong_control_output':1,'wrong_valid_data':1,'truncated_frame':2,'active_unqualified_aux_TLB':2,'wrong_SDK_identity':1,'old_host_context_wrapper':1},'strict_first_attempt':{'receipt':str(R/'build/memory-fabric-replay-v1/replay.stderr'),'first_frame':393,'first_TB':785,'field':'rocket_tile::auto_buffer_out_d_ready','source_qualification':'D.valid=0; sourceID82 from unwritten FIFO slot. TLXbar.sv301 ready selects invalid sourceID, but source253/263/275 gate every D valid and the async FIFO only pops on valid&&ready. Only this idle-ready comparison is excluded; own computed ready is never replaced.'},'metadata_checked':metadata,'checked_input_sha256':checked_inputs,'artifacts':artifacts,'artifact_count':len(artifacts),'bytes_before_CAS_dedup':sum(x['bytes']for x in artifacts),'snapshot_layout':'absolute source paths relative to snapshot/; independent CAS hardlinks only within this capsule','limits':['Rocket scalar cache, exact adapters, complete NoC and L2 are coupled; real CPU pipelines and other masters remain external physical actors.','Only external reference pins are replayed. Their service schedule is a validation stimulus, not a predictor or a fitted memory parameter.','Raw unreset async FIFO storage payloads and unconnected outputs are excluded; decoded valid TL payloads and queue control are checked.','Full internal four-state knownness and arbitrary unreset-order invariance remain unproved.','Shuttle default undefined-replay refusal remains; its caches are not yet joined here.','TCM/scratch/serialTL/DRAM services and programmed-image association remain unqualified.'],'automatic_external_service':False,'observed_joined_readiness_or_internal_state_injected':False,'full_model_certified':False,'full_RTL_certified':False,'timing_certified':False,'calibration_usable':False,'loaded_image_association_verified':False,'hardware_contacted':False}
 (O/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'report_sha256':sha(O/'report.json'),'artifacts':len(artifacts),'checked_inputs':len(checked_inputs),'source_words':positive['compared_words']}))
if __name__=='__main__':main()
