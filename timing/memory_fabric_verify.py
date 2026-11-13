#!/usr/bin/env python3
"""Verify the immutable component capsule and rebuild consumers from its snapshot."""
import hashlib,json,stat,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];C=R/'build/memory-fabric-component-v1';O=R/'build/memory-fabric-component-v1-verify'
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def snap(path):return C/'snapshot'/str(Path(path).absolute()).lstrip('/')
def main():
 if O.exists():raise ValueError('fresh independent verification output required')
 source=R/'timing';report=json.loads((C/'report.json').read_text());before=sha(C/'report.json');count=0
 for item in report['artifacts']:
  p=C/item['snapshot'];assert p.is_file()and sha(p)==item['sha256'],item['original'];assert stat.S_IMODE(p.stat().st_mode)==item['mode'];count+=1
 O.mkdir();ctx=R/'build/memory-fabric-context-sdk-v2';model=R/'build/memory-fabric-coupled-native-v4';replay=R/'build/memory-fabric-replay-v2';sdkdirs=[snap(model/'sdk'),snap(ctx/'cache/sdk'),snap(ctx/'noc/sdk'),snap(ctx/'adapters/sdk')];libs=[snap(model/'sdk/libiris_memory_fabric.a'),snap(ctx/'cache/sdk/libiris_cache_hierarchy.a'),snap(ctx/'noc/sdk/libiris_noc.a'),snap(ctx/'adapters/sdk/libiris_memory_adapters.a')];commands=[];tests=[];start=time.monotonic()
 def run(argv,stem,expected=0):
  commands.append(argv)
  with(O/(stem+'.stdout')).open('w')as stdout,(O/(stem+'.stderr')).open('w')as stderr:q=subprocess.run(argv,stdout=stdout,stderr=stderr)
  assert q.returncode==expected,(stem,q.returncode);tests.append({'name':stem,'exit_status':q.returncode,'stdout_sha256':sha(O/(stem+'.stdout')),'stderr_sha256':sha(O/(stem+'.stderr'))})
 for name,cpp in [('semantic','memory_fabric_check.cpp'),('replay','memory_fabric_replay.cpp')]:
  argv=['/usr/bin/g++','-O3','-std=c++20',*['-I'+str(p)for p in sdkdirs],'-I'+str(snap(replay)),str(snap(source/cpp)),*map(str,libs),'-pthread','-latomic','-lz','-o',str(O/name)];run(argv,'compile-'+name)
 run([str(O/'semantic')],'semantic')
 semantic=[json.loads(line)for line in(O/'semantic.stdout').read_text().splitlines()];assert semantic[-1]['checks']==1805
 trace=snap(R/'build/memory-fabric-rtl-v1/fabric-ports.bin.gz');run([str(O/'replay'),str(trace)],'closed-replay');positive=json.loads((O/'closed-replay.stdout').read_text());assert positive['frames']==74903 and positive['compared_words']==23703753
 run([str(O/'replay'),str(trace),'--wrong-data'],'wrong-data',1)
 run([str(O/'replay'),str(snap(replay/'truncated-frame.bin.gz'))],'truncated',2)
 run([str(O/'replay'),str(snap(replay/'active-aux-tlb.bin.gz'))],'active-aux',2)
 # Archive-only executables additionally retain the exact independently
 # qualified host-ownership test and SDK identity-refusal paths.
 run([str(snap(ctx/'noc/order-check')),str(snap(R/'build/noc-network-replay-v1/control8-step.input'))],'owner-context')
 owner=json.loads((O/'owner-context.stdout').read_text());assert owner['physical_word_comparisons']==73443582 and owner['caller_context_restoration_checks']==1626552
 run([str(snap(model/'wrong-sdk-check'))],'wrong-sdk',1)
 assert 'SDK_IDENTITY_MISMATCH'in(O/'wrong-sdk.stderr').read_text()
 assert sha(C/'report.json')==before
 result={'schema':'iris.memory_fabric_capsule_independent_verify.v1','status':'passed','capsule_sha256':before,'artifacts_verified':count,'commands':commands,'tests':tests,'rebuilt_from_archived_source_and_SDKs':True,'rebuilt_semantics':semantic[-1],'rebuilt_closed_replay':positive,'owner_context':owner,'replay_binary_byte_identical':sha(O/'replay')==sha(snap(replay/'replay')),'semantic_binary_byte_identical':sha(O/'semantic')==sha(snap(model/'check')),'input_sha256':{str(p):sha(p)for p in [Path(__file__),C/'report.json',Path('/usr/bin/g++')]},'host_seconds':time.monotonic()-start,'capsule_unchanged':True,'primary_or_engine_changed':False,'hardware_contacted':False,'timing_certified':False}
 (O/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(O/'report.json'),'artifacts_verified':count,'replay_binary_identical':result['replay_binary_byte_identical'],'semantic_binary_identical':result['semantic_binary_byte_identical']}))
if __name__=='__main__':main()
