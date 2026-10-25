"""Export an explicitly selected experimental source-service provider.

Source identity only; no model prices, hardware admission or timing qualification.
The adjacent original provider and its exporter are never modified.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from merlin_timing.provider_bundle import RUNTIME_HEADERS, export_bundle

SOURCES = ('README.md', 'bridge.cpp', 'provider.hpp', 'staged.hpp',
           'scratchpad_load.hpp', 'streamed_readout.hpp', 'identity_ingress.hpp',
           'packet_load.hpp', 'reader_packets.hpp', 'readout_geometry.hpp',
           'streamed_packet_readout.hpp', 'writer_packets.hpp',
           'instruction_context.hpp', 'instruction_suffix.hpp', 'posted.hpp', 'command_ingress.hpp', 'registered_transport.hpp', 'posted_readout_frontend.hpp',
           'posted_one_beat_writer.hpp','posted_source_d.hpp','posted_full_packet_writer.hpp','posted_cold_write.hpp','posted_banked_store.hpp','posted_victim_probe.hpp','posted_read_allocation.hpp')

def export(destination: Path):
    root = Path(__file__).absolute().parent / 'source_service'
    payloads = {}
    for name in SOURCES:
        path = root / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents):
            raise ValueError('source members must not resolve through symlinks')
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError('source members must be ordinary bounded files')
        payloads[name] = path.read_bytes()
    return export_bundle(payloads, destination, entrypoint='bridge.cpp', runtime_headers=(
        *RUNTIME_HEADERS, 'timing/core/include/merlin_timing/reservations.hpp',
        'timing/core/include/merlin_timing/posted_timeline.hpp',
        'timing/core/include/merlin_timing/posted_engine_stage.hpp',
        'timing/core/include/merlin_timing/memory_milestones.hpp','timing/write_transaction.hpp','timing/read_allocation.hpp'))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.bundle_dir), sort_keys=True))
