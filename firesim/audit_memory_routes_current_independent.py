#!/usr/bin/env python3
"""Independent stdlib-only audit of the captured three-trial memory experiment.

This reads local evidence only, after owned cleanup. No repository validation,
preparation, capture or hardware module is imported.
"""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import tarfile
from urllib.parse import urlparse, unquote

ROLE='memory_routes_current_fitting_v1'
ELF_SHA='bc35d90129829608f681a9451502806d54dcbf331d5e30b8e4bb70749148d268'
IMAGE_SHA='9bbe1f12a2b18091c28b05ea43c001e579f70c8cfef0f528fcb49003212fb776'
BIT_SHA='fe3e6097489f14b10ecdeaf0d781201835810de41635b46b92426095cbda1e98'
DRIVER_SHA='5457de1e9c0dd1e3c52efbf5d083bdac7dfa5a5e3124c9887961c08159b03450'
KERNEL_SHA='651c8ade2c6c416f9b9cfcb07050ba9434004ec2ef04486fc2616ae30feb8801'
TARGETS=(('tcm0',0x70000000),('tcm1',0x70020000),('scratchpad',0x580000000),('dram',0x84000000))


def need(test,message):
    if not test: raise ValueError(message)


def hash_bytes(raw):return hashlib.sha256(raw).hexdigest()


def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def pairs(items):
    out={}
    for key,value in items:
        need(key not in out,'Duplicate JSON key: '+key);out[key]=value
    return out


def js(raw):return json.loads(raw,object_pairs_hook=pairs)


def uint(value):return type(value) is int and 0<=value<2**64


def read_archive(path,expected_manifest):
    """Hash every inventoried byte, with no extraction or path traversal."""
    retained={};ids={};total=0
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers();names=[m.name for m in members]
        need(len(names)==len(set(names)),'Duplicate archive member')
        for m in members:
            p=PurePosixPath(m.name)
            need(m.isfile() and not p.is_absolute() and '..' not in p.parts and str(p)==m.name,'Unsafe/nonregular archive member')
        inventory=js(archive.extractfile('capture-manifest.json').read())
        need(inventory.get('schema_version')==1 and inventory.get('hardware_contacted') is False,'Capture inventory schema/scope')
        for row in inventory['files']:
            name=row['path'];need(name not in ids and name!='capture-manifest.json','Duplicate/self inventory entry')
            need(type(row['bytes']) is int and row['bytes']>=0 and re.fullmatch('[0-9a-f]{64}',row['sha256']),'Inventory field types')
            member=archive.getmember(name);h=hashlib.sha256();size=0;blocks=[]
            keep=(name in ('job/run.json','job/corpus.json','job/ready.json','job/build.json','job/readback-layout.json','job/manager/workloads/iris-batch/batch.elf','job/launch-authorization.json','job/manager/config_runtime.yaml') or name.endswith('/uartlog'))
            with archive.extractfile(member) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    h.update(block);size+=len(block)
                    if keep:blocks.append(block)
            need(size==member.size==row['bytes'] and h.hexdigest()==row['sha256'],'Inventory bytes differ: '+name)
            ids[name]=h.hexdigest();total+=size
            if keep:retained[name]=b''.join(blocks)
        need(set(names)==set(ids)|{'capture-manifest.json'},'Missing/uninventoried archive member')
    need(ids.get('job/run.json')==expected_manifest,'Archived result manifest differs from capture receipt')
    return retained,ids,total


def canonical():
    cases=[]
    for target,base in TARGETS:
        for pattern,stride,spread in (('bank0',128,0),('hart-banks',128,1),('alternating',64,0)):
            for kind,counts in (('chase',(33,257)),('read',(1,16)),('write',(1,16))):
                for n in counts:
                    for mask in range(1,8):
                        parent='memroute.%s.%s.%s.%d.mask%d'%(target,pattern,kind,n,mask)
                        for trial in range(3):
                            c=dict(target_region=target,base=base,stride=stride,spread=spread,kind=kind,n=n,mask=mask,parent_case_id=parent,trial_id=trial,suite='memory_routes_current',case_id='memroute.current.v1.%s.r%d'%(parent,trial),semantic_parent_case_id='memroute.%s.%s.%s.mask%d'%(target,pattern,kind,mask))
                            cases.append(c)
    need(len(cases)==1512,'Independent enumeration size');return cases


def golden(c,h):
    address=c['base']+h*32768+(64*(h&1) if c['spread'] else 0)
    if c['kind']=='chase':return address+((13*c['n'])%64)*c['stride']
    if c['kind']=='read':return c['n']*(64*(4096+256*h)+2016)
    return 64*(256*c['n']+h)


def check_corpus(corpus):
    need(corpus.get('schema')=='iris.memory_routes_current_corpus.v1' and corpus.get('trials')==3 and corpus.get('physical_harts')==3 and corpus.get('expected_region_count')==2592 and corpus.get('fitting_only') is True and corpus.get('global_heldout') is False,'Wrong corpus scope')
    expected=canonical();need(len(corpus['cases'])==1512,'Corpus case count')
    for c,wanted in zip(corpus['cases'],expected):
        need(all(c.get(k)==v and type(c.get(k)) is type(v) for k,v in wanted.items()),'Corpus order/identity/geometry')
        pointers=[c['base']+h*32768+(64*(h&1) if c['spread'] else 0)for h in range(3)]
        need(c['addresses_by_hart']==pointers and c['expected_checksums']==[golden(c,h)for h in range(3)],'Corpus pointer/independent golden')
        need(c['node_count']==64 and c['window_bytes_per_hart']==32768,'Corpus node/window geometry')
        need(c['bank_bit6_sequence_by_hart']==[[((a+i*c['stride'])>>6)&1 for i in range(64)]for a in pointers],'Corpus bank-bit geometry')
        for h,a in enumerate(pointers):need(c['base']+h*32768<=a and a+63*c['stride']+8<=c['base']+(h+1)*32768,'Corpus region overlap')
    return expected


class Elf:
    def __init__(self,raw):
        self.raw=raw;need(len(raw)>=64 and raw[:7]==b'\x7fELF\x02\x01\x01','ELF64 little endian header')
        need(self.unpack('<H',18)[0]==243,'ELF architecture')
        po=self.unpack('<Q',32)[0];ps,pn=self.unpack('<HH',54);self.loads=[]
        need(ps==56 and pn>0 and po+ps*pn<=len(raw),'ELF program table')
        for i in range(pn):
            typ,flags,off,va,pa,filesz,memsz,align=self.unpack('<IIQQQQQQ',po+i*ps)
            if typ==1:
                need(filesz<=memsz and off+filesz<=len(raw) and va==pa and pa+memsz<2**64,'ELF load bounds')
                need(all(not(max(pa,base)<min(pa+memsz,base+0x20000))for _,base in TARGETS),'ELF overlaps target memory')
                self.loads.append((pa,off,filesz,memsz))
        so=self.unpack('<Q',40)[0];ss,sn=self.unpack('<HH',58)
        need(ss==64 and sn>0 and so+ss*sn<=len(raw),'ELF section table')
        sections=[self.unpack('<IIQQQQIIQQ',so+i*ss)for i in range(sn)];self.syms={}
        for s in sections:
            if s[1]!=2:continue
            need(s[6]<sn and s[9]==24 and s[5]%24==0 and s[4]+s[5]<=len(raw),'ELF symtab bounds')
            st=sections[s[6]];need(st[4]+st[5]<=len(raw),'ELF string table bounds');strings=raw[st[4]:st[4]+st[5]]
            for pos in range(s[4],s[4]+s[5],24):
                name,info,other,index,value,size=self.unpack('<IBBHQQ',pos)
                if not index or not name:continue
                end=strings.find(b'\0',name);need(0<name<len(strings) and end>=name,'ELF symbol string')
                symbol=strings[name:end].decode('utf-8');entry=(value,size)
                if symbol not in ('experiments','kernel','buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count'):continue
                need(symbol not in self.syms or self.syms[symbol]==entry,'Ambiguous ELF symbol');self.syms[symbol]=entry
    def unpack(self,fmt,offset):
        need(0<=offset<=len(self.raw)-struct.calcsize(fmt),'ELF field bounds');return struct.unpack_from(fmt,self.raw,offset)
    def read(self,address,size):
        matches=[(base,off)for base,off,fs,ms in self.loads if base<=address and address+size<=base+fs]
        need(len(matches)==1 and size>=0,'ELF file-backed read');base,off=matches[0];return self.raw[off+address-base:off+address-base+size]
    def string(self,address):
        out=bytearray()
        for i in range(256):
            value=self.read(address+i,1)
            if value==b'\0':return out.decode('utf-8')
            out+=value
        raise ValueError('ELF unterminated case ID')


def check_elf(raw,cases,layout):
    e=Elf(raw);address,size=e.syms['experiments'];need(size==1512*64,'ELF compiled table size')
    for i,c in enumerate(cases):
        row=struct.unpack('<QQIIIII4xQQQ',e.read(address+i*64,64))
        need(e.string(row[0])==c['case_id'],'ELF compiled case order/ID')
        need(row[1:7]==(c['base'],('chase','read','write').index(c['kind']),c['stride'],c['spread'],c['n'],c['mask']),'ELF compiled geometry')
        need(row[7:]==tuple(golden(c,h)for h in range(3)),'ELF compiled independent goldens')
    k,ks=e.syms['kernel'];need(ks==160 and hash_bytes(e.read(k,ks))==KERNEL_SHA,'ELF original kernel code')
    objects={name:{'address':e.syms[name][0],'size':e.syms[name][1]}for name in ('buffered_records','buffered_measurements_done','buffered_record_count','buffered_case_count')}
    need(layout['objects']==objects and objects['buffered_records']['size']==2592*64,'ELF buffered geometry')
    need(layout['record_bytes']==64 and layout['records']==2592 and layout['fields']==['case_index','hart','start','end','instret','checksum','expected','pass'],'Readback record fields')
    need(e.read(objects['buffered_measurements_done']['address'],8)==b'\xff'*8,'ELF initialized sentinel')
    return {'compiled_records':1512,'compiled_goldens':4536,'readback_records':2592,'kernel_bytes':160}


def check_uart(raw,cases):
    text=raw.decode('utf-8','strict');need('IRIS_FATAL' not in text,'Guest fatal')
    rows=[];term=[]
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('IRIS_REGION'):need(line.startswith('IRIS_REGION '),'Malformed region prefix');rows.append(js(line[12:]))
        if line.startswith('IRIS_BATCH_DONE'):need(line.startswith('IRIS_BATCH_DONE '),'Malformed terminal prefix');term.append(js(line[16:]))
    want=[(c,h)for c in cases for h in range(3)if c['mask']&(1<<h)]
    need(len(rows)==len(want)==2592,'UART complete region count')
    previous={};by_hart=collections.Counter();kinds=collections.Counter()
    for row,(c,h)in zip(rows,want):
        need(isinstance(row,dict) and row.get('case_id')==c['case_id'] and row.get('hart')==h,'UART case/hart order')
        for key in ('hart','trial_id','start_cycle','end_cycle','instret_delta','checksum','expected_checksum'):need(uint(row.get(key)),'UART unsigned field '+key)
        need(all(row.get(k)==c[k]for k in ('parent_case_id','trial_id','suite')) and row.get('region')=='kernel','UART trial/parent identity')
        need(previous.get(h,-1)<row['start_cycle']<row['end_cycle'] and row['instret_delta']>0,'UART interval order/retirement')
        previous[h]=row['end_cycle']
        need(row['checksum']==row['expected_checksum']==golden(c,h) and row.get('pass') is True,'UART independent checksum')
        by_hart[h]+=1;kinds[c['kind']]+=1
    need(term==[{'failed':0,'cases':1512,'regions':2592}],'UART terminal contract')
    need(all(type(v)is int for v in term[0].values()),'UART terminal types')
    return rows,{'regions':len(rows),'by_hart':dict(by_hart),'by_kernel':dict(kinds),'three_trial_groups':864}


def check_role(manifest):
    need(manifest.get('campaign_role')==ROLE and manifest.get('expected_regions')==2592 and manifest.get('fitting_only') is True and manifest.get('global_heldout') is False and manifest.get('old_campaign_timings_applicable') is False and manifest.get('new_exact_ELF_reference_required') is True,'Wrong archived experiment role')
    need(manifest.get('require_regions') is True and manifest.get('require_goldens') is True,'Goldens not required')


def check_lifecycle(manifest,current,ids):
    need(manifest.get('status')==current.get('status')=='completed_uncertified' and manifest.get('cleanup_status')==current.get('cleanup_status')=='passed','Incomplete run/owned cleanup')
    need(manifest.get('error') is None and manifest.get('cleanup_error') is None,'Run/cleanup error')
    commands=manifest['commands'];need([c['task']for c in commands]==['kill','infrasetup','runworkload','kill'],'Required four-phase order')
    for index,c in enumerate(commands,1):
        need(c['phase_index']==index and c['status']=='passed' and c['returncode']==0 and c['timed_out'] is False and c['cleanup_phase']==(index==4),'Phase result/cleanup ownership')
        need(type(c['host_elapsed_seconds'])in(int,float) and c['host_elapsed_seconds']>0,'Phase elapsed time')
        for suffix in ('stdout','stderr'):need(ids['job/'+c[suffix+'_path']]==c[suffix+'_sha256'],'Phase raw stream changed')
        actual=c['actual_input_sha256']
        for key,field in [('manager_sha256','prepared_manager_sha256'),('runtime_sha256','execution_runtime_sha256'),('hwdb_sha256','prepared_hwdb_sha256')]:need(actual[key]==manifest[field],'Phase execution input differs')
    need(commands[-1]['host_elapsed_seconds']>=0,'Owned cleanup duration')
    auth=manifest['launch_authorization_receipt'];grant=auth['authorization'];lock=manifest['shared_lock']
    need(grant['authorization_source']=='explicit_current_user_launch_instruction' and grant['operator_or_Ethan_exclusive_reservation_claimed'] is False,'User grant provenance')
    need(lock['path']=='/scratch/firesim/iris-locks/fpga0' and lock['kind']=='exclusive_atomic_directory' and lock['authorization_id']==grant['authorization_id'] and lock['boot_id']==grant['boot_id'] and lock['uid']==grant['uid']==1003,'Shared lock/account/boot ownership')
    need(manifest['authorization_id']==grant['authorization_id'] and bool(manifest['lock_token']),'Launch token/authorization')
    stages={x['stage']:x['report']for x in manifest['safety_inspections']}
    for stage in ('kill','infrasetup','runworkload','cleanup'):
        r=stages[stage];need(r['inspection_complete'] is True and r['inspection_errors']==[] and r['boot_id']==grant['boot_id'] and r['inspection_euid']==0,'Complete trusted phase inspection: '+stage)
    loader=manifest['loader_override']
    need(loader['fesvr_step_size_target_cycles']==128 and loader['target_cycle_bound'] is None and loader['remote_wall_watchdog_seconds']==600 and loader['foreground'] is True and loader['driver_binary_unchanged'] is True,'Loader/watchdog contract')
    return [{'task':c['task'],'host_seconds':c['host_elapsed_seconds'],'status':c['status'],'cleanup_phase':c['cleanup_phase']}for c in commands]


def artifact_identities(manifest,ids):
    out={}
    for field,expected in (('image',IMAGE_SHA),('driver',DRIVER_SHA)):
        info=manifest[field];need(info['sha256']==expected,'Wrong '+field+' artifact SHA')
        uri=urlparse(info['uri']);need(uri.scheme=='file' and uri.netloc=='','Local exact artifact URI required');path=Path(unquote(uri.path))
        need(hash_file(path)==expected,'Changed external '+field+' bytes')
        out[field]={'path':str(path),'sha256':expected,'artifact_bytes_rehashed':True,'loaded_implementation_attested':False}
        if field=='image':
            with tarfile.open(path,'r:gz')as t:
                bits=[x for x in t.getmembers()if x.isfile() and x.name.endswith('/firesim.bit')];need(len(bits)==1,'Unique archived bit artifact')
                h=hashlib.sha256()
                with t.extractfile(bits[0])as f:
                    for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
                need(h.hexdigest()==BIT_SHA,'Wrong image bit artifact');out['bit']={'member':bits[0].name,'sha256':BIT_SHA,'bytes':bits[0].size,'loaded_implementation_attested':False}
        else:need(expected in ids.values(),'Driver bundle missing from captured source inventory')
    return out


def audit(job,output):
    job=Path(job).resolve();output=Path(output).resolve();need(not output.exists() and job!=output and job not in output.parents,'Fresh output outside job required');output.mkdir(parents=True)
    report={'schema':'iris.memory_routes_current_independent_archive_audit.v1','pass':False,'standard_library_only':True,'repository_validator_imports':False,'hardware_contacted':False,'loaded_bit_attested':False,'source_image_association_verified':False,'physical_traffic_or_DRAM_bank_verified':False,'timing_accuracy_certified':False,'auditor_sha256':hash_file(__file__)}
    try:
        current=js((job/'run.json').read_bytes());cap=current['capture']
        need(current.get('cleanup_status')=='passed' and cap.get('status')=='captured' and cap.get('returncode')==0,'Quiescent owned cleanup and completed capture required')
        archive=Path(cap['archive']);need(hash_file(archive)==cap['archive_sha256'],'Archive outer SHA')
        data,ids,total=read_archive(archive,cap['captured_run_manifest_sha256']);m=js(data['job/run.json']);check_role(m)
        lifecycle=check_lifecycle(m,current,ids)
        runtime=data['job/manager/config_runtime.yaml']
        private=m['remote_simulation_dir'];need(private=='/scratch/agustin/firesim/'+m['lock_token'],'Owned private runtime path/token')
        line=('    default_simulation_dir: '+private+'\n').encode()
        need(runtime.count(line)==1,'Unique owned runtime field')
        reconstructed=runtime.replace(line,b'    default_simulation_dir: /scratch/firesim\n',1)
        need(hash_bytes(reconstructed)==m['prepared_runtime_sha256'],'Runtime changed beyond the owned private directory')
        need(ids['job/manager/config_runtime.yaml']==m['execution_runtime_sha256'],'Archived execution runtime hash')
        for name,wanted in m['prepared_file_sha256'].items():
            actual=hash_bytes(reconstructed) if name=='manager/config_runtime.yaml' else ids.get('job/'+name)
            need(actual==wanted,'Prepared file changed: '+name)
        for source,wanted in m['input_sha256'].items():need(wanted in ids.values(),'Captured source input absent: '+source)
        need(ids.get('job/manager/workloads/iris-batch/batch.elf')==m['elf_sha256']==ELF_SHA,'Exact memory ELF')
        need(ids.get('job/corpus.json')==m['corpus_sha256'],'Corpus archive hash')
        ready=js(data['job/ready.json']);need(ids['job/ready.json']==m['ready_sha256'] and ready['elf_sha256']==ELF_SHA,'Ready/ELF binding')
        for name,key in (('build.json','build_sha256'),('readback-layout.json','readback_layout_sha256')):need(ids['job/'+name]==ready[key],'Ready constituent changed')
        corpus=js(data['job/corpus.json']);cases=check_corpus(corpus);compiled=check_elf(data['job/manager/workloads/iris-batch/batch.elf'],cases,js(data['job/readback-layout.json']))
        logs=[name for name in data if name.endswith('/uartlog')];primary=[n for n in logs if n.startswith('job/manager/results-workload/')]
        need(len(primary)==1 and set(logs)<={primary[0],'job/optional-observability/uartlog'},'Unique managed guest UART')
        for name in logs:need(data[name]==data[primary[0]],'Cleanup UART copy differs')
        rows,numeric=check_uart(data[primary[0]],cases);artifacts=artifact_identities(m,ids)
        need(hash_file(archive)==cap['archive_sha256'],'Archive changed while auditing')
        (output/'regions.json').write_text(json.dumps(rows,indent=2)+'\n')
        report.update(pass_=True,archive=str(archive),archive_sha256=cap['archive_sha256'],archived_files=len(ids),archived_bytes_rehashed=total,all_inventory_bytes_verified=True,compiled_elf=compiled,numeric=numeric,guest_uart={'member':primary[0],'sha256':ids[primary[0]],'bytes':len(data[primary[0]])},artifacts=artifacts,lifecycle=lifecycle,source_inputs_verified=len(m['input_sha256']),prepared_files_verified=len(m['prepared_file_sha256']),runtime_transform={'only_change':'default_simulation_dir from /scratch/firesim to owned token path','prepared_sha256':m['prepared_runtime_sha256'],'execution_sha256':m['execution_runtime_sha256'],'prepared_bytes_reconstructed_and_rehashed':True},regions_sha256=hash_file(output/'regions.json'),write_golden_scope='The store kernel returns zero; its reported checksum is a post-ROI sum of64 volatile reads. This validates that aggregate against64*(256*N+hart), not each final RAM word, ordering, physical writes or absence of compensating errors.',fitting_only=True,global_heldout=False)
        report['pass']=report.pop('pass_')
    except (OSError,EOFError,ValueError,KeyError,TypeError,IndexError,struct.error,tarfile.TarError,UnicodeError)as error:report['error']=str(error)
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=audit(a.job,a.output);print(json.dumps({k:r.get(k)for k in ('pass','archived_files','numeric','error')}));return 0 if r['pass']else 1
if __name__=='__main__':raise SystemExit(main())
