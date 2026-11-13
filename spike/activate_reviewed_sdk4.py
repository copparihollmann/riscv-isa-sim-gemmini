#!/usr/bin/env python3
"""Activate the reviewed local functional release, retaining complete rollback bytes.

The coordinator must first quiesce primary software consumers. This does not
contact hardware, replace the shared Git anchor, or certify the full model.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def metadata(path):
    if path.is_symlink():
        return {'type': 'symlink', 'target': os.readlink(path)}
    if not path.exists():
        return {'type': 'absent'}
    info = path.stat()
    if path.is_dir():
        return {'type': 'directory', 'inode': info.st_ino, 'mode': stat.S_IMODE(info.st_mode)}
    return {'type': 'file', 'sha256': sha(path), 'mode': stat.S_IMODE(info.st_mode)}


def activate(review_path, output):
    review = json.loads(review_path.read_text())
    if review.get('status') != 'review_ready_not_published' or review.get('primary_published') is not False:
        raise ValueError('A reviewed, unpublished candidate is required')
    candidate = Path(review['candidate_root'])
    sources, aliases = review['source_updates'], review['symlink_updates']
    inventory_path = review_path.with_name(review['new_release_inventory'])
    inventory = json.loads(inventory_path.read_text())
    # Validate both sides before writing any active path.
    for name, row in sources.items():
        current, staged = ROOT / name, candidate / name
        if sha(staged) != row['sha256'] or stat.S_IMODE(staged.stat().st_mode) != row['mode']:
            raise ValueError('Candidate source changed: ' + name)
        if (sha(current) if current.exists() else None) != row['old_sha256']:
            raise ValueError('Primary source changed since review: ' + name)
    for name, expected in review['receipts'].items():
        if sha(name) != expected:
            raise ValueError('Review evidence changed: ' + name)
    # No active FPGA input may resolve through a changed path or directory.
    for run in (ROOT / 'runs').glob('*/broad-fit/run.json'):
        record = json.loads(run.read_text())
        if record.get('lifecycle_started') and record.get('status') == 'prepared':
            for bound in record.get('input_sha256', {}):
                path = Path(bound)
                if any(path == ROOT / name or ROOT / name in path.parents for name in (*sources, *aliases)):
                    raise ValueError('Active FPGA input overlaps local publication: ' + bound)
    anchor = ROOT / 'third_party/riscv-isa-sim/.git'
    anchor_identity = (anchor.stat().st_dev, anchor.stat().st_ino)
    anchor_index = sha(anchor / 'index')
    output.mkdir(parents=True, exist_ok=False)
    original = {name: metadata(ROOT / name) for name in (*sources, *aliases)}
    (output / 'before.json').write_text(json.dumps(original, indent=2) + '\n')
    (output / 'review.json').write_bytes(review_path.read_bytes())
    backup = output / 'rollback'
    backup.mkdir()
    subprocess.run(['cp', '-a', '--reflink=auto', str(ROOT / 'spike'), str(backup / 'spike')], check=True)
    for name in sources:
        if not name.startswith('spike/') and (ROOT / name).exists():
            destination = backup / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
    payloads = ('spike/releases/combined-359-sdk4', 'spike/historical-5e6-dispatch')
    stage = output / 'staged-payloads'
    for name in payloads:
        if (ROOT / name).exists():
            raise ValueError('Publication destination already exists; preserve it: ' + name)
        shutil.copytree(candidate / name, stage / name, symlinks=True)
    for name, row in inventory.items():
        if not any(name.startswith(prefix + '/') for prefix in payloads):
            raise ValueError('Unexpected reviewed payload path: ' + name)
        path = stage / name
        if sha(path) != row['sha256'] or stat.S_IMODE(path.stat().st_mode) != row['mode']:
            raise ValueError('Staged release inventory mismatch: ' + name)
    for name in payloads:
        (ROOT / name).parent.mkdir(exist_ok=True)
        (stage / name).rename(ROOT / name)
    changed = []
    try:
        for name, row in sources.items():
            path = ROOT / name
            if metadata(path) != original[name]:
                raise ValueError('Primary changed during coordinated publication: ' + name)
            temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
            shutil.copy2(candidate / name, temporary)
            changed.append(name)
            os.replace(temporary, path)
        # First migration has multiple paths; only subsequent selection is a
        # one-pointer transaction. Keep the selector last and retain rollback.
        for name, target in sorted(aliases.items(), key=lambda row: row[0] == 'spike/current'):
            path = ROOT / name
            if metadata(path) != original[name]:
                raise ValueError('Primary alias changed during coordinated publication: ' + name)
            if path.is_dir() and not path.is_symlink():
                moved = output / 'displaced' / name
                moved.parent.mkdir(parents=True, exist_ok=True)
                path.rename(moved)
            changed.append(name)
            temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
            temporary.symlink_to(target)
            os.replace(temporary, path)
        if (anchor.stat().st_dev, anchor.stat().st_ino) != anchor_identity or sha(anchor / 'index') != anchor_index:
            raise ValueError('Shared Git anchor changed')
    except BaseException:
        for name in reversed(changed):
            path = ROOT / name
            if path.is_symlink() or path.is_file():
                path.unlink()
            displaced = output / 'displaced' / name
            saved = backup / name
            if displaced.exists():
                displaced.rename(path)
            elif original[name]['type'] != 'absent':
                if saved.is_symlink():
                    path.symlink_to(os.readlink(saved))
                else:
                    shutil.copy2(saved, path)
        raise
    report = {'schema': 'iris.primary_sdk4.activation.v1', 'status': 'active_experimental_functional',
              'review_sha256': sha(review_path), 'inventory_sha256': sha(inventory_path),
              'backup': str(backup), 'changed_paths': changed, 'aliases': aliases,
              'native_sha256': review['native_sha256'], 'uart_sha256': review['uart_sha256'],
              'launcher_sha256': review['launcher_sha256'], 'native_device_abi': 4,
              'shared_git_anchor_unchanged': True, 'initial_migration_multi_path': True,
              'hardware_contacted': False, 'full_model_available': False,
              'rtl_certified': False, 'timing_certified': False, 'held_out_2pct': False,
              'activated_at_unix': time.time(), 'post_activation_validation': 'required'}
    (output / 'activation.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with (ROOT / 'spike/.release-switch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(activate(args.review.resolve(), args.output.resolve())))


if __name__ == '__main__':
    main()
