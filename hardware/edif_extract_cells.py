#!/usr/bin/env python3
"""Extract complete named cell definitions from a digest-bound decoded EDIF."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time

from checkpoint_edif import digest
from edif_ram_audit import delta,expression,name,identifier as definition_identifier


def extract(receipt,expected,prefixes,output):
    if output.exists()or not prefixes:raise ValueError('Fresh output and explicit cell prefixes required')
    if digest(receipt)!=expected:raise ValueError('Pinned complete decode receipt required')
    decoded=json.loads(receipt.read_text())
    if decoded.get('status')!='decoded_text_and_lexical_balance_verified':raise ValueError('Complete verified netlist required')
    started=time.monotonic();output.mkdir(parents=True)
    sha=hashlib.sha256();library=None;pending=None;records=[]
    with(receipt.parent/'netlist.edf').open('rb')as source:
        for line_number,raw in enumerate(source,1):
            sha.update(raw);line=raw.decode('utf-8');head=line.lstrip();keyword=head[:12].lower()
            if pending is not None:
                pending['raw'].append(raw);pending['depth']+=delta(line)
                if pending['depth']<0:raise ValueError('Cell expression overclosed')
                if pending['depth']==0:
                    data=b''.join(pending.pop('raw'));cell=expression(data.decode())
                    if cell[0]!='cell'or definition_identifier(cell[1])[0]!=pending['name']:
                        raise ValueError('Invalid selected cell')
                    filename=pending['library']+'__'+pending['name']+'.edf'
                    if not re.fullmatch('[A-Za-z0-9_.-]+',filename):raise ValueError('Unsafe cell output name')
                    (output/filename).write_bytes(data)
                    records.append({'library':pending['library'],'name':pending['name'],'file':filename,
                        'start_line':pending['start_line'],'end_line':line_number,'bytes':len(data),
                        'sha256':hashlib.sha256(data).hexdigest()});pending=None
                continue
            if keyword.startswith('(library ')or keyword.startswith('(external '):library=name(head.split(' ',1)[1])[0]
            elif keyword.startswith('(cell '):
                identifier=name(head[len('(cell '):])[0]
                if any(identifier.startswith(prefix)for prefix in prefixes):
                    if library is None:raise ValueError('Cell outside library')
                    pending={'library':library,'name':identifier,'start_line':line_number,'raw':[raw],'depth':delta(line)}
                    if pending['depth']<=0:raise ValueError('Selected inline-cell format is not yet supported')
    if pending is not None or not records:raise ValueError('Missing or incomplete selected cells')
    if sha.hexdigest()!=decoded['decoded_edif_sha256']or digest(receipt)!=expected:raise ValueError('Source netlist changed')
    report={'schema':'iris.complete_selected_edif_cells.v1','pass':True,'records':records,'source_edif_sha256':sha.hexdigest(),
        'decode_receipt_sha256':expected,'source_sha256':digest(Path(__file__)),'parser_sha256':digest(Path(__file__).with_name('edif_ram_audit.py')),
        'prefixes':prefixes,'host_seconds':time.monotonic()-started,'hardware_contacted':False,'INIT_certified':False}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'cells':len(records),'host_seconds':report['host_seconds']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--decode-receipt',type=Path,required=True)
    p.add_argument('--sha256',required=True);p.add_argument('--cell-prefix',action='append',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    extract(a.decode_receipt.resolve(),a.sha256,a.cell_prefix,a.output.resolve())
