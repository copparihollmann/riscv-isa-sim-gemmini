"""Exact source/compiled case/phase admission for the buffered RVV packet."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'benchmarks/rvv_identify_v1'))
import qualify as proof
import validate as val
sys.path.pop(0)
ELF='52b02a51d1dd7580d6a560baecf6fd979ea39cde6316610fb83b95e532e7b0ec'
ROLE='rvv_identify_single_hart_train_reserved_v1'
inspect=proof.inspect;flatten=proof.flatten;inspect_clint_window=proof.clint_proof
def validator():return val
