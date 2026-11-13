"""Primary dispatcher for one immutable, source-built Iris release."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def selected_release():
    current=HERE/'current'
    if not current.is_symlink():raise ValueError('No coordinated current Iris release')
    release=current.resolve(strict=True)
    if not release.is_relative_to((HERE/'releases').resolve()):raise ValueError('Current release escapes the versioned release directory')
    data=json.loads((release/'provenance.json').read_text());path=release/'provider.py'
    if data.get('schema')!='iris.combined_sdk4.package.v1'or _sha(path)!=data['input_sha256']['provider.py']:
        raise ValueError('Release provider/source identity mismatch')
    extras=json.loads((release/'publication-inputs.json').read_text())
    if extras.get('schema')!='iris.primary_sdk4.release_views.v1':raise ValueError('Missing matched publication SDK/source views')
    for name,digest in extras['input_sha256'].items():
        target=(release/name).resolve()
        if not target.is_relative_to(release)or not target.is_file()or _sha(target)!=digest:
            raise ValueError('Publication SDK/source view changed: '+name)
    aliases={'bin/spike-iris-functional':'bin/spike','bin/libsifive_uart.so':'bin/libsifive_uart.so',
        'bin/spike-iris-launch':'launch.py','include':'sdk','build':'compat-sdk','source':'source/third_party/riscv-isa-sim-combined',
        'iris.patch':'iris.patch','provenance.json':'provenance.json'}
    for alias,target in aliases.items():
        if (HERE/alias).resolve()!=(release/target).resolve():raise ValueError('Primary alias differs from selected release: '+alias)
    spec=importlib.util.spec_from_file_location('iris_current_release_provider',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return release,module

def device_simulator(unit=None,config=None):
    return {'available':False,'binary':None,'binary_sha256':None,'isa_extensions':[],
        'provenance':{'selection':'full_model'},
        'reason':'Full Iris model unavailable: experimental functional coverage; full RTL/image association and calibrated timing remain unqualified.'}

def experimental_functional_simulator():
    try:
        release,module=selected_release();value=module.experimental_functional_simulator()
        if value.get('available')is True:
            value['selected_release']=str(release)
            value['primary_dispatcher_sha256']=_sha(Path(__file__))
        return value
    except (OSError,ValueError,KeyError,TypeError,AttributeError)as error:
        return {'available':False,'reason':'Invalid current Iris release: '+str(error),'timing_available':False,'rtl_certified':False}

if __name__=='__main__':print(json.dumps(device_simulator(),indent=2))
