"""Explicit source-backed deployment profiles for the actual Iris UART."""
import hashlib,json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def profile(name):
    data=json.loads((HERE/'uart-profiles.json').read_text());row=dict(data['profiles'][name])
    for path,digest in data['source_sha256'].items():
        if sha(HERE/path)!=digest:raise RuntimeError('Stale UART source evidence: '+path)
    if data['clock_hz']//row['requested_baud']-1!=row['expected_divisor'] or row['expected_divisor']+1!=row['physical_bit_edges']:
        raise RuntimeError('UART driver DIV formula disagrees with deployment profile')
    if row.get('fixed_bridge_key') is not None and row['fixed_bridge_key']!=row['expected_divisor']:
        raise RuntimeError('UART software DIV disagrees with fixed FireSim bridge decoder')
    return dict(row,name=name,clock_hz=data['clock_hz'],metadata_sha256=sha(HERE/'uart-profiles.json'),hardware_tested=False)

def inputs(name):
    data=json.loads((HERE/'uart-profiles.json').read_text());row=profile(name)
    return [Path(__file__),HERE/'uart-profiles.json',HERE/'iris_uart_profile.h',*[HERE/x for x in data['source_sha256']],*([HERE/row['overlay']] if row['overlay'] else [])]

def cmake(name):
    row=profile(name)
    return ['-DEXTRA_DTC_OVERLAY_FILE='+str(HERE/row['overlay'])] if row['overlay'] else []

def check_report(lines,name):
    row=profile(name);reports=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_UART_PROFILE ')]
    expected={'requested_baud':row['requested_baud'],'clock_hz':row['clock_hz'],'divisor':row['expected_divisor']}
    if reports!=[expected]:raise RuntimeError('Guest UART DIV/clock/readback differs from selected deployment profile: '+repr(reports))
    return reports[0]
