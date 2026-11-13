"""Read-only, finite audit of the actual RVV ASM benchmark instruction bytes."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[1]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def inspect(build):
    elf = (build / 'guest.elf').read_bytes()
    h = struct.unpack_from('<16sHHIQQQIHHHHHH', elf)
    assert h[0][:7] == b'\x7fELF\x02\x01\x01' and h[2] == 243
    sections = [struct.unpack_from('<IIQQQQIIQQ', elf, h[6]+i*h[11]) for i in range(h[12])]
    def content(s): return elf[s[4]:s[4]+s[5]]
    symbols = {}
    for s in sections:
        if s[1] != 2: continue
        strings = content(sections[s[6]])
        for off in range(0, s[5], 24):
            name, info, other, index, address, size = struct.unpack_from('<IBBHQQ', elf, s[4]+off)
            text = strings[name:strings.index(b'\0',name)].decode()
            if index and index < len(sections): symbols[text]=(address,size,index)
    def raw(name):
        address,size,index=symbols[name];s=sections[index]
        return elf[s[4]+address-s[3]:s[4]+address-s[3]+size]
    def instructions(name):
        data=raw(name);offset=0;result=[]
        while offset<len(data):
            lo=int.from_bytes(data[offset:offset+2],'little');width=4 if lo&3==3 else 2
            result.append(int.from_bytes(data[offset:offset+width],'little'));offset+=width
        assert offset==len(data)
        return result
    patterns={
        'integer0':[0x02880457], 'integer1':[0x02880457,0x03880c57],
        'integer2':[0x02880457,0x02880c57], 'fp0':[0x02881457],
        'fp1':[0x02881457,0x03881c57], 'fp2':[0x02881457,0x02881c57],
        'load':[0x0205e407], 'store':[0x02066427],
        'load_use':[0x0205e407,0x02880c57],
        'load_independent':[0x0205e407,0x0380bc57],
        'store_compute':[0x02066427,0x0380bc57],
        'matrix_int':[0xf2880077], 'matrix_fp8':[0xf2881077]}
    checked=[]
    for suffix,pattern in patterns.items():
        name='asm_'+suffix;values=instructions(name)
        assert values[:-3]==pattern*16
        assert values[-3:]==[0x157d,0xfd5d if len(pattern)==1 else 0xfd3d,0x8082]
        checked.append(dict(name=name,address=symbols[name][0],target_instructions_per_block=16*len(pattern),
                            loop_instructions_per_block=2,scalar_memory_or_helper_calls=0))
    for n in (1,4,16,64):
        values=instructions('asm_row'+str(n));expected=[]
        for i in range(n): expected += [0x4e01+((i%32)<<2),0x43fe6c57]
        assert values==expected+[0x8082]
        checked.append(dict(name='asm_row'+str(n),target_instructions=n,row_indices=[i%32 for i in range(n)],scalar_memory_or_helper_calls=0))
    wrapper=instructions('asm_measure')
    first=wrapper.index(0xb0002af3);last=wrapper.index(0xb0002d73)
    assert wrapper[first:last+1]==[0xb0002af3,0xb0202b73,0x000480e7,0xb0202bf3,
                                  0xb0002c73,0x0330000f,0xb0202cf3,0xb0002d73]
    # This sequence is exact in the compiled executable; the call target was
    # selected in C before entry, and save/restore/CLINT are outside it.
    assert all(x&0x7f not in (3,0x23) for x in wrapper[first:last+1])
    corpus=json.loads((build/'corpus.json').read_text());cases=corpus['cases']
    assert len(cases)==1320 and {c['hart'] for c in cases}=={0,1}
    assert [c['hart'] for c in cases]==[0]*660+[1]*660
    assert {k:sum(c['internal_split']==k for c in cases)for k in ('train','reserved_holdout')}=={'train':978,'reserved_holdout':342}
    mask=(1<<64)-1
    def fp(value,sew): return int.from_bytes(struct.pack({16:'<e',32:'<f',64:'<d'}[sew],value),'little')
    words=0
    for c in cases:
        kind=c['kind_id'];n=c['n'];vl=c['vl'];values=[]
        if kind>=8:
            value=n*c['mode']*(6 if kind==8 else 1)
            values=[(value if kind==8 else fp(value,32)) if r<vl and col<vl else 0 for r in range(32)for col in range(32)]
        else:
            for stream in range(c['streams']):
                for i in range(vl):
                    if kind<2:value=n+int(c['mode']==2 and stream==1)
                    elif kind==2:value=i+3
                    elif kind==3:value=3
                    elif kind==4:value=i+3+stream
                    elif kind==5:value=n if stream else i+3
                    elif kind==6:value=n if stream else 3
                    else:value=6
                    values.append(fp(value,c['sew']) if kind==1 else value)
        checksum=14695981039346656037
        for value in values: checksum=((checksum^value)*1099511628211)&mask
        assert checksum==c['expected_checksum'],c['case_id']
        words+=len(values)
        if kind!=7: assert n in (16,64) and n%16==0
    assert words==184128
    emit=instructions('emit')
    assert all(not(x&3==3 and x&0x7f in (0x57,0x27,0x07)) for x in emit)
    # Actual final sentinel SD and fenced call to emit, not a source-only order.
    # Address-dependent immediates are checked against bound disassembly below.
    dis=(build/'disassembly.txt').read_text()
    assert re.search(r'[0-9a-f]+:.*sd\s+zero,.*rvv_measurements_done',dis)
    assert re.search(r'sd\s+zero,.*rvv_measurements_done[^\n]*\n\s*[0-9a-f]+:.*fence\s+rw,rw\n\s*[0-9a-f]+:.*jal.*<emit>',dis)
    matched=0
    for address,word in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+',dis,re.M):
        address=int(address,16);wanted=bytes.fromhex(word)[::-1]
        owners=[x for x in sections if x[1]==1 and x[3]<=address and address+len(wanted)<=x[3]+x[5]]
        assert len(owners)==1
        x=owners[0];offset=x[4]+address-x[3]
        assert elf[offset:offset+len(wanted)]==wanted
        matched+=1
    old=ROOT/'build/rvv-compute-asm-v4'
    old_build=json.loads((old/'build.json').read_text())
    old_hash=old_build['input_sha256'][str(ROOT/'benchmarks/rvv_compute_asm_v1/guest.c')]
    prior=(old/'inputs'/old_hash).read_text()
    insertion='  fn(blocks,input[h],target[h]); /* explicit body pre-execution outside all CSR ROI */\n  setup(h,c); /* full operand/tile/output reset+fence, including omitted-call builds */\n'
    current=(ROOT/'benchmarks/rvv_compute_asm_v1/guest.c').read_text()
    assert current.count(insertion)==1 and current.replace(insertion,'')==prior
    assert json.loads((old/'corpus.json').read_text())['cases']==cases
    return dict(disassembly_raw_byte_checks=matched,preexecution_then_complete_setup_reset_only_source_delta=True,schema='iris.independent_ASM_RVV_ELF_audit.v2',**{'pass':True},
        ELF_sha256=sha(build/'guest.elf'),kernels=checked,regions=1320,independent_golden_words=words,
        wrapper_timed_sequence_hex=[hex(x)for x in wrapper[first:last+1]],
        timing_overhead='JALR dispatch, kernel RET, counter reads; two scalar loop instructions per 16 operations; rowmove has one LI per operation. No overhead subtraction.',
        all_periteration_scalar_metadata_and_helper_loads_outside_ROI=True,
        sentinel_before_final_UART=True,compiled_emit_scalar_only=True,
        numeric_scope='Independent host checksum oracle; actual two-seed normal guest execution is owned by benchmark author, not rerun here.',
        source_image_or_timing_certified=False,
        input_sha256={str(p):sha(p)for p in [Path(__file__).resolve(),build/'guest.elf',build/'corpus.json',build/'disassembly.txt',ROOT/'benchmarks/rvv_compute_asm_v1/guest.c',ROOT/'benchmarks/rvv_compute_asm_v1/kernels.S']})

if __name__=='__main__':
    out=ROOT/'build/rvv-compute-asm-v5-independent-audit-v1';out.mkdir(exist_ok=False)
    result=inspect(ROOT/'build/rvv-compute-asm-v5')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'report_sha256':sha(out/'report.json')}))
