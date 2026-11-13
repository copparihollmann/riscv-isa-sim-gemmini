"""Independent encoding and integer oracle for mixed16/32-bit ALU streams."""
import random
from pipeline.alu_corpus import MASK, signed

REGISTERS=[5,6,7,8,9,10,11,12,13,14,15,16,17,28,29]
NAMES=['C.NOP','C.ADDI','C.ADDIW','C.LI','C.LUI','C.ADDI16SP','C.ADDI4SPN',
       'C.SRLI','C.SRAI','C.ANDI','C.SUB','C.XOR','C.OR','C.AND','C.SUBW','C.ADDW','C.SLLI','C.MV','C.ADD']


def corpus(count=2048,seed=536729):
    rng=random.Random(seed);program=[]
    for index in range(count):
        name=NAMES[index] if index<len(NAMES) else rng.choice(NAMES)
        rd=rng.choice(REGISTERS);r2=rng.choice(REGISTERS);immediate=rng.randrange(-32,32)
        common=((immediate&31)<<2)|((immediate&32)<<7)|(rd<<7)|1
        length=2
        if name=='C.NOP':word=1;rd=0;immediate=0
        elif name in ('C.ADDI','C.ADDIW','C.LI','C.LUI'):
            if name=='C.LUI' and immediate==0:immediate=1
            common=((immediate&31)<<2)|((immediate&32)<<7)|(rd<<7)|1
            word=common|({'C.ADDI':0,'C.ADDIW':1,'C.LI':2,'C.LUI':3}[name]<<13)
        elif name=='C.ADDI16SP':
            rd=2;immediate=rng.choice([v for v in range(-512,512,16) if v])
            b=immediate&1023
            word=0x6101|((b>>9&1)<<12)|((b>>4&1)<<6)|((b>>6&1)<<5)|((b>>7&3)<<3)|((b>>5&1)<<2)
        elif name=='C.ADDI4SPN':
            rd=rng.randrange(8,16);immediate=rng.randrange(1,256)*4
            word=((rd-8)<<2)|((immediate>>6&15)<<7)|((immediate>>4&3)<<11)|((immediate>>3&1)<<5)|((immediate>>2&1)<<6)
        elif name in ('C.SRLI','C.SRAI','C.ANDI'):
            rd=rng.randrange(8,16)
            if name!='C.ANDI':immediate=rng.randrange(64)
            word=0x8001|((rd-8)<<7)|((immediate&31)<<2)|((immediate&32)<<7)|({'C.SRLI':0,'C.SRAI':1,'C.ANDI':2}[name]<<10)
        elif name in ('C.SUB','C.XOR','C.OR','C.AND','C.SUBW','C.ADDW'):
            rd=rng.randrange(8,16);r2=rng.randrange(8,16)
            op={'C.SUB':0,'C.XOR':1,'C.OR':2,'C.AND':3,'C.SUBW':0,'C.ADDW':1}[name]
            word=0x8c01|((rd-8)<<7)|((r2-8)<<2)|(op<<5)|(0x1000 if name.endswith('W') else 0)
        elif name=='C.SLLI':
            immediate=rng.randrange(64);word=2|(rd<<7)|((immediate&31)<<2)|((immediate&32)<<7)
        elif name in ('C.MV','C.ADD'):
            word=0x8002|(rd<<7)|(r2<<2)|(0x1000 if name=='C.ADD' else 0)
        else:raise ValueError(name)
        program.append(dict(name=name,rd=rd,rs2=r2,immediate=immediate,word=word,length=length))
        if index%7==6:
            rd=rng.choice(REGISTERS);r2=rng.choice(REGISTERS)
            program.append(dict(name='ADD',rd=rd,rs2=r2,immediate=0,word=(r2<<20)|(rd<<15)|(rd<<7)|0x33,length=4))
    return dict(seed=seed,initial_registers={r:rng.getrandbits(64) for r in REGISTERS},instructions=program)


def assembly(program):
    lines=['.option push','.option norvc','.text','.global rvc_corpus','rvc_corpus:',
           '  addi sp,sp,-16','  sd s0,0(sp)','  sd s1,8(sp)','  mv x30,sp','  mv x31,a0','  sd sp,120(x31)']
    lines += [f'  li x{reg},0x{value:016x}' for reg,value in program['initial_registers'].items()]
    lines += ['.global rvc_corpus_begin','rvc_corpus_begin:']
    lines += [f"  {'.hword' if op['length']==2 else '.word'} 0x{op['word']:0{op['length']*2}x} # {op['name']}" for op in program['instructions']]
    lines += ['.global rvc_corpus_end','rvc_corpus_end:','  sd sp,128(x31)','  mv sp,x30']
    lines += [f'  sd x{reg},{index*8}(x31)' for index,reg in enumerate(REGISTERS)]
    lines += ['  ld s0,0(sp)','  ld s1,8(sp)','  addi sp,sp,16','  ret','.option pop']
    return '\n'.join(lines)+'\n'


def evaluate(program,initial_sp):
    regs={int(r):v for r,v in program['initial_registers'].items()};regs[2]=initial_sp;regs[0]=0
    for op in program['instructions']:
        n,rd,imm=op['name'],op['rd'],op['immediate'];a,b=regs[rd],regs[op['rs2']]
        if n=='C.NOP':continue
        if n in ('C.ADDI','C.ADDIW','C.ADDI16SP'):value=a+imm
        elif n=='C.LI':value=imm
        elif n=='C.LUI':value=imm<<12
        elif n=='C.ADDI4SPN':value=regs[2]+imm
        elif n=='C.SRLI':value=a>>imm
        elif n=='C.SRAI':value=signed(a,64)>>imm
        elif n=='C.ANDI':value=a&(imm&MASK)
        elif n in ('C.SUB','C.SUBW'):value=a-b
        elif n=='C.XOR':value=a^b
        elif n=='C.OR':value=a|b
        elif n=='C.AND':value=a&b
        elif n in ('C.ADD','C.ADDW','ADD'):value=a+b
        elif n=='C.SLLI':value=a<<imm
        elif n=='C.MV':value=b
        else:raise ValueError(n)
        if n in ('C.ADDIW','C.SUBW','C.ADDW'):value=signed(value,32)
        if rd:regs[rd]=value&MASK
    return [regs[r] for r in REGISTERS]+[initial_sp,regs[2]]
