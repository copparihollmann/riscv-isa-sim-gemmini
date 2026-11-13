"""Exact public source metadata subset; no timing labels."""
import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'build/rvv-identify-compact-v1/corpus.json'
def generate():
 return [copy.deepcopy(c) for c in json.loads(PARENT.read_text())['cases'] if c['hart']==2]
def golden(c):
 from validate import checksum
 return checksum(c)
