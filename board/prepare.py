#!/usr/bin/env python3
"""Freeze the actual Iris boot prefix and source-backed board integration facts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chipyard', type=Path, default=Path('/scratch/eygao/iris-cy'))
    args = parser.parse_args()
    root = args.chipyard.resolve()
    inputs = {
        'boot-config.scala': 'generators/chipyard/src/main/scala/config/fragments/PeripheralFragments.scala',
        'bootrom.rv64.img': 'generators/testchipip/src/main/resources/testchipip/bootrom/bootrom.rv64.img',
        'bootrom.S': 'generators/testchipip/bootrom/bootrom.S',
        'bootrom-linker.ld': 'generators/testchipip/bootrom/linker.ld',
        'boot-address-register.scala': 'generators/testchipip/src/main/scala/boot/BootAddrReg.scala',
        'bootrom.scala': 'generators/rocket-chip/src/main/scala/devices/tilelink/BootROM.scala',
        'register-router.scala': 'generators/rocket-chip/src/main/scala/tilelink/RegisterRouter.scala',
        'plic.scala': 'generators/rocket-chip/src/main/scala/devices/tilelink/Plic.scala',
        'clint.scala': 'generators/rocket-chip/src/main/scala/devices/tilelink/CLINT.scala',
        'uart.scala': 'generators/rocket-chip-blocks/src/main/scala/devices/uart/UART.scala',
        'uart-registers.scala': 'generators/rocket-chip-blocks/src/main/scala/devices/uart/UARTCtrlRegs.scala',
    }
    evidence = HERE / 'evidence'
    evidence.mkdir(exist_ok=True)
    files = {}
    for name, relative in inputs.items():
        path = root / relative
        data = path.read_bytes()
        (evidence / name).write_bytes(data)
        files[name] = {'source_path': str(path), 'snapshot': 'evidence/' + name,
                       'sha256': sha(data), 'bytes': len(data)}
    prefix = (evidence / 'bootrom.rv64.img').read_bytes()
    if len(prefix) != 0xc0 or prefix[:4] != bytes.fromhex('17050000'):
        raise ValueError('ROM geometry/reset instruction changed; audit before updating helpers')
    hardware = HERE.parent / 'hardware/evidence'
    for name in ('firesim-dts.dts', 'firesim-memmap.json'):
        data = (hardware / name).read_bytes()
        (evidence / name).write_bytes(data)
        files[name] = {'source_path': str(hardware / name), 'snapshot': 'evidence/' + name,
                       'sha256': sha(data), 'bytes': len(data)}
    regions = json.loads((hardware / 'firesim-memmap.json').read_text())['mapping']
    lines = ['// Generated from frozen elaborated memmap; do not infer transfer timing.',
             '#pragma once', '#include <cstdint>', '#include <cstddef>',
             'namespace iris_board {',
             'enum class Access { Read, Write, Execute, Atomic };',
             'struct Region { const char* name; uint64_t base, size; bool read, write, execute, atomics; };',
             'inline constexpr Region regions[] = {']
    for r in regions:
        if any(len(r[k]) != 1 for k in ('base', 'size', 'r', 'w', 'x', 'a', 'names')):
            raise ValueError('Unexpected elaborated region shape')
        flags = ', '.join(str(r[k][0]).lower() for k in ('r', 'w', 'x', 'a'))
        lines.append('  {' + json.dumps(r['names'][0]) + ', ' + hex(r['base'][0]) + 'ULL, ' +
                     hex(r['size'][0]) + 'ULL, ' + flags + '},')
    lines.extend(['};', 'inline const Region* region_for(uint64_t address, size_t bytes) {',
                  '  if (!bytes) return nullptr;', '  for (const auto& region : regions)',
                  '    if (address >= region.base && address - region.base < region.size &&',
                  '        bytes <= region.size - (address - region.base)) return &region;',
                  '  return nullptr;', '}',
                  'inline bool permits(uint64_t address, size_t bytes, Access access) {',
                  '  const auto* r = region_for(address, bytes);', '  if (!r) return false;',
                  '  switch (access) {', '    case Access::Read: return r->read;',
                  '    case Access::Write: return r->write;',
                  '    case Access::Execute: return r->execute;',
                  '    case Access::Atomic: return r->read && r->write && r->atomics;',
                  '  }', '  return false;', '}', '}  // namespace iris_board', ''])
    (HERE / 'physical_map.hpp').write_text('\n'.join(lines))
    pins = {}
    for repo in ('chipyard', 'testchipip', 'rocket-chip', 'rocket-chip-blocks'):
        path = root if repo == 'chipyard' else root / 'generators' / repo
        pins[repo] = subprocess.check_output(['git', '-c', 'safe.directory=' + str(path),
            '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    for source in files.values():
        original = source['source_path']
        repo = next((name for name in pins if name != 'chipyard' and
                     '/generators/' + name + '/' in original), 'chipyard')
        source.update(repository=repo, repository_commit=pins[repo])
    manifest = {'schema_version': 1, 'status': 'source_backed_helpers_not_integrated_board',
                'repositories': pins, 'sources': files, 'reset_pc': 0x10000,
                'rom_base': 0x10000, 'rom_size': 0x10000, 'dtb_offset': len(prefix),
                'boot_address_register_base': 0x1000, 'boot_address_register_size': 0x1000,
                'boot_address_default': 0x80000000, 'clint_base': 0x2000000,
                'mtime_hz': 500000, 'plic_base': 0xc000000, 'plic_size': 0x4000000,
                'plic_sources': 1, 'plic_max_priority': 1,
                'plic_contexts': [{'hart': h, 'privilege': p} for h in range(3) for p in ('M', 'S')],
                'uart_base': 0x10020000, 'uart_interrupt_source': 1,
                'uninitialized_rtl_registers': ['CLINT.mtimecmp[0..2]', 'PLIC.priority[1]',
                                                'PLIC.threshold[0..5]', 'PLIC.enable[0..5]'],
                'physical_map_sha256': sha((HERE / 'physical_map.hpp').read_bytes()),
                'fact_evidence': {
                    'reset_pc': [{'source': 'boot-config.scala', 'lines': [30, 45]}],
                    'rom_base': [{'source': 'firesim-dts.dts', 'lines': [187, 191]}],
                    'rom_size': [{'source': 'firesim-dts.dts', 'lines': [187, 191]}],
                    'dtb_offset': [{'source': 'bootrom.rv64.img', 'byte_length': len(prefix)},
                                   {'source': 'bootrom.scala', 'lines': [90, 96]}],
                    'boot_address_register_base': [{'source': 'boot-address-register.scala', 'lines': [12, 15]}],
                    'boot_address_register_size': [{'source': 'boot-address-register.scala', 'lines': [25, 30]}],
                    'boot_address_default': [{'source': 'boot-address-register.scala', 'lines': [12, 15]}],
                    'clint_base': [{'source': 'bootrom.S', 'lines': [6, 8]}],
                    'mtime_hz': [{'source': 'firesim-dts.dts', 'lines': [13, 17]}],
                    'plic_base': [{'source': 'firesim-dts.dts', 'lines': [168, 176]}],
                    'plic_size': [{'source': 'firesim-dts.dts', 'lines': [168, 176]}],
                    'plic_sources': [{'source': 'firesim-dts.dts', 'lines': [168, 176]}],
                    'plic_max_priority': [{'source': 'firesim-dts.dts', 'lines': [168, 176]}],
                    'plic_contexts': [{'source': 'firesim-dts.dts', 'lines': [168, 176]}],
                    'uart_base': [{'source': 'firesim-dts.dts', 'lines': [201, 208]}],
                    'uart_interrupt_source': [{'source': 'firesim-dts.dts', 'lines': [201, 208]}],
                    'uninitialized_rtl_registers': [{'source': 'clint.scala', 'lines': [71, 81]},
                                                     {'source': 'plic.scala', 'lines': [166, 184]}],
                },
                'limitations': ['No deployed bitstream binding.', 'No boot/timer/PLIC helper is installed into Spike automatically.',
                               'PMA helper validates coarse region permission; transfer sizes and transaction-specific access faults require core integration.']}
    (HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'rom_sha256': files['bootrom.rv64.img']['sha256'], 'prefix_bytes': len(prefix),
                      'mapped_regions': len(regions)}))


if __name__ == '__main__':
    main()
