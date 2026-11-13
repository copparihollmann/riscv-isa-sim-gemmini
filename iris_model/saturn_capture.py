"""Read source-clock-stamped Saturn telemetry without inferring knownness or time.

The physical input/output prefix and internal activity suffix have separate
schemas. These are raw source bits; a qualified semantic contract must decide
which fields are meaningful. This module does not simulate hardware or supply
captured state as model input.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import gzip
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
from types import MappingProxyType

MAGIC = 0x314E494254415349
HEADER = struct.Struct('<4Q')
WORD = struct.Struct('<Q')
PROFILES = ('compute', 'compute', 'rocket')


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError('Invalid ' + label)
    return value


@dataclass(frozen=True)
class Field:
    name: str
    width: int
    parts: tuple

    def raw_value(self, payload):
        value = 0
        for index, lo, width in self.parts:
            word = WORD.unpack_from(payload, index * 8)[0]
            if word >> width:
                raise ValueError('Out-of-width telemetry word: ' + self.name)
            value |= word << lo
        return value


@dataclass(frozen=True)
class Profile:
    name: str
    words: int
    physical_input_words: int
    physical_output_words: int
    activity_words: int
    fields: object


@dataclass(frozen=True)
class Layout:
    profiles: object
    clock_ids: tuple

    @property
    def counts(self):
        return tuple(self.profiles[p].words for p in PROFILES)


def _field(name, width, parts):
    if not isinstance(name, str) or not name:
        raise ValueError('Nonempty telemetry field name required')
    _integer(width, 'field width', 1)
    if width > 65536:
        raise ValueError('Unsupported telemetry field width')
    ordered = sorted(parts, key=lambda p: p[1])
    if [p[1] for p in ordered] != list(range(0, width, 64)):
        raise ValueError('Missing/overlapping telemetry field pieces: ' + name)
    for index, lo, bits in ordered:
        _integer(index, 'field word index')
        if bits != min(64, width - lo):
            raise ValueError('Incorrect telemetry word width: ' + name)
    return Field(name, width, tuple(ordered))


def layout_from_documents(physical, activity):
    if activity.get('schema') != 'iris.saturn_typed_internal_activity.v1':
        raise ValueError('Unsupported internal activity schema')
    if set(physical) != {'compute', 'rocket'} or set(activity.get('profiles', {})) != set(physical):
        raise ValueError('Both exact Iris source profiles required')
    result, clocks = {}, [None] * 3
    for name, harts in [('compute', [0, 1]), ('rocket', [2])]:
        ports, internal = physical[name], activity['profiles'][name]
        if (ports.get('source_harts') != harts or any(type(h) is not int for h in ports['source_harts'])
                or internal.get('unresolved') != []):
            raise ValueError('Unresolved source profile or hart binding')
        fields, occupied, offset = {}, set(), 0
        counts = []
        for direction in ('input', 'output'):
            pieces = {}
            words = ports['words'][direction]
            if not isinstance(words, list):
                raise ValueError('Physical word list required')
            counts.append(len(words))
            for index, word in enumerate(words):
                if _integer(word.get('word_index'), 'physical word index') != index or word.get('direction') != direction:
                    raise ValueError('Physical word index/direction mismatch')
                key = direction + '.' + word['name']
                width = _integer(word['width'], 'physical field width', 1)
                if key in pieces and pieces[key][0] != width:
                    raise ValueError('Inconsistent physical field widths')
                pieces.setdefault(key, (width, []))[1].append((offset + index,
                    _integer(word['lo'], 'physical field offset'), _integer(word['word_width'], 'physical word width', 1)))
            for key, (width, parts) in pieces.items():
                fields[key] = _field(key, width, parts)
            occupied.update(range(offset, offset + len(words)))
            offset += len(words)
        internal_words = _integer(internal['word_count'], 'activity word count', 1)
        for item in internal['fields']:
            key = item['name']
            if key in fields:
                raise ValueError('Duplicate telemetry field: ' + key)
            parts = [(offset + _integer(w['index'], 'activity word index'),
                      _integer(w['lo'], 'activity field offset'), _integer(w['width'], 'activity word width', 1)) for w in item['words']]
            for index, _, _ in parts:
                if index in occupied or not offset <= index < offset + internal_words:
                    raise ValueError('Overlapping/out-of-range activity word')
                occupied.add(index)
            fields[key] = _field(key, item['width'], parts)
        total = offset + internal_words
        if total > 65536 or occupied != set(range(total)):
            raise ValueError('Missing or excessive telemetry words')
        for hart in harts:
            clock = ports['clock_IDs'].get(str(hart))
            if not isinstance(clock, str) or not clock:
                raise ValueError('Source clock identity required')
            clocks[hart] = clock
        result[name] = Profile(name, total, counts[0], counts[1], internal_words, MappingProxyType(fields))
    return Layout(MappingProxyType(result), tuple(clocks))


@dataclass(frozen=True)
class Frame:
    tb: int
    source_edge: int
    hart: int
    source_clock_id: str
    profile: Profile
    payload: bytes

    def raw_value(self, name):
        try:
            field = self.profile.fields[name]
        except KeyError:
            raise ValueError('Unknown telemetry field: ' + str(name)) from None
        return field.raw_value(self.payload)


def _read_exact(stream, count, eof_ok=False):
    pieces, remaining = [], count
    while remaining:
        block = stream.read(remaining)
        if not isinstance(block, bytes):
            raise ValueError('Binary telemetry stream required')
        if not block:
            if eof_ok and remaining == count:
                return None
            raise ValueError('Truncated Saturn capture')
        pieces.append(block);remaining -= len(block)
    return b''.join(pieces)


class Reader:
    def __init__(self, stream, layout):
        self.stream, self.layout = stream, layout
        self.finished = False
        self.counts = [0, 0, 0]
        self.last_tb = [None, None, None]
        self._started = False

    def __iter__(self):
        if self._started:
            raise ValueError('Capture reader is single-use')
        self._started = True
        magic, *counts = HEADER.unpack(_read_exact(self.stream, HEADER.size))
        if magic != MAGIC or tuple(counts) != self.layout.counts:
            raise ValueError('Capture magic/profile word counts disagree with source schemas')
        previous_tb = None
        while True:
            header = _read_exact(self.stream, HEADER.size, eof_ok=True)
            if header is None:
                if not all(self.counts):
                    raise ValueError('Capture is missing a configured hart')
                self.finished = True
                return
            tb, edge, hart, count = HEADER.unpack(header)
            if hart >= 3 or count != self.layout.counts[hart]:
                raise ValueError('Invalid captured hart/word count')
            if edge != self.counts[hart]:
                raise ValueError('Missing, repeated or nonzero initial source edge')
            if ((previous_tb is not None and tb < previous_tb)
                    or (self.last_tb[hart] is not None and tb <= self.last_tb[hart])):
                raise ValueError('Captured testbench/source clock order regressed')
            payload = _read_exact(self.stream, count * 8)
            self.counts[hart] += 1;self.last_tb[hart] = previous_tb = tb
            yield Frame(tb, edge, hart, self.layout.clock_ids[hart],
                        self.layout.profiles[PROFILES[hart]], payload)


def _signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


@contextmanager
def verified_capture(path, layout, expected_sha256):
    """Verify exact ordinary-file bytes and require complete envelope consumption."""
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('Frozen capture SHA256 required')
    path = Path(path)
    initial = path.lstat()
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError('Capture must be an ordinary file')
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as raw:
        before = os.fstat(raw.fileno())
        if not stat.S_ISREG(before.st_mode) or _signature(initial) != _signature(before):
            raise ValueError('Capture changed while opening')
        digest = hashlib.sha256()
        for block in iter(lambda: raw.read(1024 * 1024), b''):
            digest.update(block)
        if digest.hexdigest() != expected_sha256:
            raise ValueError('Capture SHA256 differs from frozen receipt')
        raw.seek(0)
        try:
            with gzip.GzipFile(fileobj=raw, mode='rb') as stream:
                reader = Reader(stream, layout)
                yield reader
                if not reader.finished:
                    raise ValueError('Complete capture consumption required')
        finally:
            if (_signature(before) != _signature(os.fstat(raw.fileno()))
                    or _signature(before) != _signature(path.lstat())):
                raise ValueError('Capture changed while reading')
