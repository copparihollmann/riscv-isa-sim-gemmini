#!/usr/bin/env python3
"""Build and check private numeric intents without executing the main CPU/unit hook."""
import argparse,hashlib,json,shlex,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);src=ROOT/'pipeline/riscv-isa-sim-saturn-live';base=ROOT/'build/spike-rocket-serial-v1';manifest=ROOT/'build/rocket-serial-frozen-15b10335/manifest.json';m=json.loads(manifest.read_text())
 if sha(base/'spike')!=m['binary_sha256']:raise ValueError('frozen native SDK identity changed')
 libs=shlex.split(next(line.split(':=',1)[1]for line in(base/'Makefile').read_text().splitlines()if line.startswith('LIBS ')));compiler=Path(shutil.which('g++')).resolve();sources=[src/'riscv/iris_saturn_oracle.cc',ROOT/'pipeline/test_saturn_private_oracle.cpp'];binary=out/'check';command=[str(compiler),'-std=c++20','-O2','-I'+str(base),'-I'+str(src/'riscv'),'-I'+str(src),*[str(p)for p in sources],'-L'+str(base),'-Wl,--start-group','-lriscv','-ldisasm','-lsoftfloat','-lfesvr','-lfdt',*libs,'-Wl,--end-group','-pthread','-ldl','-o',str(binary)];r=subprocess.run(command,text=True,capture_output=True);(out/'build.log').write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError('private oracle build failed: '+r.stderr[-4000:])
 r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
 if r.returncode:raise RuntimeError('private oracle invariants failed: '+r.stderr[-4000:])
 paths=[Path(__file__).resolve(),*sources,src/'riscv/iris_saturn_oracle.h',compiler,manifest,base/'pipeline-build.json',base/'Makefile',*[base/name for name in ['libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a']],*[Path(x)for x in libs if x.endswith('.a')]];findings=json.loads(r.stdout);report=dict(schema='iris.saturn_private_numeric_oracle.v1',status=findings['status'],findings=findings,command=command,binary_sha256=sha(binary),input_sha256={str(p):sha(p)for p in paths},real_state_mutated=False,memory_or_device_service=False,source_CPU_unit_hook_executed=False,timing_certified=False);(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
