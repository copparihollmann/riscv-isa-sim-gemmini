#!/usr/bin/env python3
"""Capture final isolated publication contract tests and real Merlin smoke."""
import argparse,hashlib,json,os,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 root=a.candidate.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 os.environ['IRIS_PUBLICATION_ROOT']=str(root);os.environ['IRIS_PUBLICATION_MANIFEST']=str(a.manifest.resolve())
 suite=unittest.defaultTestLoader.discover(str(HERE/'tests'))
 with(out/'tests.log').open('w')as stream:r=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
 module=sys.modules['test_publication'];actual=getattr(module.ExistingOotTests,'result',None)
 run=None
 if actual:
  for key in ['stdout','stderr']:(out/('merlin.'+key)).write_bytes(actual[key])
  run={key:actual[key]for key in ['argv','returncode','elf_sha256','execution_input_sha256']}
  run.update(stdout_sha256=sha(out/'merlin.stdout'),stderr_sha256=sha(out/'merlin.stderr'),region_count=sum(line.startswith(b'IRIS_REGION ')for line in actual['stdout'].splitlines()))
 files=[Path(__file__),HERE/'tests/test_publication.py',root/'spike/provider.py',root/'spike/build.py',root/'spike/selftest.py',
  root/'integration/iris-mlir/simulator.py',root/'integration/iris-mlir/configure_model.py',root/'integration/merlin/src/merlin/runtime/backends/device_simulator.py',a.manifest.resolve()]
 result={'schema':'iris.primary_sdk4.integration_contract.v1','pass':r.wasSuccessful()and run is not None,'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),
  'actual_generic_merlin_run':run,'candidate':str(root),'input_sha256':{str(path):sha(path)for path in files},
  'native_sha256':sha(root/'spike/bin/spike-iris-functional'),'uart_sha256':sha(root/'spike/bin/libsifive_uart.so'),
  'launcher_sha256':sha(root/'spike/bin/spike-iris-launch'),'artifact_sha256':{path.name:sha(path)for path in out.iterdir()if path.is_file()},
  'primary_published':False,'rtl_certified':False,'timing_certified':False,'hardware_contacted':False}
 (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'results.json');raise SystemExit(0 if result['pass']else 1)
if __name__=='__main__':main()
