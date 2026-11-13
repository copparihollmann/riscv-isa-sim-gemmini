#!/usr/bin/env python3
"""Emit a reviewable boot-only patch; never edit the concurrently developed core."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'third_party/riscv-isa-sim'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Core integration anchor changed: ' + old[:80])
    return text.replace(old, new)


def main():
    files = {}
    for name in ('riscv/cfg.h', 'riscv/processor.cc', 'riscv/sim.cc', 'spike_main/spike.cc'):
        original = (SOURCE / name).read_text()
        edited = original
        if name == 'riscv/cfg.h':
            edited = replace_once(edited, '  bool                    iris_vme = false;',
                '  bool                    iris_vme = false;\n'
                '  std::string             iris_bootrom_file; // explicit source-backed physical boot')
        elif name == 'riscv/processor.cc':
            edited = replace_once(edited, '  pc = DEFAULT_RSTVEC;',
                '  pc = proc->get_cfg().iris_bootrom_file.empty() ? DEFAULT_RSTVEC : 0x10000;')
        elif name == 'riscv/sim.cc':
            edited = replace_once(edited, '#include "sim.h"',
                '#include "sim.h"\n#include "../../../board/iris_boot.hpp"')
            edited = replace_once(edited,
                'void sim_t::reset()\n{\n  if (dtb_enabled)\n    set_rom();\n}',
                '''void sim_t::reset()
{
  if (cfg->iris_bootrom_file.empty()) {
    if (dtb_enabled) set_rom();
    return;
  }
  if (!dtb_enabled || !clint || cfg->hartids != std::vector<size_t>({0, 1, 2}))
    throw std::runtime_error("Iris physical boot requires DTB, CLINT and harts 0/1/2");
  auto prefix = iris_board::read_binary(cfg->iris_bootrom_file);
  auto rom = std::make_shared<iris_board::ReadOnlyBootROM>(prefix,
      std::vector<char>(dtb.begin(), dtb.end()));
  auto bootreg = std::make_shared<iris_board::BootAddressRegister>();
  add_device(iris_board::rom_base, rom);
  add_device(iris_board::bootreg_base, bootreg);
  // htif has loaded the ELF before reset(): model the external loader writing
  // the boot address register and raising hart 0's software interrupt.
  reg_t entry = cfg->start_pc.get(0).value_or(get_entry_point());
  uint8_t data[8];
  for (unsigned i = 0; i < 8; ++i) data[i] = uint8_t(entry >> (8 * i));
  if (!bootreg->store(0, 8, data)) throw std::runtime_error("Iris boot address write failed");
  const uint8_t release[4] = {1, 0, 0, 0};
  if (!clint->store(0, 4, release)) throw std::runtime_error("Iris boot release failed");
}''')
        else:
            edited = replace_once(edited,
                '  parser.option(0, "iris-vme", 0, [&](const char*){cfg.iris_vme = true;});',
                '  parser.option(0, "iris-vme", 0, [&](const char*){cfg.iris_vme = true;});\n'
                '  parser.option(0, "iris-bootrom", 1, [&](const char* path){cfg.iris_bootrom_file = path;});')
        files[name] = (original, edited)
    patch = ''.join(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
        fromfile='a/' + name, tofile='b/' + name)) for name, (old, new) in files.items())
    (HERE / 'core-changes.patch').write_text(patch)
    metadata = {'schema_version': 1, 'status': 'unapplied_boot_only_proposal',
                'base_input_sha256': {name: hashlib.sha256(old.encode()).hexdigest()
                                      for name, (old, _) in files.items()},
                'patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
                'limitations': ['Does not install board PMA, PLIC or UART replacements.',
                               'Does not change mtime frequency or hook timer callbacks.',
                               'Relative board header include assumes this workspace source layout.',
                               'Parent must reconcile with concurrent timing/core integration and refresh build provenance.']}
    (HERE / 'core-changes.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps({'patch_sha256': metadata['patch_sha256'], 'applied': False}))


if __name__ == '__main__':
    main()
