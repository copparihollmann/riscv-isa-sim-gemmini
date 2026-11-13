"""Attribute causally owned source observations without inventing occupancy."""
import bisect
import collections
import math


CONTROL={'EX_candidate','EX_fire','MEM_kill','IFC_owner_transfer','PFC_front_permission'}
SCRUB={'VRF_scrub_accept','VRF_scrub_commit'}
WRITES={'VRF_scrub_commit','VRF_bank_commit','MRF_zero_commit','MRF_mvin_commit',
        'MRF_INT8_commit','MRF_FP8_commit'}


def integer(value,label,upper=2**64):
    if type(value)is not int or not 0<=value<upper:
        raise ValueError('Invalid unsigned '+label)
    return value


def profile(rows,instructions,symbols,clock_hz,expected_counts):
    """One continuous source replay; expected counts come from its frozen proof.

    Caller node labels are never interpreted as native graph IDs. Write masks
    count physical write enables, and never initialize numeric state.
    """
    if not math.isfinite(clock_hz)or clock_hz<=0:
        raise ValueError('Explicit source timebase required')
    if set(expected_counts)!={0,1,2}:
        raise ValueError('All three source harts and independent counts required')
    starts=[s[0]for s in symbols]
    owners={};accepted=set();actual={h:collections.Counter()for h in range(3)}
    functions={};points={};pending={};transactions=[]
    previous=-1;edges={h:-1 for h in range(3)};first=None;last=None

    def function(pc):
        if pc is None:return None,None
        index=bisect.bisect_right(starts,pc)-1
        return (symbols[index][2],symbols[index][0])if index>=0 and pc<symbols[index][1]else(None,None)

    for row in rows:
        kind,source=row.get('kind'),row.get('source')
        if not isinstance(kind,str)or not kind or not isinstance(source,str)or not source:
            raise ValueError('Exact source event kind and signal required')
        hart=integer(row.get('hart'),'hart',3);tick=integer(row.get('tb'),'source timestamp')
        edge=integer(row.get('source_edge'),'source edge');amount=integer(row.get('amount'),'source amount')
        if tick<previous or edge<edges[hart]:raise ValueError('Nonmonotonic source events')
        previous=tick;edges[hart]=edge;first=tick if first is None else first;last=tick
        actual[hart][kind]+=1
        command=row.get('command');key=None;pc=None
        if command is not None:
            epoch=integer(command.get('reset_epoch'),'reset epoch')
            sequence=integer(command.get('sequence'),'command sequence')
            ex_edge=integer(command.get('EX_edge'),'command EX edge')
            pc=integer(command.get('pc'),'command PC')
            raw=integer(command.get('instruction'),'command instruction',2**32)
            if command.get('pc_known')is not True or type(command.get('EX_fired'))is not bool:
                raise ValueError('Known physical command identity required')
            if ex_edge>edge:raise ValueError('Physical work precedes its command')
            if instructions.read(pc)!=raw:raise ValueError('Physical instruction does not match bound executable')
            key=(hart,epoch,sequence)
            identity=(pc,raw,ex_edge,command['EX_fired'],command.get('caller_node'))
            if key in owners and owners[key]!=identity:
                raise ValueError('Command generation changed physical identity')
            owners[key]=identity
            if kind=='frontend_issue_accept':
                if key in accepted or command['EX_fired']is not True:
                    raise ValueError('Duplicate or unfired frontend acceptance')
                accepted.add(key)
            if kind not in CONTROL and key not in accepted:
                raise ValueError('Physical work lacks accepted command generation')
        elif kind not in SCRUB:
            raise ValueError('Non-scrub physical observation lacks causal command')
        name,address=function(pc);fkey=(hart,name,address)
        group=functions.setdefault(fkey,{'hart':hart,'function':name,'symbol_address':address,
            'kind_counts':collections.Counter(),'source_amount_totals_by_kind':collections.Counter(),
            'declared_bytes_by_kind':collections.Counter(),'write_enable_bits_by_kind':collections.Counter(),
            'accepted_commands':0,'source_signals':set()})
        group['kind_counts'][kind]+=1;group['source_amount_totals_by_kind'][kind]+=amount
        group['source_signals'].add(source)
        if kind=='frontend_issue_accept':group['accepted_commands']+=1
        written=0
        if 'bit_mask'in row:
            mask=row['bit_mask']
            if not isinstance(mask,list)or not mask:raise ValueError('Physical mask words required')
            written=sum(bin(integer(word,'physical write mask')).count('1')for word in mask)
            if 'data_words'in row:
                if not isinstance(row['data_words'],list)or len(row['data_words'])!=len(mask):
                    raise ValueError('Physical data/mask shape mismatch')
                for word in row['data_words']:integer(word,'raw data word')
            if kind in WRITES:group['write_enable_bits_by_kind'][kind]+=written
        if 'bytes'in row:
            group['declared_bytes_by_kind'][kind]+=integer(row['bytes'],'declared transaction bytes')
        point_key=(hart,tick,kind,key)
        point=points.setdefault(point_key,{'kind':kind,'hart':hart,'tb':tick,'source_edge':edge,
            'function':name,'symbol_address':address,'pc':pc,'command_key':key,
            'observations':0,'source_amount_total':0,'physical_write_enable_bits':0,'source_signals':set()})
        point['observations']+=1;point['source_amount_total']+=amount
        point['physical_write_enable_bits']+=written if kind in WRITES else 0;point['source_signals'].add(source)
        if kind in ('TL_transaction_accept','TL_transaction_complete'):
            transaction=integer(row.get('transaction'),'physical transaction')
            if key is None:raise ValueError('TL transaction lacks owner')
            token=(hart,key[1],transaction)
            details=(key,integer(row.get('address'),'transaction address'),
                integer(row.get('bytes'),'transaction bytes'),integer(row.get('transport_source'),'TL source ID'),
                integer(row.get('memory_tag'),'memory tag'))
            if kind=='TL_transaction_accept':
                if token in pending:raise ValueError('Duplicate live physical transaction')
                pending[token]=(tick,edge,details,name,address)
            else:
                if token not in pending:raise ValueError('Unmatched physical response')
                begin,begin_edge,original,owner_name,owner_address=pending.pop(token)
                if details!=original or tick<begin or edge<begin_edge:
                    raise ValueError('Physical response changed owner, payload or source')
                transactions.append({'hart':hart,'transaction':transaction,'reset_epoch':key[1],
                    'command_sequence':key[2],'pc':pc,'function':owner_name,'symbol_address':owner_address,
                    'start_tb':begin,'end_tb':tick,'elapsed_TB_ticks':tick-begin,
                    'elapsed_source_edges':edge-begin_edge,'address':details[1],
                    'declared_transaction_bytes':details[2],'transport_source':details[3],
                    'boundary':'Saturn auto_atl_out A acceptance to matching final D acceptance'})
    if actual!={h:collections.Counter(expected_counts[h])for h in range(3)}:
        raise ValueError('Complete source event counts differ from independently frozen proof')
    function_rows=[]
    for key,group in sorted(functions.items(),key=lambda item:(item[0][0],item[0][2]if item[0][2]is not None else -1,item[0][1]or'')):
        group['source_signals']=sorted(group['source_signals']);function_rows.append(group)
    traces=[]
    for point in points.values():
        point['source_signals']=sorted(point['source_signals'])
        traces.append({'name':point['kind'],'ph':'i','s':'t','cat':'owned physical source edge',
            'pid':point['hart'],'tid':point['kind'],'ts':point['tb']*1e6/clock_hz,'args':point})
    for span in transactions:
        traces.append({'name':'owned TL transaction','ph':'X','cat':'source transport lifetime',
            'pid':span['hart'],'tid':'Saturn auto_atl_out transactions','ts':span['start_tb']*1e6/clock_hz,
            'dur':span['elapsed_TB_ticks']*1e6/clock_hz,'args':span})
    summary={'schema':'iris.saturn_owned_point_profile.v1','source_clock_hz':clock_hz,
        'source_observation_span_TB':[first,last],'functions':function_rows,
        'event_counts_by_hart':actual,'aggregated_point_groups':len(points),
        'transport_transactions':transactions,'pending_transport_transactions':len(pending),
        'caller_node_policy':'Opaque producer metadata; not interpreted as a native CPU graph ID.',
        'numeric_policy':'Raw payloads/write masks are not used to initialize or certify architectural values.',
        'counting_policy':'Kinds are separate physical observations; summing stages double-counts the same command/payload. Amount units remain source-kind-specific.',
        'transport_policy':'Elapsed source-boundary lifetime includes all downstream delays; it is neither pure DRAM latency nor attributed contention wait. Declared transaction bytes are not application bytes.',
        'occupancy':None,'retired_instructions':None,'stall_breakdown':None,'roofline':None,
        'whole_SoC_or_FPGA_or_2percent_certified':False}
    return summary,{'traceEvents':traces,'displayTimeUnit':'ns','metadata':{
        'source_clock_hz':clock_hz,'point_work_has_no_invented_duration':True,'hardware_certified':False}}
