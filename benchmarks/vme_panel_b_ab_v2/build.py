"""Build the frozen single-hart weight-layout comparison; no hardware access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
IRIS=Path('/scratch/copparihollmann/iris-mlir-direct-conv-pack')
SDK=Path('/scratch/eygao/iris-cy/.conda-env')
BASE=Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1')
HEADERS=BASE/'int8/library-v1/kernel';RVV=BASE/'harness/layout-pilot-components-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')

def build(out):
 out.mkdir(parents=True,exist_ok=False);app=out/'app';app.mkdir()
 main=HERE/'main.c';body=main.read_text().split('static const shape shapes[]=',1)[1].split(';',1)[0]
 shapes=[tuple(map(int,x))for x in re.findall(r'\{(\d+),(\d+),(\d+)\}',body)];assert len(shapes)==6
 source=[main,IRIS/'kernels/vme_gemm_1x2_reuse.c',IRIS/'kernels/vme_gemm_panel_b_i8.c',IRIS/'kernels/vme_pack_panel_b_i8.c',IRIS/'kernels/vme_pack_at_i8.c',RVV/'panel64.o']
 pins={str(p):sha(p)for p in source+[HERE/'build.py',HERE/'validate.py',IRIS/'kernels/vme_api.h',IRIS/'kernels/vme_panel_b_i8.h',IRIS/'kernels/vme_pack_at_i8.h',HEADERS/'saturn_vme.h',RVV/'emission.json',RVV/'panel64.c']}
 rvv=json.loads((RVV/'emission.json').read_text());assert sha(RVV/'panel64.o')==rvv['object_sha256'];assert (RVV/'panel64.c').read_text()==rvv['source']
 cmake='''cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(iris_vme_panel_b_ab)
target_compile_options(app PRIVATE -std=gnu11)
target_sources(app PRIVATE '''+' '.join('"'+str(p)+'"'for p in source)+''')
target_include_directories(app PRIVATE "'''+str(IRIS/'kernels')+'" "'+str(HEADERS)+'''")
zephyr_compile_options(-fno-tree-vectorize -fno-tree-slp-vectorize)
'''
 for p in source:
  if p.suffix!='.c':continue
  march='rv64gcv_zvl256b'if p.name.startswith('vme_gemm')else'rv64gc'
  cmake+='set_source_files_properties("'+str(p)+'" PROPERTIES COMPILE_FLAGS "-march='+march+' -O3 -std=gnu11")\n'
 (app/'CMakeLists.txt').write_text(cmake)
 config=BASE/'approved-operator-campaign-20261110-v1/memory-roofline-20261111-v1/full-v5/app/prj.conf'
 (app/'prj.conf').write_bytes(config.read_bytes())
 env=dict(os.environ,PATH=str(SDK/'bin')+':'+os.environ['PATH'],ZEPHYR_BASE=str(ROOT/'third_party/zephyr-iris'),ZEPHYR_TOOLCHAIN_VARIANT='cross-compile',CROSS_COMPILE=str(SDK/'riscv-tools/bin/riscv64-unknown-elf-'))
 cm=str(SDK/'bin/cmake');commands=[[cm,'-GNinja','-S',str(app),'-B',str(out/'build'),'-DBOARD=iris','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DBOARD_ROOT='+str(ROOT/'zephyr'),'-DDTS_ROOT='+str(ROOT/'zephyr'),'-DPython3_EXECUTABLE='+str(SDK/'bin/python3'),'-DDTC='+str(SDK/'bin/dtc'),'-DEXTRA_DTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/chipyard/iris/ethan-firesim.overlay')],[cm,'--build',str(out/'build'),'--parallel','2']]
 for phase,cmd in zip(['configure','build'],commands):
  r=subprocess.run(cmd,capture_output=True,env=env,timeout=600);(out/(phase+'.stdout')).write_bytes(r.stdout);(out/(phase+'.stderr')).write_bytes(r.stderr)
  if r.returncode:raise RuntimeError(r.stderr.decode()[-2000:]+r.stdout.decode()[-2000:])
 assert all(sha(p)==h for p,h in pins.items()),'Source changed during build'
 deps=subprocess.check_output([str(SDK/'bin/ninja'),'-C',str(out/'build'),'-t','deps'],text=True);(out/'compiler-dependencies.txt').write_text(deps)
 for l in deps.splitlines():
  if l.startswith('    '):
   p=Path(l.strip());p=p if p.is_absolute()else out/'build'/p
   if p.is_file():pins[str(p.resolve())]=sha(p)
 for p in [app/'CMakeLists.txt',app/'prj.conf',out/'build/zephyr/.config',out/'build/zephyr/linker.cmd',out/'build/compile_commands.json',ROOT/'zephyr/boards/chipyard/iris/ethan-firesim.overlay']:
  pins[str(p)]=sha(p)
 elf=out/'build/zephyr/zephyr.elf';tool=SDK/'riscv-tools/bin/riscv64-unknown-elf-objdump'
 (out/'disassembly.txt').write_bytes(subprocess.check_output([str(tool),'-d',str(elf)]))
 rows=[];points=[]
 for i,(m,n,k)in enumerate(shapes):
  factor=sum((kk%4+1)*(kk%3+1)for kk in range(k));checksum=sum(((int(((r%7)-3)*((c%11)-5)*factor)&0xffffffff)*(r*n+c+1))for r in range(m)for c in range(n))%2**64
  points.append(dict(m=m,n=n,k=k,MACs=m*n*k,expected_checksum=checksum,panel_n=64))
  for route in range(5):
   for rep in range(3):rows.append(dict(id=f'panel_p{i}_c{route}_r{rep}',region='packed_gemm_operator',active_harts=[0],expected_checksums_by_hart=[checksum],pass_id=rep,warmup=False))
 save(out/'cases.json',rows)
 save(out/'manifest.json',dict(schema='iris.vme_panel_b_ab.v2',ELF=str(elf),ELF_sha256=sha(elf),input_sha256=pins,cases=rows,points=points,expected_regions=90,source_image_build_association_verified=False,physical_busy=None,physical_bus_bytes=None,cache_cold_verified=False,roles=dict(controller_hart=2,compute_harts=[0],idle_compute_harts=[1],separate_RVV_and_VME_worker_contexts=True),scope='Already encoded synthetic signed-I8 GEMM ablation; same mathematical inputs and exact output. No activation quantization, scales/bias or full-model inference claim. Factorial: RVV P64; legacy VME/unblockedA; panelB VME/unblockedA; legacy VME/blockedA; panelB VME/blockedA. H2 A transpose and common output copy included in operation windows; weight initialization/packing recorded separately. H2 whole dispatch timer includes matrix registration and initial/final dispatch, H0 operation clock excludes initial registration/wakeup. H0 busy-waits across the H2 preparation/finish phases as in the staged runtime; H2 blocks during H0 compute. Three ordered observations, output poison/checks outside operation.'))
 save(out/'build-receipt.json',dict(commands=commands,ELF=str(elf),ELF_sha256=sha(elf),compiler_sha256=sha(SDK/'riscv-tools/bin/riscv64-unknown-elf-gcc'),rvv_object_sha256=sha(RVV/'panel64.o')))
 return dict(packet=str(out),observations=90,ELF_sha256=sha(elf),hardware_actions=False)

if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(build(a.output.resolve())))
