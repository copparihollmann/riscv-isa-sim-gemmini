#!/usr/bin/env python3
"""Verify actual six-task FP/RVV context stress against an independent oracle."""
import argparse,hashlib,json,os,struct,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike.run_functional import command,symbols
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def oracle(i):
    h=14695981039346656037
    for r in range(12):
        data=struct.pack('<32Q',*[0x3ff0000000000000|((i+1)<<40)|((r+1)<<24)|(n<<12) for n in range(32)])
        data+=bytes((i*37+r*13+n*7)&255 for n in range(1024))
        data+=struct.pack('<6Q',i%3,[17,15,7,5,31,13][i],[0xc0,0xc9,0xd0,0xd9,0xc2,0xd1][i],((i%4)<<1)|(i&1),32,((i%5)<<5)|((i*3+r)&31))
        for b in data:h=((h^b)*1099511628211)&((1<<64)-1)
    return h
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--elf',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--timeout',type=int,default=90)
    p.add_argument('--binary',type=Path,default=ROOT/'build/zephyr-binary-snapshot/spike');p.add_argument('--uart',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'results.json').unlink(missing_ok=True)
    elf=a.elf.resolve();build=elf.parents[1]/'build.json';built=json.loads(build.read_text())
    if built['status']!='built' or built['elf_sha256']!=sha(elf):raise RuntimeError('ELF differs from successful build')
    if any(sha(ROOT/name)!=digest for name,digest in built['input_sha256'].items()):raise RuntimeError('Current sources differ from this build; preserve and rebuild explicitly')
    binary=a.binary.resolve();plugin=a.uart.resolve() if a.uart else binary.parent/'libsifive_uart.so'
    (out/'runner-source.py').write_bytes(Path(__file__).read_bytes())
    argv=command(binary,elf);argv=[('--extlib='+str(plugin)) if x.startswith('--extlib=') else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
    env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v) for k,v in symbols(elf).items() if k in ['z_fatal_error','z_riscv_fatal_error']))
    start=time.perf_counter();timed=False
    try:r=subprocess.run(argv,capture_output=True,timeout=a.timeout,env=env)
    except subprocess.TimeoutExpired as e:r=subprocess.CompletedProcess(argv,-1,e.stdout or b'',e.stderr or b'');timed=True
    (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
    rows=[json.loads(line.split(' ',1)[1]) for line in r.stdout.decode(errors='replace').splitlines() if line.startswith('IRIS_CONTEXT ')]
    passed=r.returncode==0 and len(rows)==6 and {x['thread'] for x in rows}==set(range(6)) and b'PASSED six competing RVV/IEEE contexts' in r.stdout and b'FATAL' not in r.stdout
    for x in rows:passed &= x['hart']==x['thread']//2 and x['rounds']==12 and x['timer_ticks']>0 and x['checksum']==oracle(x['thread']) and x['end_cycle']>x['start_cycle']
    receipt={'status':'passed' if passed else 'failed','argv':argv,'exit_status':r.returncode,'timed_out':timed,'host_seconds':time.perf_counter()-start,'rows':rows,'expected_checksums':[oracle(i) for i in range(6)],'input_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [elf,build,binary,plugin,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',Path(__file__)]},'source_patch_sha256':built['source_patch_sha256'],'stdout_sha256':sha(out/'stdout'),'stderr_sha256':sha(out/'stderr'),'rtl_certified':False,'timing_certified':False}
    (out/'results.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':receipt['status'],'rows':rows,'receipt':str(out/'results.json')}));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
