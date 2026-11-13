"""Typed compute corpus wrapper around the unchanged independent row oracle."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.campaign_buffered.validate_priority import check_rows as _check_rows, validate as _validate


def admitted(corpus):
    if (corpus.get('schema') != 'iris.compute_fitting_corpus.v1'
            or corpus.get('split_id') != 'iris-compute-fitting-v1'
            or corpus.get('trials') != 3 or corpus.get('physical_harts') != 3):
        raise ValueError('Exact new compute fitting corpus required')
    for case in corpus['cases']:
        if case['suite'] != 'distribution' or case['kind'] in ('memory', 'vme_memory'):
            raise ValueError('Bulk memory case cannot read excluded noinit storage')
        if not case['case_id'].startswith('compute.v1.') or not case['parent_case_id'].startswith('compute.v1.'):
            raise ValueError('New exact-reference compute identities required')
    return dict(corpus, schema='iris.buffered_fitting_corpus.v2', split_id='iris-buffered-priority-fit-campaign-v2')


def check_rows(rows, corpus): return _check_rows(rows, admitted(corpus))
def validate(text, corpus): return _validate(text, admitted(corpus))
