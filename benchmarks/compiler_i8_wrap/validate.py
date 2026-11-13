"""Independent whole-output integer oracle checks for all three runtime harts."""
import json

from cases import corpus


def validate(text,supplied,variant):
    if supplied!=corpus() or variant not in ('vme','twin','combined'):
        raise ValueError('Exact independent wrapping corpus and explicit variant required')
    rows,done=[],[]
    for line in text.splitlines():
        if line.startswith('IRIS_FATAL '):raise ValueError('Fatal guest trap')
        if line.startswith('IRIS_REGION '):rows.append(json.loads(line.split(' ',1)[1]))
        elif line.startswith('IRIS_BATCH_DONE '):done.append(json.loads(line.split(' ',1)[1]))
    expected_rows=126 if variant=='combined'else 21
    if (len(rows)!=expected_rows or done!=[{'failed':0,'regions':expected_rows}]
            or any(type(value)is not int for record in done for value in record.values())):
        raise ValueError('Complete all-three-hart wrapping corpus required')
    order=([(case,h,v,t)for t in range(3)for v in ('vme','twin')for case in supplied['cases']for h in range(3)]
           if variant=='combined'else[(case,h,variant,0)for case in supplied['cases']for h in range(3)])
    for row,(case,hart,actual_variant,trial) in zip(rows,order):
        if any(type(row.get(name))is not int or not 0<=row[name]<2**64 for name in (
            'hart','start_cycle','end_cycle','instret_delta','checksum','expected_checksum','failed_words')):
            raise ValueError('Exact unsigned region fields required')
        parent=case['case_id']+'.variant-'+actual_variant if variant=='combined'else case['case_id']
        identity=parent+'.trial'+str(trial)if variant=='combined'else parent
        if (row.get('case_id')!=identity or row.get('parent_case_id')!=parent or row['hart']!=hart
                or row.get('variant')!=actual_variant or type(row.get('trial_id'))is not int or row['trial_id']!=trial
                or row.get('suite')!='compiler_i8_wrap' or row.get('region')!='kernel'):
            raise ValueError('Region identity/hart/variant mismatch')
        expected=case['expected_checksums'][str(hart)]
        if row['checksum']!=expected or row['expected_checksum']!=expected or row['failed_words']!=0 or row.get('pass')is not True:
            raise ValueError('Independent modulo32/producer golden mismatch')
        if not row['start_cycle']<row['end_cycle'] or row['instret_delta']==0:
            raise ValueError('Invalid observed counter region')
    return {'regions':expected_rows,'per_hart':[expected_rows//3]*3,'all_cases':7,'variant':variant,
            'trials':3 if variant=='combined'else 1,
            'unique_case_output_values_per_compute_hart':sum(c['m']*c['n']for c in supplied['cases']),
            'matrix_output_values_per_compute_hart':sum(c['m']*c['n']for c in supplied['cases'])*(6 if variant=='combined'else 1),
            'hart2_RVV_values':168 if variant=='combined'else 28,'semantics':'I8 products and bias modulo2^32',
            'counter_policy':'Raw functional-mode progress; not target timing or calibration.',
            'calibration_usable':False,'full_functional_certified':False}
