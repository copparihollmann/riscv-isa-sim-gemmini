"""Self-contained fatal-aware launcher template; never changes modeled time."""
import hashlib
import os
from pathlib import Path
import struct
import sys

FATAL_SYMBOLS = {'z_fatal_error', 'z_riscv_fatal_error', 'k_sys_fatal_error_handler',
                 'arch_system_halt', '__assert_func', '__stack_chk_fail', 'abort'}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()


def fatal_addresses(path):
    data = Path(path).read_bytes()
    def unpack(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data): raise ValueError('Truncated ELF structure')
        return struct.unpack_from(fmt, data, offset)
    header = unpack('<16sHHIQQQIHHHHHH', 0)
    if header[0][:7] != b'\x7fELF\x02\x01\x01' or header[2] != 243:
        raise ValueError('RV64 little-endian ELF required')
    if header[11] != 64 or not header[12]: raise ValueError('ELF section table required')
    sections = [unpack('<IIQQQQIIQQ', header[6] + i * header[11]) for i in range(header[12])]
    if not any(row[1] == 2 for row in sections):
        raise ValueError('Unstripped symbol table required for automatic fatal-handler resolution')
    def section(row):
        offset, size = row[4], row[5]
        if offset > len(data) or size > len(data) - offset: raise ValueError('Truncated ELF section')
        return data[offset:offset + size]
    result = {}
    for row in sections:
        if row[1] not in (2, 11): continue
        if row[9] != 24 or row[5] % 24 or row[6] >= len(sections): raise ValueError('Invalid ELF symbol table')
        table, strings = section(row), section(sections[row[6]])
        for offset in range(0, len(table), 24):
            name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', table, offset)
            if name >= len(strings): raise ValueError('Invalid ELF symbol name')
            end = strings.find(b'\0', name)
            if end < 0: raise ValueError('Unterminated ELF symbol name')
            text = strings[name:end].decode('utf-8', errors='strict')
            if text in FATAL_SYMBOLS and index and value and info & 15 in (0, 2): result[text] = value
    return result


def launch(native, native_sha256, python, python_sha256, arguments):
    try:
        native, python = Path(native), Path(python)
        if Path(sys.executable).resolve() != python.resolve() or sha(python) != python_sha256:
            raise ValueError('Selected Python interpreter changed')
        if sha(native) != native_sha256: raise ValueError('Selected native binary changed')
        if not arguments: raise ValueError('Guest ELF argument required')
        elf = Path(arguments[-1]).resolve()
        if not elf.is_file(): raise ValueError('Last argument must be the guest ELF')
        before = sha(elf); configured = set(fatal_addresses(elf).values())
        raw = os.environ.get('IRIS_FATAL_PCS', '')
        if raw:
            for token in raw.split(','):
                value = int(token, 0)
                if not 0 <= value < 1 << 64: raise ValueError('Invalid explicit fatal PC')
                configured.add(value)
        environment = dict(os.environ)
        if configured: environment['IRIS_FATAL_PCS'] = ','.join(hex(v) for v in sorted(configured))
        if sha(elf) != before or sha(native) != native_sha256: raise ValueError('Input changed before native exec')
        os.execve(str(native), [str(native), *arguments], environment)
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        print('IRIS_LAUNCH_REFUSED: ' + str(error), file=sys.stderr)
        raise SystemExit(1)


def launcher_text(native, native_sha256, python, python_sha256):
    """Include this exact source in the wrapper; runtime needs no repo imports."""
    source = Path(__file__).read_text()
    return ('#!' + str(python) + ' -IS\n' + source +
            '\nif __name__ == "__main__":\n    launch(' + repr(str(native)) + ', ' +
            repr(native_sha256) + ', ' + repr(str(python)) + ', ' + repr(python_sha256) + ', sys.argv[1:])\n')
