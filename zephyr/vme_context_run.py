#!/usr/bin/env python3
"""Run real Zephyr VME context/migration stress with independent bitwise goldens."""
import argparse,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def update(h,data):
    for b in data:h=((h^b)*1099511628211)&((1<<64)-1)
    return h
def oracle(i):
    h=14695981039346656037
    for r in range(8):
        data=struct.pack('<32Q',*[0x3ff0000000000000|((i+1)<<40)|((r+1)<<24)|(n<<12) for n in range(32)])
        data+=bytes((i*37+r*13+n*7)&255 for n in range(1024))
        data+=struct.pack('<7Q',i%3,[17,23,27,31][i],0xd2 if i==2 else 0xc0|(0x100 if i&1 else 0),((i%4)<<1)|(i&1),32,((i%5)<<5)|((i*3+r)&31),(1 if i==2 else 4)|([4,3,1,2][i]<<5)|([9,11,19,7][i]<<10))
        tiles=[0x80000000^(i*0x1020304)^(r*0x10001)^(t*0x100000)^(row*0x101)^col for t in range(4) for row in range(32) for col in range(32)]
        for t in range(4):tiles[t*1024:t*1024+8]=[0,0x80000000,0x7f800000,0xff800000,0x7fc01234,0x7fa05678,0xffffffff,1]
        h=update(h,data);h=update(h,struct.pack('<4096I',*tiles))
        value=struct.unpack('<I',struct.pack('<f',float((2 if r&1 else 1)*2*(i+1))))[0] if i&1 else 2*(r+3)*(i+1)
        for row in range(32):
            for col in range(32):tiles[i*1024+row*32+col]=value if row<3+i and col<4+i else 0
        h=update(h,struct.pack('<4096I',*tiles))
    return h
def producer_oracle():
    h=14695981039346656037
    for r in range(8):h=update(h,struct.pack('<8I',*[r*8+n+7 for n in range(8)]))
    return h
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=90)
    p.add_argument('--binary',type=Path,default=ROOT/'build/zephyr-binary-snapshot/spike');p.add_argument('--uart',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'results.json').unlink(missing_ok=True)
    elf=a.elf.resolve();build=elf.parents[1]/'build.json';receipt=json.loads(build.read_text())
    if receipt['status']!='built' or receipt['elf_sha256']!=sha(elf):raise RuntimeError('ELF differs from successful build')
    if any(sha(ROOT/name)!=digest for name,digest in receipt['input_sha256'].items()):raise RuntimeError('Current sources differ from this build; preserve and rebuild explicitly')
    binary=a.binary.resolve();plugin=a.uart.resolve() if a.uart else binary.parent/'libsifive_uart.so'
    argv=command(binary,elf);argv=[('--extlib='+str(plugin)) if x.startswith('--extlib=') else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
    env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v) for k,v in symbols(elf).items() if k in ['z_fatal_error','z_riscv_fatal_error']))
    inputs={str(p.relative_to(ROOT)):sha(p) for p in [elf,build,binary,plugin,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',Path(__file__)]}
    (out/'runner-source.py').write_bytes(Path(__file__).read_bytes())
    start=time.perf_counter();timed=False
    try:r=subprocess.run(argv,capture_output=True,timeout=a.timeout,env=env)
    except subprocess.TimeoutExpired as e:r=subprocess.CompletedProcess(argv,-1,e.stdout or b'',e.stderr or b'');timed=True
    (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
    rows=[json.loads(line.split(' ',1)[1]) for line in r.stdout.decode(errors='replace').splitlines() if line.startswith('IRIS_VME_CONTEXT ')]
    producer=[json.loads(line.split(' ',1)[1]) for line in r.stdout.decode(errors='replace').splitlines() if line.startswith('IRIS_VME_PRODUCER ')]
    passed=r.returncode==0 and len(rows)==4 and {x['thread'] for x in rows}==set(range(4)) and b'PASSED explicit VME ownership' in r.stdout and b'FATAL' not in r.stdout and b'FATAL' not in r.stderr
    for x in rows:passed &= x['hart_mask']==3 and x['rounds']==8 and x['timer_ticks']>0 and x['saves']>0 and x['restores']>0 and x['checksum']==oracle(x['thread'])
    passed &= producer==[{'hart':2,'rounds':8,'checksum':producer_oracle(),'vme_refused':True}]
    passed &= all(sha(ROOT/name)==digest for name,digest in inputs.items())
    result={'status':'passed' if passed else 'failed','argv':argv,'exit_status':r.returncode,'timed_out':timed,'host_seconds':time.perf_counter()-start,'rows':rows,'producer':producer,'expected_checksums':[oracle(i) for i in range(4)],'input_sha256':inputs,'source_patch_sha256':receipt['source_patch_sha256'],'stdout_sha256':sha(out/'stdout'),'stderr_sha256':sha(out/'stderr'),'tile_context_abi':'explicit-first-use-zero-all-four-tiles','automatic_unregistered_vme_context':False,'rtl_certified':False,'timing_certified':False}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'rows':rows,'receipt':str(out/'results.json')}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
