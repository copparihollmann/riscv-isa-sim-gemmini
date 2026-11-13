"""Profile qualified Saturn source-edge observations into JSON and Perfetto.

States describe the interval preceding their sample. Accepted work/completions
are separate events at the sample edge. Unqualified values never become idle,
completed work, architectural data knownness, CPU cycles or memory bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

PREFIX = ('hart', 'source_edge', 'tb', 'known_mask')
STATES = ('reset', 'VRF_scrub', 'backend_busy_source', 'RVV_integer_pipe_busy',
          'RVV_FP_pipe_busy', 'RVV_unified_pipe_busy', 'VME_busy_union')
OCCUPANCY = ('VMU_LIQ_occupancy', 'VMU_SIQ_occupancy', 'VDQ_occupancy')
COUNTERS = ('dispatch_accept', 'VME_macro_accept', 'VME_micro_issue', 'VME_INT8_MAC_accept',
    'VME_FP8_MAC_accept', 'VME_INT8_MAC_complete', 'VME_FP8_MAC_complete', 'VME_VRF_write_bits',
    'RVV_pipe_write_beats', 'RVV_iter_write_beats', 'RVV_sequencer_issue_beats',
    'VMU_load_request_accept', 'VMU_store_request_accept', 'VMU_load_response', 'VMU_store_ack',
    'shared_FPU_request_accept', 'shared_FPU_response')
FIELDS = set(STATES + OCCUPANCY + COUNTERS)


@dataclass(frozen=True)
class Region:
    name: str
    hart: int
    start: int | None = None
    end: int | None = None
    source: str = 'entire captured source edge set'

    def point(self, tb):
        return self.start is None or self.start <= tb < self.end

    def interval(self, start, end):
        return (start, end) if self.start is None else (max(start, self.start), min(end, self.end))


class Timeline:
    def __init__(self, hz):
        self.hz, self.events, self.open, self.counters = hz, [], {}, {}

    def interval(self, hart, region, name, start, end, unknown=False):
        if end <= start:
            return
        key = hart, region, name, unknown
        old = self.open.get(key)
        if old and old[1] == start:
            self.open[key] = old[0], end
        else:
            if old:
                self._emit(key, old)
            self.open[key] = start, end

    def _emit(self, key, interval):
        hart, region, name, unknown = key; start, end = interval
        self.events.append({'ph': 'X', 'pid': hart, 'tid': name, 'name': name + (' unknown' if unknown else ''),
            'cat': 'qualification' if unknown else 'source activity', 'ts': start * 1e6 / self.hz,
            'dur': (end-start) * 1e6 / self.hz, 'args': {'region': region, 'known': not unknown,
            'state_interval': 'preceding source edge interval', 'start_tb': start, 'end_tb': end}})

    def instant(self, hart, region, name, tb, count):
        self.events.append({'ph': 'i', 's': 't', 'pid': hart, 'tid': name, 'name': name,
            'cat': 'source commit', 'ts': tb * 1e6 / self.hz,
            'args': {'region': region, 'count': count, 'tb': tb}})

    def occupancy(self, hart, region, name, tb, value):
        key = hart, region, name
        if self.counters.get(key) != value:
            self.events.append({'ph': 'C', 'pid': hart, 'tid': name, 'name': name,
                'cat': 'source occupancy', 'ts': tb * 1e6 / self.hz,
                'args': {'value': value, 'known': 1}})
            self.counters[key] = value

    def finish(self):
        for key, interval in self.open.items():
            self._emit(key, interval)
        return sorted(self.events, key=lambda e: (e['ts'], e['pid'], str(e['tid']), e['ph']))


def _bucket():
    return {'states': {name: {'known_intervals': 0, 'unknown_intervals': 0, 'active_intervals': 0,
        'known_tb_ticks': 0, 'unknown_tb_ticks': 0, 'active_tb_ticks': 0} for name in STATES},
        'counts': {name: {'known_edges': 0, 'unknown_edges': 0, 'sum': 0} for name in COUNTERS},
        'occupancy': {name: {'known_intervals': 0, 'unknown_intervals': 0, 'maximum': None,
                            'sum_per_interval': 0} for name in OCCUPANCY}}


def profile(records, schema, contract, tb_clock_hz, clock_source, regions=()):
    if (not isinstance(tb_clock_hz, (int, float)) or isinstance(tb_clock_hz, bool)
            or not math.isfinite(tb_clock_hz) or tb_clock_hz <= 0 or not clock_source):
        raise ValueError('Explicit target TestDriver clock frequency and provenance required')
    columns = schema.get('record_layout', [])
    if (schema.get('schema') != 'iris.saturn_qualified_activity_projection.v1'
            or tuple(columns[:4]) != PREFIX or len(columns) != 31
            or set(columns[4:]) != FIELDS or len(set(columns)) != len(columns)):
        raise ValueError('Unsupported qualified source projection layout')
    if contract.get('schema') != 'iris.saturn_activity_semantic_contract.v1':
        raise ValueError('Source semantic contract required')
    profiles = contract['profiles']
    if (profiles['compute']['configured_harts'] != [0,1] or profiles['rocket']['configured_harts'] != [2]
            or profiles['compute']['metrics']['VME']['peak_eligible_MAC_per_source_edge'] != 256
            or profiles['rocket']['metrics']['VME'] is not None):
        raise ValueError('Unexpected heterogeneous unit/peak contract')
    index = {name: i for i, name in enumerate(columns[4:])}
    masks = {name: 1 << i for name, i in index.items()}
    requested = [Region('capture', hart) for hart in range(3)]
    names = set()
    for item in regions:
        if (type(item.get('hart')) is not int or item['hart'] not in range(3)
                or not isinstance(item.get('id'), str) or not item['id'] or item['id'] == 'capture'
                or type(item.get('start_tb')) is not int or type(item.get('end_tb')) is not int
                or not 0 <= item['start_tb'] < item['end_tb'] or not isinstance(item.get('source'),str) or not item['source']
                or (item['hart'], item['id']) in names):
            raise ValueError('Unique explicit source-coordinate region with provenance required')
        names.add((item['hart'],item['id']))
        requested.append(Region(item['id'], item['hart'], item['start_tb'], item['end_tb'], item['source']))
    buckets = {(r.hart,r.name): _bucket() for r in requested}
    timeline = Timeline(tb_clock_hz)
    counts, first, last, seen_reset = [0]*3, [None]*3, [None]*3, [False]*3
    previous_tb = None
    for row in records:
        if (not isinstance(row, list) or len(row) != len(columns)
                or any(type(v) is not int or not 0 <= v < 2**64 for v in row)):
            raise ValueError('Invalid unsigned qualified projection row')
        hart, edge, tb, known = row[:4]; values = row[4:]
        if (hart not in range(3) or edge != counts[hart] or known >= 1 << len(index)
                or not known & masks['reset']):
            raise ValueError('Invalid hart/source edge or knownness mask')
        if ((previous_tb is not None and tb < previous_tb)
                or (last[hart] is not None and tb <= last[hart])):
            raise ValueError('Source observation clock order regressed')
        for name, i in index.items():
            if not known & masks[name] and values[i] != 0:
                raise ValueError('Unknown source value must remain a placeholder')
            if name in STATES and values[i] not in (0,1):
                raise ValueError('Source state must be boolean')
            if name.startswith('VME_') and ('MAC_' in name) and values[i] > 256:
                raise ValueError('Physical VME cell count exceeds source capacity')
            if hart == 2 and name.startswith('VME_') and values[i] != 0:
                raise ValueError('VME activity on a hart without the unit')
        reset = values[index['reset']]
        if reset:
            seen_reset[hart] = True
            if known != masks['reset']:
                raise ValueError('Semantic work cannot be qualified during reset')
        elif not seen_reset[hart]:
            raise ValueError('Observed reset history required before source work')
        previous = last[hart]
        if first[hart] is None:
            first[hart] = tb
        for region in (r for r in requested if r.hart == hart):
            bucket = buckets[hart,region.name]
            if region.point(tb) and not reset:
                for name in COUNTERS:
                    metric = bucket['counts'][name]
                    if known & masks[name]:
                        value = values[index[name]];metric['known_edges'] += 1;metric['sum'] += value
                        if value:
                            timeline.instant(hart,region.name,name,tb,value)
                    else:
                        metric['unknown_edges'] += 1
            if previous is None:
                continue  # No invented interval before the first observation.
            start,end = region.interval(previous,tb)
            if end <= start:
                continue
            for name in STATES:
                if reset and name != 'reset':
                    continue
                metric = bucket['states'][name]
                if known & masks[name]:
                    metric['known_intervals'] += 1;metric['known_tb_ticks'] += end-start
                    if values[index[name]]:
                        metric['active_intervals'] += 1;metric['active_tb_ticks'] += end-start
                        timeline.interval(hart,region.name,name,start,end)
                else:
                    metric['unknown_intervals'] += 1;metric['unknown_tb_ticks'] += end-start
                    timeline.interval(hart,region.name,name,start,end,True)
            if not reset:
                for name in OCCUPANCY:
                    metric = bucket['occupancy'][name]
                    if known & masks[name]:
                        value = values[index[name]];metric['known_intervals'] += 1
                        metric['maximum'] = max(value, metric['maximum'] or 0)
                        metric['sum_per_interval'] += value
                        timeline.occupancy(hart,region.name,name,start,value)
                    else:
                        metric['unknown_intervals'] += 1
        last[hart] = previous_tb = tb;counts[hart] += 1
    if not all(counts):
        raise ValueError('Missing configured hart observations')
    results = []
    for region in requested:
        if region.start is not None and (region.start < first[region.hart] or region.end > last[region.hart]):
            raise ValueError('Region extends beyond captured source coordinates')
        bucket = buckets[region.hart,region.name]
        for metric in bucket['states'].values():
            metric['active_fraction_of_known_intervals'] = metric['active_intervals']/metric['known_intervals'] if metric['known_intervals'] else None
            metric['active_fraction_of_known_tb_ticks'] = metric['active_tb_ticks']/metric['known_tb_ticks'] if metric['known_tb_ticks'] else None
        for metric in bucket['occupancy'].values():
            metric['mean_per_known_interval'] = metric['sum_per_interval']/metric['known_intervals'] if metric['known_intervals'] else None
        for metric in bucket['counts'].values():
            metric['per_known_source_edge'] = metric['sum']/metric['known_edges'] if metric['known_edges'] else None
        config = profiles['compute' if region.hart < 2 else 'rocket']
        results.append({'hart': region.hart, 'region': region.name,
            'bounds': {'start_tb': first[region.hart] if region.start is None else region.start,
                       'end_tb': last[region.hart] if region.end is None else region.end,
                       'commit_endpoint': 'all captured commits included' if region.start is None else '[start_tb,end_tb)',
                       'source': region.source},
            'configured_VLEN_bits': config['VLEN_bits'], 'configured_DLEN_bits': config['DLEN_bits'],
            'VME_present': region.hart < 2, 'VME_peak_eligible_MACs_per_source_edge': 256 if region.hart < 2 else None,
            'VME_peak_scope': config['metrics']['VME']['peak_scope'] if region.hart < 2 else 'Unit absent',
            'RVV_peak_elements_per_edge': None, 'memory_bytes': None, 'roofline': None,
            'unsupported_metrics': {'RVV_peak': config['metrics']['RVV_peak_reason'],
                'roofline': 'No qualified external TL byte ledger supplied; internal VMU requests/VRF bits are distinct.',
                'CPU_utilization': 'This stream observes Saturn, not the scalar CPU pipeline.',
                'function_attribution': 'No qualified command-to-physical-work PC ownership supplied.'},
            **bucket})
    summary = {'schema': 'iris.saturn_source_activity_profile.v1', 'tb_clock_hz': tb_clock_hz,
        'clock_source': clock_source, 'frames_per_hart': counts, 'regions': results,
        'interval_policy': schema['state_interval'],
        'state_fraction_policy': 'Known postreset intervals; scrub separately reported, retained in denominator. First sample has no preceding interval.',
        'work_policy': 'Qualified commit events only, accepted and completed separate; cropped regions need not balance.',
        'busy_policy': 'Overlapping source flags/unions are separate tracks, never summed into utilization.',
        'mcycle_projection_inferred': False, 'numeric_knownness_inferred': False,
        'FPGA_or_full_timing_certified': False, 'calibration_usable': False}
    trace = {'traceEvents': timeline.finish(), 'displayTimeUnit': 'ns',
         'metadata': {'source': 'qualified Saturn source-edge observations', 'tb_clock_hz': tb_clock_hz,
                      'clock_source': clock_source, 'FPGA_or_full_timing_certified': False}}
    return summary, trace
