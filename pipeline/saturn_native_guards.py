#!/usr/bin/env python3
"""Actual-ELF finite-unit admission, dimension and pending-context refusal gates."""
import argparse,copy,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
from pipeline.saturn_live_manifest import generate
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def patch_at(data,pc,old,new):
 raw=bytearray(data);h=struct.unpack_from('<16sHHIQQQIHHHHHH',raw);matches=[]
 for n in range(h[10]):
  typ,flags,off,addr,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,h[5]+n*h[9])
  if typ==1 and addr<=pc and pc+len(old)<=addr+filesz:matches.append(off+pc-addr)
 if len(matches)!=1 or raw[matches[0]:matches[0]+len(old)]!=old or len(old)!=len(new):raise ValueError('exact same-layout ELF patch failed')
 raw[matches[0]:matches[0]+len(new)]=new;return bytes(raw)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-saturn-live-v1/spike');a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');original=ROOT/'build/saturn-timing-live-guest-v1/guest.elf';admission=original.with_name('admission.json');original_manifest=generate(original,admission);fixture_template=(ROOT/'build/saturn-native-guarded-v1/explicit.fixture').read_text();identity=sha(binary),sha(plugin);rows=[]
 cases=['wrong-PC','wrong-raw','missing-command','wrong-schema','vector-memory','FP-compute','K2','pending-context']
 for name in cases:
  folder=out/name;folder.mkdir();elf=folder/'guest.elf';raw=original.read_bytes()
  if name=='K2':raw=patch_at(raw,0x800004c6,bytes.fromhex('8546'),bytes.fromhex('8946'))
  elif name=='pending-context':raw=patch_at(raw,0x800004ea,bytes.fromhex('85028502'),struct.pack('<I',0x30046073))
  elf.write_bytes(raw);manifest=folder/'native.manifest';text=original_manifest;expected=''
  if name=='wrong-PC':text=text.replace('command 0x8000049a ','command 0x90000000 ');expected='IRIS_SATURN_ELF_PC_RAW_OUTSIDE_FINITE_ADMISSION'
  elif name=='wrong-raw':text=text.replace('0x5e03b257','0x5e04b257');expected='IRIS_SATURN_ELF_PC_RAW_OUTSIDE_FINITE_ADMISSION'
  elif name=='missing-command':text='\n'.join(x for x in text.splitlines()if not x.startswith('command 0x8000049a '))+'\n';expected='IRIS_SATURN_EXACT_NINE_COMMAND_ADMISSION_REQUIRED'
  elif name=='wrong-schema':text=text.replace('iris.saturn.finite_integer_K1.v1','unsupported');expected='IRIS_SATURN_ADMISSION_SCHEMA'
  elif name=='vector-memory':text=text.replace('0xf2880077','0x02050407');expected='IRIS_SATURN_FIRST_VECTOR_MEMORY_SERVICE_NOT_CONNECTED'
  elif name=='FP-compute':text=text.replace('0xf2880077','0xf2881077');expected='IRIS_SATURN_FIRST_SHARED_FPU_OR_FP_COMPUTE_NOT_ADMITTED'
  else:
   text=text.replace(sha(original),sha(elf));expected='IRIS_SATURN_PARTIAL_REDUCTION_INTENTS_K_GREATER_THAN_ONE_UNMODELED'if name=='K2'else'IRIS_SATURN_PENDING_CONTEXT_CHANGE_UNMODELED'
  manifest.write_text(text);fixture=folder/'explicit.fixture';fixture.write_text('\n'.join('saturn_live finite-integer-K1-hart0 '+str(manifest)if line.startswith('saturn_live ')else line for line in fixture_template.splitlines())+'\n');graph=folder/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)];start=time.perf_counter();r=subprocess.run(argv,text=True,capture_output=True,timeout=60,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']));(folder/'stdout').write_text(r.stdout);(folder/'stderr').write_text(r.stderr);passed=r.returncode!=0 and expected in r.stderr;rows.append(dict(name=name,argv=argv,exit_status=r.returncode,expected_diagnostic=expected,pass_=passed,host_seconds=time.perf_counter()-start,ELF_sha256=sha(elf),manifest_sha256=sha(manifest),fixture_sha256=sha(fixture),graph_sha256=sha(graph)if graph.exists()else None,stdout_sha256=sha(folder/'stdout'),stderr_sha256=sha(folder/'stderr')));print(json.dumps(dict(name=name,pass_=passed,stderr=r.stderr[-900:])),flush=True)
 if identity!=(sha(binary),sha(plugin)):raise ValueError('native guard inputs changed')
 files=[Path(__file__).resolve(),ROOT/'pipeline/saturn_live_manifest.py',ROOT/'spike/run_functional.py',original,admission,binary,plugin,ROOT/'build/saturn-native-guarded-v1/explicit.fixture',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];report=dict(schema='iris.saturn.actual_native_scope_guards.v1',status='passed_actual_ELF_source_unit_guards'if all(r['pass_']for r in rows)else'preserved_failed_native_guard_attempt',binary_sha256=identity[0],uart_sha256=identity[1],input_sha256={str(p):sha(p)for p in files},rows=rows,hardware_contacted=False,timing_certified=False);(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0if report['status'].startswith('passed')else 1)
if __name__=='__main__':main()
