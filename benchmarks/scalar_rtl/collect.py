#!/usr/bin/env python3
"""Run identical no-UART scalar probe on standalone RTL or an explicit Spike pair."""
import argparse,json,os,re,subprocess,time
from pathlib import Path
from build import sha,ROOT

def decode(path):
 lines=path.read_text().splitlines()
 if len(lines)!=56 or any(not re.fullmatch('[0-9a-f]{16}',line) for line in lines):raise ValueError('invalid 448-byte signature')
 words=[int(line,16) for line in lines]
 if words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('incomplete/failed mailbox')
 rows=[]
 for hart in range(3):
  for kind in range(2):
   start,end,ibegin,iend,checksum,operations,pad0,pad1=words[8+hart*16+kind*8:16+hart*16+kind*8]
   if end<=start or iend-ibegin!=257 or checksum!=(257 if kind==0 else 292) or operations!=256 or pad0 or pad1:raise ValueError('counter/checksum mismatch')
   rows.append({'hart':hart,'kernel':'dependent256' if kind==0 else 'independent256','start_cycle':start,'end_cycle':end,'cycles':end-start,'instret_delta':iend-ibegin,'checksum':checksum,'alu_operations':256})
 return rows

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--kind',choices=['rtl','spike'],required=True);p.add_argument('--binary',type=Path);p.add_argument('--uart',type=Path)
 p.add_argument('--fixture',type=Path);p.add_argument('--timeout',type=int,default=240);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 build=json.loads((a.build/'build.json').read_text());elf=Path(build['elf']);sig=out/'signature'
 if sha(elf)!=build['elf_sha256']:raise ValueError('changed ELF')
 for path,digest in build['input_sha256'].items():
  if sha(path)!=digest:raise ValueError('changed build input '+path)
 inputs={str(elf):sha(elf),str((a.build/'build.json').resolve()):sha(a.build/'build.json')}
 if a.kind=='rtl':
  manifest=ROOT/'build/rtl-loader-diag/loader-build.json';m=json.loads(manifest.read_text());binary=Path(m['binary'])
  if sha(binary)!=m['binary_sha256']:raise ValueError('changed source-bound RTL binary')
  inputs[str(manifest)]=sha(manifest)
  cmd=[str(binary),'+permissive','+verilator+seed+1','+verilator+rand+reset+2','+loadmem=1','+max-cycles=400000','+init_write=0x2000004:0x1','+init_write=0x2000008:0x1','+signature='+str(sig),'+signature-granularity=8','+permissive-off',str(elf)]
 else:
  if not a.binary or not a.uart:p.error('explicit matched --binary and --uart required')
  binary=a.binary.resolve();uart=a.uart.resolve();inputs[str(uart)]=sha(uart)
  dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
  cmd=[str(binary),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(uart),'--device=sifive_uart,0x10020000']
  for option,path in [('--iris-bootrom=',ROOT/'board/evidence/bootrom.rv64.img'),('--dtb=',ROOT/'board/build/iris.dtb')]:
   cmd.append(option+str(path));inputs[str(path)]=sha(path)
  if a.fixture:
   fixture=a.fixture.resolve();inputs[str(fixture)]=sha(fixture);cmd.extend(['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(out/'graph.json')])
  cmd.extend(['+signature='+str(sig),'+signature-granularity=8',str(elf)])
 inputs[str(binary)]=sha(binary)
 ldd=subprocess.check_output(['ldd',str(binary)],text=True);(out/'ldd.txt').write_text(ldd)
 if 'not found' in ldd:raise ValueError('unresolved runtime library')
 for path in re.findall(r'(?:=>\s*)?(/[^\s]+)',ldd):
  if Path(path).is_file():inputs[path]=sha(path)
 (out/'inputs').mkdir()
 for path,digest in inputs.items():(out/'inputs'/digest).write_bytes(Path(path).read_bytes())
 receipt={'schema':'iris.scalar_reference_run.v1','argv':cmd,'kind':a.kind,'input_sha256':inputs,'runner_sha256':sha(Path(__file__)),
          'source_fir_sha256':json.loads((ROOT/'build/rtl-verilator/manifest.json').read_text())['source_fir_sha256'] if a.kind=='rtl' else None,
          'timing_calibrated':False,'ethan_image_association_verified':False,'calibration_usable_for_firesim':False}
 env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ.get('PATH',''));started=time.monotonic()
 with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
  try:r=subprocess.run(cmd,cwd=out,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout);receipt.update(exit_status=r.returncode,timed_out=False)
  except subprocess.TimeoutExpired:receipt.update(exit_status=None,timed_out=True)
 receipt.update(host_seconds=time.monotonic()-started)
 try:
  if receipt['exit_status']!=0:raise ValueError('unsuccessful process')
  receipt['regions']=decode(sig)
  for path,digest in inputs.items():
   if sha(path)!=digest:raise ValueError('input changed during run')
  receipt['status']='passed_scalar_reference_regions'
 except (ValueError,OSError) as ex:receipt.update(status='failed',error=str(ex))
 receipt['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
 (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({k:receipt[k] for k in ['status','host_seconds','exit_status']}))
 if receipt['status']=='failed':raise SystemExit(1)
if __name__=='__main__':main()
