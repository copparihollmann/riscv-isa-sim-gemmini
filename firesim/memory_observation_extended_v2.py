"""Frozen five-register observer contract; no device/network operation on import."""
import hashlib
import json
from pathlib import Path
try:
    from firesim import memory_observation as parent
except ModuleNotFoundError:
    import memory_observation as parent

ROOT=Path(__file__).resolve().parents[1]
SOURCE_SHA='3d2bdcb026d88bed7072cc1686c38576700f6e1c09dc1423428fe3c1762067de'
BINARY_SHA='dc3f7860fc265741553adf46f2d8c38c098ee7f8ad11a3aacb8f5f5fe49457c2'
HEADER_SHA=parent.HEADER_SHA
REMOTE=parent.REMOTE
PROBE_SCHEMA='iris.readonly_fased_config_probe.v2'
REGISTER_MAP={'writeLatency':0,'readLatency':4,'writeMaxReqs':8,'readMaxReqs':12,'relaxFunctionalModel':72}
AUDIT=ROOT/'build/fased-config-MMIO-audit-v2/report.json'
AUDIT_SHA='18b65f502a1cf7b203b04d8e61d73960bd8d5ebfb6495770ff537af4a99706e7'


def verify_audit():
    def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    if sha(AUDIT)!=AUDIT_SHA:raise ValueError('Frozen extended MMIO audit changed')
    j=json.loads(AUDIT.read_text())
    if(j['schema']!='iris.archived_fased_configuration_MMIO_audit.v2'or j['pass']is not True
       or j['driver_binary_sha256']!='8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a'
       or j['registers_readable']!=REGISTER_MAP or j['registers_writable']!=REGISTER_MAP
       or any(type(v)is not int for field in('registers_readable','registers_writable')for v in j[field].values())):
        raise ValueError('All five R/W configuration mappings must be independently proved')
    inputs=dict(j['input_sha256']);inputs[str(AUDIT)]=AUDIT_SHA
    inputs[str(Path(parent.__file__).resolve())]=sha(parent.__file__)
    for p,h in inputs.items():
        if sha(p)!=h:raise ValueError('Extended MMIO audit input changed: '+p)
    return inputs
