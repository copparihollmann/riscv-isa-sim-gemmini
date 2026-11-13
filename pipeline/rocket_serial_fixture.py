"""Explicit, uncalibrated saved-reference Serial calendar and functional actors."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SYSTEM='eb4cdd5a94121c510ba34a011b727757d4ca61fe17973cb835c1feb57f68266a'
LP='1d1d497a614cda9e0076368589246bceaeb2cb5dcc20c82d951c6f2566257f85'
def text(elf:Path,seed=1):
    base=(ROOT/'pipeline/rocket-source-synthetic.fixture').read_text()
    lines=[]
    for line in base.splitlines():
        if line.startswith('base_hz '):line='base_hz 1000000000'
        elif line.startswith('rtc_divider '):line='rtc_divider 2000'
        elif line.startswith('max_cycles '):line='max_cycles 2000000'
        elif line.startswith('trap_cycles '):line='trap_cycles 8'
        elif line.startswith('hart '):line=' '.join([*line.split()[:2],'2','source'])
        elif line.startswith('rule '):
            fields=line.split();fields[5]='6';fields[6]='2';line=' '.join(fields)
        elif line.startswith('shuttle_frontend '):line=f'shuttle_frontend saved-rtl-M-mode {seed} 16'
        lines.append(line)
    lines += [f'rocket_serial source-path-explicit-functional-AXI-fixture 2 1 10 100 30 30 16 16 {elf.resolve()} {SYSTEM} {LP} virtual_phase_units', 'serial_cbus_fixture 3 1 explicit-synthetic-CBUS-ROM-CLINT-service', 'rocket_scalar_memory source-cache-M-mode']
    return '\n'.join(lines)+'\n'
