"""Admission boundaries in the source-bound workload plan, not model execution."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def test_held_out_and_unknown_model_inputs_never_enter_fitting():
    plan=json.loads((ROOT/'workloads/operator-coverage.json').read_text())
    rows={r['model_id']:r for r in plan['models']}
    for row in rows.values():
        if row['validation_only']:assert row['operator_cases']==[]
        if row['selection']!='primary-user-selected':assert not any(c['fit_eligible'] for c in row['operator_cases'])
        assert not row['model_execution_qualified']
    llama=rows['meta-llama/Llama-2-7b-hf']
    assert 'config.json' not in llama['files']
    assert llama['provisional_reference_defaults']['vocab_size'] is None
    assert not any(c['fit_eligible'] for c in llama['operator_cases'])
    assert plan['streaming_contract']['kv_bytes'] is None
    assert plan['streaming_contract']['serial_latency_cycles'] is None
    assert not plan['streaming_contract']['fits_qualified']


def test_independent_config_agreement_and_nonexistent_projection_refusal():
    rows={r['model_id']:r for r in json.loads((ROOT/'workloads/operator-coverage.json').read_text())['models']}
    for name in ['openai/gpt-oss-20b','openai/gpt-oss-120b']:
        assert all(rows[name]['independent_original_config_crosscheck'].values())
        q=next(c for c in rows[name]['operator_cases'] if c['role']=='attention.q')
        assert q['shape_mnk'][1:]==[4096,2880]  # head count*head width differs from hidden width.
    a4b=rows['google/gemma-4-26B-A4B-it']
    assert 'full_attention.v' not in {c['role'] for c in a4b['operator_cases']}
    for name in ['openai/gpt-oss-20b','google/gemma-4-E4B-it']:
        assert rows[name]['selected_matrix_storage_lower_bound']['int8_bytes']>4*(1<<30)
        assert rows[name]['required_nonmatmul_coverage']
        assert not any(c['compiler_qualified'] for c in rows[name]['required_nonmatmul_coverage'])
