"""Generate and independently evaluate a fixed RV64I pure-ALU dependency corpus."""
import random

MASK = (1<<64)-1
REGISTERS = [5,6,7,10,11,12,13,14,15,16,17,28,29,30]
NAMES = ['LUI','AUIPC','ADDI','SLTI','SLTIU','XORI','ORI','ANDI','SLLI','SRLI','SRAI',
         'ADD','SUB','SLL','SLT','SLTU','XOR','SRL','SRA','OR','AND',
         'ADDIW','SLLIW','SRLIW','SRAIW','ADDW','SUBW','SLLW','SRLW','SRAW']


def signed(value, bits):
    value &= (1<<bits)-1
    return value-(1<<bits) if value&(1<<(bits-1)) else value


def corpus(count=2048, seed=729536):
    rng = random.Random(seed)
    initial = {r:rng.getrandbits(64) for r in REGISTERS}
    program = []
    for index in range(count):
        name = NAMES[index] if index<len(NAMES) else rng.choice(NAMES)
        rd, r1, r2 = [rng.choice([0]+REGISTERS) for _ in range(3)]
        imm = rng.randint(-2048,2047)
        word = None
        if name in ('LUI','AUIPC'):
            imm = rng.getrandbits(20)
            word = (imm<<12)|(rd<<7)|(0x37 if name=='LUI' else 0x17)
        elif name in ('ADDI','SLTI','SLTIU','XORI','ORI','ANDI','ADDIW'):
            funct3 = {'ADDI':0,'SLTI':2,'SLTIU':3,'XORI':4,'ORI':6,'ANDI':7,'ADDIW':0}[name]
            word = ((imm&4095)<<20)|(r1<<15)|(funct3<<12)|(rd<<7)|(0x1b if name=='ADDIW' else 0x13)
        elif name in ('SLLI','SRLI','SRAI','SLLIW','SRLIW','SRAIW'):
            imm = rng.randrange(32 if name.endswith('W') else 64)
            funct3 = 1 if name.startswith('SLL') else 5
            immediate = imm|(0x400 if name.startswith('SRA') else 0)
            word = (immediate<<20)|(r1<<15)|(funct3<<12)|(rd<<7)|(0x1b if name.endswith('W') else 0x13)
        else:
            funct3 = {'ADD':0,'SUB':0,'SLL':1,'SLT':2,'SLTU':3,'XOR':4,'SRL':5,'SRA':5,'OR':6,'AND':7,
                      'ADDW':0,'SUBW':0,'SLLW':1,'SRLW':5,'SRAW':5}[name]
            word = ((0x20 if name in ('SUB','SRA','SUBW','SRAW') else 0)<<25)|(r2<<20)|(r1<<15)|(funct3<<12)|(rd<<7)|(0x3b if name.endswith('W') else 0x33)
        program.append(dict(name=name, rd=rd, rs1=r1, rs2=r2, immediate=imm, word=word))
    return dict(seed=seed, initial_registers=initial, instructions=program)


def assembly(program):
    lines = ['.option push','.option norvc','.text','.global alu_corpus','alu_corpus:','  mv x31,a0']
    lines += [f'  li x{reg},0x{value:016x}' for reg,value in program['initial_registers'].items()]
    lines += ['.global alu_corpus_begin','alu_corpus_begin:']
    lines += [f"  .word 0x{op['word']:08x} # {op['name']}" for op in program['instructions']]
    lines += ['.global alu_corpus_end','alu_corpus_end:']
    lines += [f'  sd x{reg},{index*8}(x31)' for index,reg in enumerate(REGISTERS)]
    lines += ['  ret','.option pop']
    return '\n'.join(lines)+'\n'


def evaluate(program, first_pc):
    registers = {int(k):v for k,v in program['initial_registers'].items()}
    registers[0] = 0
    for index,op in enumerate(program['instructions']):
        name, rd, imm = op['name'], op['rd'], op['immediate']
        a,b = registers[op['rs1']],registers[op['rs2']]
        if name=='LUI':value=signed(imm<<12,32)
        elif name=='AUIPC':value=first_pc+index*4+signed(imm<<12,32)
        elif name in ('ADDI','ADDIW'):value=a+imm
        elif name=='SLTI':value=int(signed(a,64)<imm)
        elif name=='SLTIU':value=int(a<(imm&MASK))
        elif name=='XORI':value=a^(imm&MASK)
        elif name=='ORI':value=a|(imm&MASK)
        elif name=='ANDI':value=a&(imm&MASK)
        elif name in ('SLLI','SLLIW'):value=a<<imm
        elif name in ('SRLI','SRLIW'):value=(a&((1<<(32 if name.endswith('W') else 64))-1))>>imm
        elif name in ('SRAI','SRAIW'):value=signed(a,32 if name.endswith('W') else 64)>>imm
        elif name in ('ADD','ADDW'):value=a+b
        elif name in ('SUB','SUBW'):value=a-b
        elif name in ('SLL','SLLW'):value=a<<(b&(31 if name.endswith('W') else 63))
        elif name=='SLT':value=int(signed(a,64)<signed(b,64))
        elif name=='SLTU':value=int(a<b)
        elif name=='XOR':value=a^b
        elif name in ('SRL','SRLW'):value=(a&((1<<(32 if name.endswith('W') else 64))-1))>>(b&(31 if name.endswith('W') else 63))
        elif name in ('SRA','SRAW'):value=signed(a,32 if name.endswith('W') else 64)>>(b&(31 if name.endswith('W') else 63))
        elif name=='OR':value=a|b
        elif name=='AND':value=a&b
        else:raise ValueError('missing independent ALU oracle: '+name)
        if name.endswith('W'):
            value=signed(value,32)
        if rd:
            registers[rd]=value&MASK
    return [registers[r] for r in REGISTERS]
