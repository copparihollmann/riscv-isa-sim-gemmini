#!/usr/bin/env python3
"""New two-phase diagnostic pair differing only in a retained nonexec byte."""
import argparse,hashlib,json,os,shutil,struct,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def locate(raw,address):
 po=struct.unpack_from('<Q',raw,32)[0];ps,pn=struct.unpack_from('<HH',raw,54);hits=[]
 for i in range(pn):
  p=struct.unpack_from('<IIQQQQQQ',raw,po+i*ps)
  if p[0]==1 and p[3]<=address<p[3]+p[5]:hits.append(p[2]+address-p[3])
 assert len(hits)==1;return hits[0]
def sections(raw):
 so=struct.unpack_from('<Q',raw,40)[0];ss,sn=struct.unpack_from('<HH',raw,58);return[struct.unpack_from('<IIQQQQIIQQ',raw,so+i*ss)for i in range(sn)]
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--force-stall-negative',action='store_true');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);parent=R/'build/heldout-phase-diagnostic-v2';pm=json.loads((parent/'manifest.json').read_text());build=json.loads((parent/'build/build.json').read_text());app=out/'app';gen=out/'generated';app.mkdir();gen.mkdir();inputs={str(Path(__file__)):sha(__file__),str(parent/'manifest.json'):sha(parent/'manifest.json'),str(parent/'build/build.json'):sha(parent/'build/build.json')}
 # Read only the preserved, source-bound app snapshot, never alter its inputs.
 for path in (parent/'app').rglob('*'):
  if path.is_file():
   name=str(path.relative_to(R));expected=build['input_sha256'].get(name);assert expected==sha(path),(path,expected);dest=app/path.relative_to(parent/'app');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest);inputs[str(path)]=expected
 for path in (parent/'generated').iterdir():
  if path.is_file():shutil.copyfile(path,gen/path.name);inputs[str(path)]=sha(path)
 source=app/'src/main.c';text=source.read_text();old='  k_tid_t watcher=k_thread_create(&diag_thread,diag_stack,K_THREAD_STACK_SIZEOF(diag_stack),diag_watchdog,NULL,NULL,NULL,-1,0,K_FOREVER);if(k_thread_cpu_pin(watcher,1))fail(0,90);k_thread_start(watcher);';assert text.count(old)==1;text=text.replace(old,'  if(iris_diag_watchdog_enabled){'+old.strip()+'}',1)
 old='  atomic_set(&diag_complete,1);k_sem_take(&diag_joined,K_FOREVER);if(k_thread_join(&diag_thread,K_FOREVER))fail(0,91);';assert text.count(old)==1;text=text.replace(old,'  if(iris_diag_watchdog_enabled){'+old.strip()+'}',1);needle='volatile const unsigned char iris_heldout_full_output=1;';assert text.count(needle)==1;text=text.replace(needle,needle+'\nvolatile const unsigned char iris_diag_watchdog_enabled=1;',1);source.write_text(text)
 for name in ['cases.json','golden.json']:shutil.copyfile(parent/name,out/name);inputs[str(parent/name)]=sha(parent/name)
 extra=out/'negative.conf';extra.write_text('CONFIG_COMPILER_OPT="-DIRIS_DIAG_FORCE_STALL -DIRIS_DIAG_TIMEOUT_MS=10"\n'if a.force_stall_negative else '')
 cmd=[sys.executable,str(R/'zephyr/context_build.py'),'--source',str(R/'third_party/zephyr-iris'),'--patch',str(R/'zephyr/patches/0002-iris-vme-context.patch'),'--uart-profile','ethan-firesim','--app',str(app),'--output',str(out/'build'),'--cmake=-DIRIS_KERNEL_DIR='+str(gen),'--cmake=-DIRIS_TARGET_DIR='+str(R/'integration/iris-mlir')]
 if a.force_stall_negative:cmd+=['--extra-conf',str(extra)]
 for path in[Path(__file__),*[p for p in gen.iterdir()if p.is_file()]]:cmd+=['--input',str(path)]
 with(out/'build.log').open('w')as f:run=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
 if run.returncode:raise RuntimeError('See newpair build.log')
 linked=out/'build/zephyr/zephyr.elf';raw=bytearray(linked.read_bytes());nm=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm');listing=subprocess.check_output([str(nm),'-S','--defined-only',str(linked)],text=True);symbols={}
 for name in ['iris_heldout_full_output','iris_diag_watchdog_enabled']:
  row=next(s.split()for s in listing.splitlines()if s.endswith(' '+name));assert int(row[1],16)==1 and row[2].upper()in['D','R'];address=int(row[0],16);offset=locate(raw,address);matches=[s for s in sections(raw)if s[3]<=address<s[3]+s[5]and s[5]and s[1]!=8];assert len(matches)==1 and matches[0][2]&2 and not matches[0][2]&4 and raw[offset]==1;symbols[name]=dict(address=address,file_offset=offset,bytes=1,nonexecutable=True)
 raw[symbols['iris_heldout_full_output']['file_offset']]=0;on=out/'watch-enabled.elf';on.write_bytes(raw);raw[symbols['iris_diag_watchdog_enabled']['file_offset']]=0;off=out/'watch-disabled.elf';off.write_bytes(raw);aon=on.read_bytes();aoff=off.read_bytes();diff=[i for i,(x,y)in enumerate(zip(aon,aoff))if x!=y];assert diff==[symbols['iris_diag_watchdog_enabled']['file_offset']]and len(aon)==len(aoff);assert all(aon[s[4]:s[4]+s[5]]==aoff[s[4]:s[4]+s[5]]for s in sections(aon)if s[2]&4)
 body=[]
 for path in gen.glob('*.o'):assert sha(path)==sha(parent/'generated'/path.name);body.append(dict(path=str(path),sha256=sha(path),parent_sha256=sha(parent/'generated'/path.name)))
 assert len(body)==8;inputs[str(R/'zephyr/context_build.py')]=sha(R/'zephyr/context_build.py');inputs[str(out/'build/build.json')]=sha(out/'build/build.json');inputs[str(nm)]=sha(nm)
 proof=dict(schema='iris.phase_watch_one_byte_pair_proof.v1',**{'pass':True},differing_file_offsets=diff,only_difference='iris_diag_watchdog_enabled',enabled_value=1,disabled_value=0,watch_byte=symbols['iris_diag_watchdog_enabled'],compact_output_byte=symbols['iris_heldout_full_output'],all_instruction_bytes_identical=True,all_ELF_symbol_and_instruction_addresses_identical=True,file_size=len(aon),parent_compiled_objects=body,variants={k:dict(path=str(p),sha256=sha(p))for k,p in [('enabled',on),('disabled',off)]});save(out/'pair-proof.json',proof)
 m=dict(schema='iris.phase_handoff_watch_pair_build.v1',status='built',phases=pm['phases'],cases=32,regions=32,trials=5,variants=proof['variants'],pair_proof_sha256=sha(out/'pair-proof.json'),force_stall_negative=a.force_stall_negative,no_progress_timeout_ms=10 if a.force_stall_negative else 5000,watchdog_hart=1,parent_ELF_sha256=pm['ELF_sha256'],original_context_thread_reuse_quantization_unchanged=True,exact_parent_compiled_objects_unchanged=True,input_sha256=inputs,diagnostic_only=True,fitting_allowed=False,global_v6_reference_timing_labels_consumed=False,hardware_contacted=False,commands=[cmd]);save(out/'manifest.json',m);print(json.dumps(dict(status='built',pair_proof_sha256=sha(out/'pair-proof.json'),variants=proof['variants'])))
if __name__=='__main__':main()
