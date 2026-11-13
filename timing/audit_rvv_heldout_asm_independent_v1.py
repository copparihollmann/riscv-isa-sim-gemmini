"""Independent protected ASM source/ELF/golden audit; never opens hardware labels."""
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
    for n in (2,8,32,128):
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
    assert all(c['internal_split']=='reserved_holdout' and c['validation_role']=='protected_validation_only' for c in cases)
    assert corpus['fitting_only'] is False and corpus['global_heldout'] is True and corpus['train_regions']==0 and corpus['reserved_regions']==1320
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
        if kind!=7: assert n in (32,128) and n%16==0
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
    source=ROOT/'benchmarks/rvv_compute_heldout_asm_v1'
    split=json.loads((source/'split.json').read_text())
    assert split['protected_validation_only'] is True and split['fitting_allowed'] is False
    assert split['timing_labels_root_only'] is True and split['train_case_ids']==[]
    assert split['protected_case_ids']==[c['case_id'] for c in cases]
    assert split['protected_semantic_parent_ids']==sorted({c['semantic_parent_case_id'] for c in cases})
    assert split['train_regions']==0 and split['reserved_regions']==1320
    assert corpus['frozen_split_sha256']==sha(source/'split.json')
    # Parse the actual linked 48-byte table and pointer strings; no packet validator imported.
    table=raw('experiments');assert len(table)==48*1320
    def memory(address,length):
        owners=[s for s in sections if s[1]==1 and s[3]<=address and address+length<=s[3]+s[5]]
        assert len(owners)==1
        s=owners[0];off=s[4]+address-s[3];return elf[off:off+length]
    def cstring(address):
        result=bytearray()
        while True:
            x=memory(address+len(result),1)
            if x==b'\0':return result.decode('ascii')
            assert len(result)<256;result.extend(x)
    fields=('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')
    parent=json.loads((ROOT/'build/rvv-compute-asm-v5/corpus.json').read_text())['cases']
    assert len(parent)==1320
    groups={}
    for i,c in enumerate(cases):
        ident,*geometry=struct.unpack_from('<Q10I',table,i*48)
        assert cstring(ident)==c['case_id'] and geometry==[c[k] for k in fields]
        prior=parent[i]
        assert c['source_case_id']==prior['case_id']
        assert c['n']==({1:2,4:8,16:32,64:128} if c['kind_id']==7 else {16:32,64:128})[prior['n']]
        assert all(c[k]==prior[k] for k in fields if k!='n')
        groups.setdefault(c['parent_case_id'],[]).append(c['trial_id'])
    assert len(groups)==440 and all(x==[0,1,2] for x in groups.values())
    current=(source/'guest.c').read_text()
    prior=(ROOT/'benchmarks/rvv_compute_asm_v1/guest.c').read_text()
    row_mapping={'1':'2','4':'8','16':'32','64':'128'}
    expected=re.sub(r'asm_row(64|16|4|1)\b',lambda m:'asm_row'+row_mapping[m.group(1)],prior)
    expected=expected.replace('case 1:return asm_row2','case 2:return asm_row2').replace('case 4:return asm_row8','case 8:return asm_row8').replace('case 16:return asm_row32','case 32:return asm_row32').replace('case 64:return asm_row128','case 128:return asm_row128')
    expected=expected.replace('rvv_identify','rvv_compute_heldout_asm_v1')
    assert expected==current,'Only row dispatch/suite source changes expected'
    # Each actual executable instruction printed by objdump was byte-crosschecked above.
    # The sole emitter call follows final sentinel SD and FENCE; no earlier call path exists.
    main=instructions('benchmark_main')
    direct_calls=[]
    for address,word in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+',dis,re.M):
        address=int(address,16);word=int(word,16)
        if symbols['benchmark_main'][0]<=address<sum(symbols['benchmark_main'][:2]) and word&0x7f==0x6f:
            imm=((word>>31)<<20)|(((word>>12)&255)<<12)|(((word>>20)&1)<<11)|(((word>>21)&1023)<<1)
            if imm&(1<<20):imm-=1<<21
            if (word>>7)&31==1:direct_calls.append((address,address+imm))
    emitter_calls=[a for a,d in direct_calls if d==symbols['emit'][0]]
    assert len(emitter_calls)==1
    assert all(d not in (symbols['putstr'][0],symbols['putuint'][0]) for a,d in direct_calls)
    assert current.index('if(h==0){__atomic_store_n(&completion.value,1')<current.index('rvv_measurements_done=0')<current.index('memory_fence();emit();')
    return dict(disassembly_raw_byte_checks=matched,protected_geometry_only_source_delta=True,schema='iris.independent_protected_ASM_RVV_ELF_audit.v1',**{'pass':True},
        ELF_sha256=sha(build/'guest.elf'),kernels=checked,regions=1320,independent_golden_words=words,
        wrapper_timed_sequence_hex=[hex(x)for x in wrapper[first:last+1]],
        timing_overhead='JALR dispatch, kernel RET, counter reads; two scalar loop instructions per 16 operations; rowmove has one LI per operation. No overhead subtraction.',
        all_periteration_scalar_metadata_and_helper_loads_outside_ROI=True,
        sentinel_before_final_UART=True,compiled_emit_scalar_only=True,no_interphase_UART=True,compiled_case_records=1320,three_trial_groups=440,train_regions=0,protected_regions=1320,hardware_labels_opened=False,
        numeric_scope='Independent host checksum oracle; actual two-seed normal guest execution is owned by benchmark author, not rerun here.',
        source_image_or_timing_certified=False,
        input_sha256={str(p):sha(p)for p in [Path(__file__).resolve(),build/'guest.elf',build/'corpus.json',build/'disassembly.txt',source/'guest.c',source/'kernels.S',source/'split.json',build/'ready.json',build/'qualification.json']})

if __name__=='__main__':
    out=ROOT/'build/rvv-compute-heldout-asm-independent-audit-v2';out.mkdir(exist_ok=False)
    result=inspect(ROOT/'build/rvv-compute-heldout-asm-v1')
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'report_sha256':sha(out/'report.json')}))
