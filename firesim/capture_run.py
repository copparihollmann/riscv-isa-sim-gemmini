#!/usr/bin/env python3
"""Archive a quiescent FireSim run and its evidence; never contacts hardware.

Run after owned cleanup (also after failure). This captures existing evidence,
not instrumentation that was disabled in the loaded image.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

SNAPSHOTS = ('GOAL.md', 'HANDOFF.md', 'AGENTS.md', 'hardware/manifest.json',
             'hardware/dtypes.json', 'hardware/memory-paths.json',
             'spike/provenance.json', 'firesim/access-audit.json',
             'firesim/runtime-comparison.json', 'firesim/source-clones.json',
             'firesim/batch_runner.py', 'firesim/run_prepared.py',
             'firesim/prepare_campaign.py', 'firesim/OPERATING_RULES.md',
             'firesim/CAMPAIGN_POLICY.md', 'firesim/capture_run.py')

class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.hash = hashlib.sha256()
    def read(self, count=-1):
        data = self.stream.read(count)
        self.hash.update(data)
        return data

def signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)

def capture(job, output, workspace=None):
    job, output = Path(job).resolve(), Path(output).absolute()
    if not job.is_dir() or not (job/'run.json').is_file():
        raise ValueError('Job directory with run.json required')
    if output == job or job in output.resolve().parents:
        raise ValueError('Archive must be outside the job directory')
    if output.exists():
        raise FileExistsError(output)
    workspace = Path(workspace).resolve() if workspace else None
    partial = output.with_name(output.name + '.partial')
    entries, skipped, missing = [], [], []
    candidates = []
    # Never traverse manager library/platform symlinks into shared source trees.
    for directory, dirs, names in os.walk(job, followlinks=False):
        root = Path(directory)
        for name in list(dirs):
            path = root/name
            if path.is_symlink():
                skipped.append({'path':str(path.relative_to(job)), 'reason':'symlink directory'})
                dirs.remove(name)
        candidates.extend((root/name, 'job/'+str((root/name).relative_to(job))) for name in sorted(names))
    if workspace:
        for name in SNAPSHOTS:
            path = workspace/name
            if path.exists(): candidates.append((path, 'context/'+name))
            else: missing.append(name)
    with partial.open('xb') as raw, tarfile.open(fileobj=raw, mode='w:gz') as archive:
        for path, name in candidates:
            before = path.lstat()
            if not stat.S_ISREG(before.st_mode):
                skipped.append({'path':name,'reason':'symlink or non-regular file'})
                continue
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
            with os.fdopen(os.open(path, flags), 'rb') as stream:
                if signature(os.fstat(stream.fileno())) != signature(before):
                    raise RuntimeError('Evidence changed before capture: '+str(path))
                info = archive.gettarinfo(str(path), arcname=name)
                reader = HashingReader(stream)
                archive.addfile(info, reader)
                if signature(os.fstat(stream.fileno())) != signature(before) or signature(path.lstat()) != signature(before):
                    raise RuntimeError('Evidence changed during capture: '+str(path))
                entries.append({'path':name,'bytes':before.st_size,'sha256':reader.hash.hexdigest()})
        manifest = {'schema_version':1,'captured_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'job':str(job),'hardware_contacted':False,'files':entries,'skipped':skipped,
                    'missing_optional_context':missing,
                    'note':'Hashes bind archived bytes. Context is a capture-time snapshot, not image build attestation. Missing/disabled counters or traces remain unavailable.'}
        data = (json.dumps(manifest,indent=2)+'\n').encode()
        info = tarfile.TarInfo('capture-manifest.json');info.size=len(data)
        archive.addfile(info,io.BytesIO(data))
    # Publish without overwriting an existing archive, even if another process raced us.
    os.link(partial, output)
    partial.unlink()
    return {'archive':str(output),'files':len(entries),'bytes':sum(row['bytes'] for row in entries),'skipped':len(skipped)}

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('job',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args()
    print(json.dumps(capture(args.job,args.output,args.workspace)))

if __name__=='__main__':main()
