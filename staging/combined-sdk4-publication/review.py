#!/usr/bin/env python3
"""Freeze exact local publication changes and their meaningful acceptance gates."""
import argparse,difflib,hashlib,json,os,stat,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SOURCES=['README.md','build.py','provider.py','selftest.py','run_functional.py','run_selftest.sh','run_native_selftest.sh','run_csr_selftest.sh','tests/test_provider.py','functional_fixture.cc','native_fp8_handlers_test.cc','ieee_fma_handlers_test.cc','shared_fma_handlers_test.cc','fpcomp_handlers_test.cc','csr_handlers_test.cc','fpcomp_guest.c','audit_fpcomp_decoder.py','audit_shared_decoder.py','compile_bitmanip.py','compile_fpcomp.py','compile_ieee_fma.py','compile_shared_fma.py','compile_saturn.py']
INTEGRATION=['integration/iris-mlir/configure_model.py','integration/iris-mlir/simulator.py','integration/iris-mlir/provenance.json','integration/merlin/src/merlin/runtime/backends/device_simulator.py','integration/manifest.json','integration/manifest-before-sdk4.json','integration/patches/iris-mlir.patch','integration/patches/merlin.patch']
ALIASES=['spike/current','spike/provenance.json','spike/iris.patch','spike/include','spike/build','spike/source','spike/bin/spike-iris-functional','spike/bin/libsifive_uart.so','spike/bin/spike-iris-launch','third_party/riscv-isa-sim-current']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args();root=a.candidate.resolve();out=a.output.resolve()
 if a.verify:
  report=json.loads((out/'report.json').read_text())
  for name,value in report['input_sha256'].items():
   if sha(Path(name))!=value:raise ValueError('Review source/evidence changed: '+name)
  for name,value in report['artifact_sha256'].items():
   if sha(out/name)!=value:raise ValueError('Review artifact changed: '+name)
  for name,target in report['symlink_updates'].items():
   if os.readlink(root/name)!=target:raise ValueError('Candidate alias changed: '+name)
  print(json.dumps({'status':'verified','report_sha256':sha(out/'report.json'),'primary_published':False}));return
 out.mkdir(parents=True,exist_ok=False);release=(root/'spike/current').resolve()
 contract=ROOT/'build/sdk4-publication-contract-frozen/results.json';c=json.loads(contract.read_text())
 if c['pass']is not True or c['tests']!=16 or c['actual_generic_merlin_run']['region_count']!=12:raise ValueError('Contract gate incomplete')
 for name,value in c['input_sha256'].items():
  if sha(Path(name))!=value:raise ValueError('Contract source changed: '+name)
 mlir=root/'build/actual-merlin-mlir-gemm2/execution/results.json';m=json.loads(mlir.read_text())
 if not(m['pass']and m['real_merlin_mlir_executed']and all(r['pass']and r['full_output_elements']==12288 for r in m['runs'])):raise ValueError('Actual shipped/twin compiler gate incomplete')
 rebuilt=[]
 for path in(root/'build').glob('sdk4-primary-rebuild-*/rebuild.json'):
  r=json.loads(path.read_text())
  if r['binary_byte_identical']and r['uart_byte_identical']and(path.parent/'selftests/results.json').exists():
   s=json.loads((path.parent/'selftests/results.json').read_text())
   if s['pass']and len(s['rows'])==37:rebuilt.append(path)
 if len(rebuilt)!=1:raise ValueError('Expected one admitted full default rebuild+selftest')
 receipts=[contract,mlir,root/'build/actual-merlin-mlir-gemm2/results.json',rebuilt[0],rebuilt[0].parent/'selftests/results.json',
  ROOT/'build/sdk4-publication-gates-v1/default-scalar6/results.json',ROOT/'build/sdk4-publication-gates-v1/default-mixed9/results.json',
  ROOT/'build/sdk4-publication-gates-v1/fpcomp-final/results.json']
 for name,count in [('default-scalar6',6),('default-mixed9',9)]:
  r=json.loads((ROOT/'build/sdk4-publication-gates-v1'/name/'results.json').read_text())
  if not r['status'].startswith('passed')or len(r['regions'])!=count or r['binary_sha256']!=c['native_sha256']:raise ValueError('Default Zephyr gate failed')
 fp=json.loads(receipts[-1].read_text())
 if fp['pass']is not True:raise ValueError('Regenerated FPComp guest failed')
 sources=['spike/'+name for name in SOURCES]+INTEGRATION
 updates={};chunks=[]
 for name in sources:
  new=root/name;old=ROOT/name
  if not new.is_file():raise ValueError('Candidate update absent: '+name)
  updates[name]={'sha256':sha(new),'mode':stat.S_IMODE(new.stat().st_mode),'old_sha256':sha(old)if old.is_file()else None}
  before=old.read_text().splitlines(keepends=True)if old.is_file()else[];after=new.read_text().splitlines(keepends=True)
  if name.startswith('integration/patches/'):continue
  chunks.extend(difflib.unified_diff(before,after,fromfile='a/'+name if old.exists()else'/dev/null',tofile='b/'+name))
 (out/'publication-source.patch').write_text(''.join(chunks))
 aliases={name:os.readlink(root/name)for name in ALIASES}
 inventory={}
 for directory in[release,root/'spike/historical-5e6-dispatch']:
  for path in directory.rglob('*'):
   if path.is_file()and'.git'not in path.parts and'__pycache__'not in path.parts:inventory[str(path.relative_to(root))]={'sha256':sha(path),'mode':stat.S_IMODE(path.stat().st_mode)}
 (out/'release-files.json').write_text(json.dumps(inventory,indent=2)+'\n')
 preserved={'spike/bin/spike-iris-functional':'5e6cc309b8cd1085e30ee0c31b43c2bc27ef9c325136a94bfdd4d86700787f7e',
 'spike/bin/libsifive_uart.so':'28e8162a04b8492df4f8282ed86f01bd7a25974bbd435892211fc479f9060bb9',
 'build/combined-frozen-35901887/spike':c['native_sha256'],'build/combined-candidate-35901887/spike':c['native_sha256']}
 for name,value in preserved.items():
  if sha(ROOT/name)!=value:raise ValueError('Preserved live artifact changed: '+name)
 common=subprocess.check_output(['git','-C',str(ROOT/'third_party/riscv-isa-sim-combined'),'rev-parse','--git-common-dir'],text=True).strip()
 if common!=str(ROOT/'third_party/riscv-isa-sim/.git'):raise ValueError('Live common Git anchor changed')
 inputs={str(root/name):item['sha256']for name,item in updates.items()}
 inputs.update({str(root/name):item['sha256']for name,item in inventory.items()})
 for directory in[HERE,ROOT/'build/sdk4-publication-gates-v1',ROOT/'build/sdk4-publication-contract-frozen',root/'build/actual-merlin-mlir-gemm2',rebuilt[0].parent]:
  for path in directory.rglob('*'):
   if path.is_file()and'__pycache__'not in path.parts:inputs[str(path)]=sha(path)
 for path in receipts:inputs[str(path)]=sha(path)
 for name,value in preserved.items():inputs[str(ROOT/name)]=value
 report={'schema':'iris.primary_sdk4.publication_review.v1','status':'review_ready_not_published','candidate_root':str(root),
  'source_updates':updates,'symlink_updates':aliases,'new_release_inventory':'release-files.json',
  'native_sha256':c['native_sha256'],'uart_sha256':c['uart_sha256'],'launcher_sha256':c['launcher_sha256'],'native_device_abi':4,
  'gates':{'default_full_source_rebuild_exact':True,'rebuilt_actual_handler_and_guest_cases':37,'contract_tests':16,'primary_unit_tests':33,
    'default_zephyr_regions':[6,9],'generic_merlin_regions':12,'real_mlir_shipped_twin_elements_per_kind':12288,'regenerated_fpcomp_pass':True},
  'receipts':{str(path):sha(path)for path in receipts},'live_common_git_anchor_preserved':common,
  'do_not_publish':['Do not replace/rename third_party/riscv-isa-sim or its .git/index; it remains historical and anchors16activeworktrees.',
    'Do not replace integration/merlin/merlin/python/merlin symlink; its backend mirror resolves src and updates automatically.',
    'Do not publish candidate build outputs, loose regenerated benchmark ELF/receipts, or exploratory failures as active proofs.'],
  'coordinated_switch_order':['Wait for coordinator review and quiet primary software consumers; hardware coordinator work is separate.',
    'Preserve entire old spike tree/build and old companion source/patch/manifest bytes in an immutable rollback backup;5e6/359 frozen snapshots stay untouched.',
    'Stage versioned release payload, corrected dispatch/source files, SDK views and companion deltas before enabling newselection.',
    'Initial migration covers several paths, so use coordinator quiescence+rollback; it is not a multi-file atomic filesystem transaction.',
    'Set current symlink last with atomic rename; subsequent epochs can select one immutable release through that pointer.',
    'Validate alias/source/pair hashes, provider/default/full-mode refusal and fresh deployment manifest after activation; retain exact pre-switch receipts.'],
  'known_limits':['Complete model/knownness/RTL/image/timingcertification remain false; explicit functional optin only.',
    'Portable snapshot normalizes the base disassembler symlink into identical bytes; canonical inspection projection preserves its Git type.',
    'Fatal-aware generic launcher requires unstripped RV64 ELF and recognizes explicit knownfatal symbols/PCs; existingZephyr runners supply their ownfatalPCs.',
    'Old native-only descriptors remain supported; native and declaredsupport artifacts are additionallychecked when supplied.',
    'Historical loose test artifacts retain old bytes; corrected selected-release selftests use frozen32/5fixtures.'],
  'preserved_failures':['ambient Conda compiler selection produced distinctde9f/1093 and was refused; pinned hostcompiler path fixed defaultCLI.',
    'Compiler gate output outside selectedmodelroot was refused by existing contextsourceguard; finalgate uses internalbuildoutput.',
    'CanonicalGit projection required preserving base symlinktype and normalizing private index afterclone; no live Gitmetadata changed.'],
  'input_sha256':inputs,'artifact_sha256':{path.name:sha(path)for path in out.iterdir()if path.is_file()},
  'primary_published':False,'hardware_contacted':False,'rtl_certified':False,'timing_certified':False,'held_out_2pct':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'report.json')
if __name__=='__main__':main()
