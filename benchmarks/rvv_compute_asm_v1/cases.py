import copy,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'build/rvv-compute1320-v2/corpus.json'
def generate():return copy.deepcopy(json.loads(PARENT.read_text())['cases'])
def golden(c):
 from validate import checksum
 return checksum(c)
