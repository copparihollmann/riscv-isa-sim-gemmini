"""Private manager instrumentation; observes calls without invoking hardware.

Injected only into a freshly prepared manager. Durations are host elapsed time,
including command transport. Nested measurements must not be added together.
"""
import contextvars
import datetime
import functools
import itertools
import json
import shlex
import time

PREFIX = 'IRIS_HOST_PHASE '
_parent = contextvars.ContextVar('iris_host_phase_parent', default=None)
_sequence = itertools.count()


def _emit(record):
    print(PREFIX + json.dumps(record, sort_keys=True), flush=True)


def _observe(function, phase, details=None):
    @functools.wraps(function)
    def measured(*args, **kwargs):
        identity = next(_sequence)
        start = time.monotonic_ns()
        record = {'schema': 'iris.host_setup_phase.v1', 'id': identity,
                  'parent_id': _parent.get(), 'phase': phase,
                  'host': str(getattr(getattr(args[0], 'parent_node', None), 'host', '')) if args else '',
                  'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'start_monotonic_ns': start}
        if details:
            record.update(details(args, kwargs))
        _emit(dict(record, event='begin'))
        token = _parent.set(identity)
        try:
            result = function(*args, **kwargs)
        except BaseException as error:
            _emit(dict(record, event='end', status='raised', error_type=type(error).__name__,
                       host_elapsed_ns=time.monotonic_ns() - start))
            raise
        else:
            code = getattr(result, 'return_code', None)
            _emit(dict(record, event='end', status='returned', return_code=code,
                       host_elapsed_ns=time.monotonic_ns() - start))
            return result
        finally:
            _parent.reset(token)
    return measured


def _transfer_details(args, kwargs):
    return {'local_path': str(kwargs.get('local_dir', args[0] if args else '')),
            'remote_path': str(kwargs.get('remote_dir', args[1] if len(args) > 1 else ''))}


def _program_command(command):
    if not isinstance(command, str):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    # Match the reviewed manager's exact fixed helper, not shell substrings.
    return (len(words) == 5 and words[0] == '/usr/local/bin/firesim-fpga-util.py'
            and words[1] == '--bitstream-map' and words[3] == '--fpga-db')


def install(module=None):
    if module is None:
        import runtools.run_farm_deploy_managers as module
    if getattr(module, '_iris_host_phase_observer_installed', False):
        raise RuntimeError('Setup observer already installed')
    targets = [
        (module.InstanceDeployManager, 'copy_sim_slot_infrastructure', 'copy_slot_infrastructure'),
        (module.InstanceDeployManager, 'extract_driver_tarball', 'extract_driver'),
        (module.XilinxAlveoInstanceDeployManager, 'unload_xdma', 'unload_xdma'),
        (module.XilinxAlveoInstanceDeployManager, 'flash_fpgas', 'flash_including_unpack_and_script_transfer'),
        (module.XilinxAlveoInstanceDeployManager, 'load_xdma', 'load_xdma_and_device_permissions'),
        (module.XilinxAlveoInstanceDeployManager, 'change_pcie_perms', 'change_pcie_permissions'),
    ]
    # Check the entire contract before changing any function binding.
    for owner, name, phase in targets:
        if name not in vars(owner) or not callable(getattr(owner, name)):
            raise RuntimeError('Setup observer source contract changed: ' + name)
    if not callable(module.rsync_project) or not callable(module.run):
        raise RuntimeError('Setup observer transport source contract changed')
    for owner, name, phase in targets:
        setattr(owner, name, _observe(getattr(owner, name), phase))
    module.rsync_project = _observe(module.rsync_project, 'rsync_transfer', _transfer_details)
    original_run = module.run

    @functools.wraps(original_run)
    def observed_run(*args, **kwargs):
        command = args[0] if args else kwargs.get('command')
        if _program_command(command):
            return _observe(original_run, 'programming_helper',
                            lambda a, k: {'command': command})(*args, **kwargs)
        return original_run(*args, **kwargs)

    module.run = observed_run
    module._iris_host_phase_observer_installed = True


def summarize(text):
    """Pair completed events, retaining partial/failed observations explicitly."""
    starts, ends = {}, {}
    for line in text.splitlines():
        if not line.startswith(PREFIX):
            continue
        row = json.loads(line[len(PREFIX):])
        identity = row['id']
        if type(identity) is not int or identity < 0 or row.get('schema') != 'iris.host_setup_phase.v1':
            raise ValueError('Invalid host phase record')
        target = starts if row.get('event') == 'begin' else ends if row.get('event') == 'end' else None
        if target is None or identity in target:
            raise ValueError('Duplicate/invalid host phase event')
        target[identity] = row
    if set(ends) - set(starts):
        raise ValueError('Host phase end has no beginning')
    for identity, end in ends.items():
        start = starts[identity]
        for field in ('phase', 'parent_id', 'start_monotonic_ns', 'started_utc'):
            if end.get(field) != start.get(field):
                raise ValueError('Mismatched host phase event: ' + field)
        if type(end.get('host_elapsed_ns')) is not int or end['host_elapsed_ns'] < 0:
            raise ValueError('Invalid host phase duration')
    rows = [dict(starts[i], completion=ends.get(i)) for i in starts]
    def total(phase):
        selected = [e for e in ends.values() if e['phase'] == phase]
        if not selected or any(e['status'] != 'returned' or e.get('return_code') not in (None, 0) for e in selected):
            return None
        if any(s['phase'] == phase and i not in ends for i, s in starts.items()):
            return None
        return sum(e['host_elapsed_ns'] for e in selected) / 1e9
    return {'schema': 'iris.host_setup_summary.v1', 'records': rows,
            'partial_event_ids': sorted(set(starts) - set(ends)),
            'rsync_host_seconds': total('rsync_transfer'),
            'programming_helper_host_seconds': total('programming_helper'),
            'host_elapsed_only': True, 'nested_durations_are_not_additive': True,
            'programming_includes_helper_transport_reset_and_vivado': True,
            'copying_does_not_program_fpga': True, 'target_cycles_derived': False}
