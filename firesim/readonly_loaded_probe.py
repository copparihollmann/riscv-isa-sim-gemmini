#!/usr/bin/env python3
"""Remote file/sysfs inspection only; never opens XDMA/BARs or starts a driver."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def metadata(path):
    result = {'path': str(path)}
    try:
        info = path.stat()
        result.update(mode=oct(stat.S_IMODE(info.st_mode)), uid=info.st_uid, gid=info.st_gid,
                      size=info.st_size, readable=os.access(path, os.R_OK), writable=os.access(path, os.W_OK),
                      executable=os.access(path, os.X_OK), symlink=path.is_symlink())
        if path.is_symlink(): result['target'] = str(path.resolve())
        if (str(path).startswith('/scratch/firesim/') and not path.is_symlink() and stat.S_ISREG(info.st_mode) and
                info.st_size <= 64 * 1024 * 1024):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
            result['sha256'] = digest.hexdigest()
    except OSError as error: result['error'] = str(error)
    return result


report = {'schema_version': 1, 'hardware_mutated': False, 'driver_started': False,
          'device_or_bar_opened': False, 'identity': {'uid': os.getuid(), 'groups': os.getgroups()},
          'directories': [], 'files': [], 'pci': [], 'xdma': []}
for directory in [Path.home(), Path('/scratch/firesim'), Path('/scratch/firesim/vme-collateral'),
                  Path('/scratch/firesim/sim_slot_0')]:
    entry = metadata(directory)
    if str(directory).startswith('/scratch/firesim') and directory.is_dir():
        entry['children'] = [metadata(path) for path in sorted(directory.iterdir())[:100]]
        for subdir in sorted(directory.iterdir()):
            if subdir.is_dir() and not subdir.is_symlink() and subdir.name in ('vme-collateral', 'sim_slot_0'):
                entry['subdirectories'] = [metadata(path) for path in sorted(subdir.iterdir())[:100]]
    report['directories'].append(entry)

candidates = [Path('/scratch/firesim/firesim-vme-binary.sh'), Path('/scratch/firesim/firesim-binary.sh'),
              Path('/scratch/firesim/firesim-db.json')]
for directory in [Path('/scratch/firesim/vme-collateral'), Path('/scratch/firesim/sim_slot_0')]:
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if (path.suffix in ('.json', '.yaml', '.yml', '.sh', '.tcl', '.log', '.txt') or
                any(word in path.name.lower() for word in ('metadata', 'triplet', 'quintuplet', 'uartlog', 'simlog'))):
                candidates.append(path)
for path in candidates:
    record = metadata(path)
    if path.is_file() and not path.is_symlink():
        try:
            with path.open('rb') as stream:
                if path.stat().st_size > 16000: stream.seek(max(0, path.stat().st_size - 16000))
                record['text_tail'] = stream.read(16000).decode(errors='replace')
        except OSError as error: record['read_error'] = str(error)
    report['files'].append(record)

for path in sorted(Path('/sys/bus/pci/devices').glob('*')):
    try:
        vendor = (path / 'vendor').read_text().strip()
        if vendor != '0x10ee': continue
        record = metadata(path)
        record['vendor'] = vendor
        record['device'] = (path / 'device').read_text().strip()
        record['driver'] = str((path / 'driver').resolve())
        record['resources'] = [metadata(path / name) for name in ('resource0', 'resource0_wc', 'config', 'enable')]
        if (path / 'xdma').is_dir(): record['xdma'] = [metadata(p) for p in sorted((path / 'xdma').iterdir())]
        report['pci'].append(record)
    except OSError: pass
for path in sorted(Path('/dev').glob('xdma*')): report['xdma'].append(metadata(path))
print(json.dumps(report, indent=2))
