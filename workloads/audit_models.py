#!/usr/bin/env python3
"""Freeze public config-only model inputs and derive explicit operator/memory facts.

No weights are downloaded, no remote model code is executed, and no model is
claimed supported. TinyLlama stays validation-only under Merlin's claim policy.
"""
from __future__ import annotations
import argparse, ast, concurrent.futures, hashlib, json, subprocess, urllib.error, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/'workloads/sources'
MODELS=[('openai/gpt-oss-20b',False),('openai/gpt-oss-120b',False),
        ('google/gemma-4-E4B-it',False),('google/gemma-4-26B-A4B-it',False),
        ('meta-llama/Llama-2-7b-hf',False),('TinyLlama/TinyLlama-1.1B-Chat-v1.0',True),
        ('TinyLlama/TinyLlama-1.1B-intermediate-step-1431k-3T',True)]
PRIMARY={'openai/gpt-oss-20b','google/gemma-4-E4B-it','meta-llama/Llama-2-7b-hf',
         'TinyLlama/TinyLlama-1.1B-intermediate-step-1431k-3T'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def get(url):
    with urllib.request.urlopen(url,timeout=30) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('refusing oversized metadata; weights must never be fetched')
    return raw

def freeze(item):
    model,heldout=item;out=SOURCES/model.replace('/','--');out.mkdir(parents=True,exist_ok=True)
    record={'model_id':model,'validation_only':heldout,'weights_downloaded':False,'files':{},'unknowns':[]}
    try:
        meta=json.loads(get('https://huggingface.co/api/models/'+model));revision=meta['sha']
        if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):raise ValueError('invalid full revision')
        record['revision']=revision
    except Exception as error:
        record['unknowns'].append('model revision unavailable: '+str(error));return record
    files=['config.json','model.safetensors.index.json']
    if model.startswith('openai/gpt-oss-'):files.append('original/config.json')
    for name in files:
        url='https://huggingface.co/'+model+'/resolve/'+revision+'/'+name
        try:
            raw=get(url);json.loads(raw);path=out/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            record['files'][name]={'path':str(path.relative_to(ROOT)),'sha256':sha(path),'url':url}
        except Exception as error:record['unknowns'].append(name+' unavailable: '+str(error))
    return record

def implementation_sources():
    records={}
    files={'transformers':['src/transformers/models/gemma4/modeling_gemma4.py','src/transformers/models/gemma4/configuration_gemma4.py'],
           'gpt-oss':['gpt_oss/torch/model.py'], 'meta-llama':['llama/model.py','README.md']}
    for name,members in files.items():
        repo=ROOT/'third_party'/name
        commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
        if subprocess.check_output(['git','-C',str(repo),'diff','--binary','HEAD']):raise ValueError('implementation checkout dirty: '+name)
        records[name]={'commit':commit,'files':{member:{'path':str((repo/member).relative_to(ROOT)),'sha256':sha(repo/member)} for member in members}}
    return records

def derive(record):
    result={**record,'operator_cases':[],'model_execution_qualified':False,'numeric_policy_qualified':False}
    result['selection']='primary-user-selected' if record['model_id'] in PRIMARY else 'exploratory-only'
    if 'config.json' not in record['files']:
        result['status']='unknown-config-refused'
        if record['model_id']=='meta-llama/Llama-2-7b-hf':
            source=ROOT/'third_party/meta-llama/llama/model.py'
            cls=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='ModelArgs')
            defaults={n.target.id:ast.literal_eval(n.value) for n in cls.body if isinstance(n,ast.AnnAssign) and n.value is not None}
            h,layers,heads,multiple=(defaults[k] for k in ('dim','n_layers','n_heads','multiple_of'))
            intermediate=((2*(4*h)//3+multiple-1)//multiple)*multiple
            result['provisional_reference_defaults']={'hidden_size':h,'layers':layers,'heads':heads,'head_dim':h//heads,
                'intermediate_size':intermediate,'vocab_size':None,'source_sha256':sha(source),
                'source_lines':[[20,31],[200,207],[330,343],[376,381]],
                'scope':'User-authorized official Meta reference defaults; exact gated checkpoint config remains unknown'}
            for m in [1,8,32,64]:
                for role,n,k in [('q',h,h),('k',h,h),('v',h,h),('o',h,h),('mlp.gate',intermediate,h),('mlp.up',intermediate,h),('mlp.down',h,intermediate)]:
                    result['operator_cases'].append({'role':role,'shape_mnk':[m,n,k],'fit_eligible':False,'executed':False,
                        'scope':'provisional reference-default shape, not exact checkpoint admission','source_sha256':sha(source)})
            result['status']='provisional-reference-defaults-exact-config-refused'
        return result
    source=ROOT/record['files']['config.json']['path'];config=json.loads(source.read_text());c=config.get('text_config',config)
    ptr='/text_config/' if 'text_config' in config else '/'
    wanted=['model_type','hidden_size','intermediate_size','num_hidden_layers','num_attention_heads','num_key_value_heads','head_dim',
            'global_head_dim','num_global_key_value_heads','num_local_experts','num_experts','num_experts_per_tok','top_k_experts',
            'moe_intermediate_size','hidden_size_per_layer_input','vocab_size_per_layer_input','vocab_size','num_kv_shared_layers',
            'layer_types','sliding_window','enable_moe_block','attention_k_eq_v','use_double_wide_mlp','hidden_act','hidden_activation','swiglu_limit','rope_scaling','rope_parameters']
    result['facts']={key:{'value':c[key],'json_pointer':ptr+key,'source_sha256':sha(source)} for key in wanted if key in c}
    result['checkpoint_quantization']=config.get('quantization_config')
    if 'original/config.json' in record['files']:
        original=json.loads((ROOT/record['files']['original/config.json']['path']).read_text())
        fields={'hidden_size':'hidden_size','intermediate_size':'intermediate_size','num_hidden_layers':'num_hidden_layers',
                'num_local_experts':'num_experts','num_attention_heads':'num_attention_heads','num_key_value_heads':'num_key_value_heads','head_dim':'head_dim'}
        checks={a:c[a]==original[b] for a,b in fields.items()}
        if not all(checks.values()):raise ValueError('independent original/Transformers configs disagree')
        result['independent_original_config_crosscheck']=checks
    if 'model.safetensors.index.json' in record['files']:
        index=json.loads((ROOT/record['files']['model.safetensors.index.json']['path']).read_text())
        result['checkpoint_payload_bytes']=index.get('metadata',{}).get('total_size')
    else:result['checkpoint_payload_bytes']=None
    if record['validation_only']:
        result['status']='validation-only-no-corpus-derivation'
        result['operator_cases']=[]
        result['memory_residency_qualified']=False
        return result
    h,i,layers,heads,kv=(c[key] for key in ['hidden_size','intermediate_size','num_hidden_layers','num_attention_heads','num_key_value_heads'])
    dim=c.get('head_dim')
    if dim is None:
        if h%heads:raise ValueError('cannot derive exact head width')
        dim=h//heads
    variants=[('attention',dim,kv)]
    if c.get('global_head_dim'):
        variants=[('sliding_attention',dim,kv),('full_attention',c['global_head_dim'],c.get('num_global_key_value_heads') or kv)]
    roles=[]
    for kind,width,nkv in variants:
        roles.extend([(kind+'.q',heads*width,h),(kind+'.k',nkv*width,h),(kind+'.o',h,heads*width)])
        if not (kind=='full_attention' and c.get('attention_k_eq_v')):
            roles.append((kind+'.v',nkv*width,h))
    experts=c.get('num_local_experts') or c.get('num_experts')
    expert_i=c.get('moe_intermediate_size') or i
    if not experts or c['model_type']=='gemma4_text':
        roles.extend([('mlp.gate',i,h),('mlp.up',i,h),('mlp.down',h,i)])
    if experts:
        roles.extend([('router',experts,h),('expert.gate',expert_i,h),('expert.up',expert_i,h),('expert.down',h,expert_i)])
    if c.get('hidden_size_per_layer_input'):
        p=c['hidden_size_per_layer_input'];roles.extend([('ple.model_projection',layers*p,h),('ple.gate',p,h),('ple.output_projection',h,p)])
    for m in [1,8,32,64]:
        for role,n,k in roles:
            result['operator_cases'].append({'role':role,'shape_mnk':[m,n,k],'dtype_policy':'unqualified W8A8 proposal',
                'source_config_sha256':sha(source),'fit_eligible':record['model_id'] in PRIMARY,'executed':False,
                'scope':'source-derived operator shape; no checkpoint values or measured shape frequencies'})
    # Matrix-storage lower bounds only, independently corroborated by the frozen implementation shapes.
    if experts:
        base=layers*3*experts*h*expert_i
        formula='layers * experts * (2*intermediate*hidden + hidden*intermediate)'
        implementation='gpt-oss/gpt_oss/torch/model.py:275-301' if c['model_type']=='gpt_oss' else 'transformers/modeling_gemma4.py:1262-1273'
    else:
        base=layers*3*h*i
        formula='layers * (2*hidden*intermediate + intermediate*hidden)'
        implementation='transformers/modeling_gemma4.py:1059-1074'
        if c.get('hidden_size_per_layer_input'):
            base+=c['vocab_size_per_layer_input']*layers*c['hidden_size_per_layer_input']
            formula+=' + vocab_per_layer * layers * hidden_per_layer'
            implementation+='; modeling_gemma4.py:1571-1585'
    result['selected_matrix_storage_lower_bound']={'parameters':base,'int8_bytes':base,'fp8_bytes':base,'bf16_bytes':2*base,
        'formula':formula,'implementation_evidence':implementation,'excludes':'attention/normalization/biases/scales/embedding/vision/audio unless formula names them',
        'int8_exceeds_physical_dram':base>4*(1<<30),'native_checkpoint_dtype':c.get('dtype',config.get('torch_dtype'))}
    result['architecture_caveats']=['These shape cases are not full-model captures or a certified quantization policy.']
    if c['model_type']=='gpt_oss':result['architecture_caveats']+=['Native checkpoint MXFP4 must not be interpreted as Iris FP8. Unpack/dequantize/requantize needs an explicit checked software policy.', 'Actual expert loads/routing and sliding/full attention remain data-dependent.']
    if c['model_type']=='gemma4_text':result['architecture_caveats']+=['Full attention has a different head width; KV reuse removes some k/v projections. The cases are role coverage, not per-layer execution counts.', 'KV allocation with shared full-length/sliding states needs actual runtime ownership accounting; no cache-fit claim follows from a naive layers*heads product.']
    result['memory_residency_qualified']=False;result['status']='operator-shapes-only'
    result['required_nonmatmul_coverage']=[{'operator':name,'executed':False,'compiler_qualified':False} for name in
       ['embedding_gather','RMSNorm','rotary_position_embedding','masked_softmax','residual_add',
        c.get('hidden_activation',c.get('hidden_act','activation_unknown')),'activation_product','quantize_dequantize','logits_argmax']+
       (['router_softmax','topk','expert_dispatch_compact','expert_gather_weighted_combine'] if experts else [])+
       (['per_layer_embedding_gather','per_layer_gate_and_residual'] if c.get('hidden_size_per_layer_input') else [])]
    return result

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--refresh',action='store_true');p.add_argument('--verify',action='store_true');a=p.parse_args()
    frozen=ROOT/'workloads/model-inputs.json'
    if a.refresh:
        with concurrent.futures.ThreadPoolExecutor(7) as pool:records=list(pool.map(freeze,MODELS))
        manifest={'schema':'iris.model_inputs.v1','models':records,'implementations':implementation_sources(),'merlin_commit':'d56133b168bbee3d73cb8b4304d3622d4191fc6a',
                  'claim_policy':{'path':'integration/merlin/merlin/contract/claim_models.yaml','sha256':sha(ROOT/'integration/merlin/merlin/contract/claim_models.yaml')},'weights_downloaded':False}
        frozen.write_text(json.dumps(manifest,indent=2)+'\n')
    manifest=json.loads(frozen.read_text())
    for model in manifest['models']:
        for file in model['files'].values():
            if sha(ROOT/file['path'])!=file['sha256']:raise ValueError('frozen config changed')
    if implementation_sources()!=manifest['implementations']:raise ValueError('implementation source identity changed')
    if sha(ROOT/manifest['claim_policy']['path'])!=manifest['claim_policy']['sha256']:raise ValueError('claim policy changed')
    output={'schema':'iris.operator_coverage_plan.v1','input_manifest_sha256':sha(frozen),'models':[derive(row) for row in manifest['models']],
            'streaming_contract':{'physical_dram_bytes':4*(1<<30),'hardware_manifest_sha256':sha(ROOT/'hardware/manifest.json'),
                'reserve_bytes_policy':256*(1<<20),'weight_panel_bytes_policy':64*(1<<20),'double_buffer_weight_panels':True,
                'kv_bytes':None,'serial_latency_cycles':None,'bandwidth_bytes_per_cycle':None,'fits_qualified':False,
                'rules':['Count code/OS/stacks/heap/activations/KV/scales and both resident panels before admission.',
                         'Treat the 4GiB physical window separately from the Zephyr linked-image relocation limit.',
                         'Stream only requested weight/expert panels through an explicit bounded transport with completion/fence ownership.',
                         'Run CPU/RVV producer on hart2; VME tasks stay0/1 under explicit context setup. Benchmark competing CPU compute as a separate placement.',
                         'Do not simulate a tensor as silently backed RAM outside real mappings.',
                         'Report cold/miss/streaming paths separately; unknown transport latency/bandwidth prevents calibrated cycle estimates.']},
            'calibration_status':'unfitted; TinyLlama excluded from fitting and corpus derivation','full_model_execution_qualified':False}
    out=ROOT/'workloads/operator-coverage.json'
    text=json.dumps(output,indent=2)+'\n'
    if a.verify:
        if out.read_text()!=text:raise ValueError('derived operator plan is stale')
    else:out.write_text(text)
    print(json.dumps({'models':len(output['models']),'operator_cases':sum(len(m['operator_cases']) for m in output['models']),'weights_downloaded':False,'full_model_qualified':False}))
if __name__=='__main__':main()
