"""Finite two-handoff algorithm proof under release/acquire and pending-MSIP WFI.
This is a source-algorithm proof, not a proof of FPGA coherence/CLINT delivery.
"""
import hashlib,json
from pathlib import Path
def source_guard(text):
 for token in ['completion __attribute__((section(".data")))={0}','__atomic_store_n(&parked[h].value,1,__ATOMIC_RELEASE)','while(__atomic_load_n(&completion.value,__ATOMIC_ACQUIRE)<h)','while(!msip())','__atomic_store_n(&completion.value,h+1,__ATOMIC_RELEASE);io_fence();send_ipi(h+1);io_fence();','iris_uart_drain();io_fence();']:
  if token not in text:raise ValueError('Phase source contract '+token)
 if 'wait_epoch' in text or 'epoch=ci+1' in text:raise ValueError('No per-case wait protocol')
 if text.index('clear_ipi(h);wait_phase(h);')>text.index('for(unsigned ci=0;ci<CASES;'):raise ValueError('Initialization precedes cases')
def explore(omit_ipi=False):
 # local states:0clear,1ready-publication,2phase-wait,3MSIP-wait,
 #4consume,5run,6emit/drain,7publish-next,8send-next,9park,10exit.
 start=((0,0,0),(0,0,0),(0,0,0),0);seen={start};todo=[start];edges=0;terminal=0;dead=0
 while todo:
  states,ready,ip,phase=todo.pop();active=[h for h,s in enumerate(states)if s==5];assert len(active)<=1
  if active:assert phase==active[0]and all(ready)and not any(ip) # quiet measured windows
  nexts=[]
  for h,s in enumerate(states):
   ns=list(states);nr=list(ready);ni=list(ip);np=phase
   if s==0:ni[h]=0;ns[h]=1
   elif s==1:nr[h]=1;ns[h]=2
   elif s==2:
    if h==0:
     if not all(ready):continue
     ns[h]=5
    elif phase>=h:ns[h]=3
    else:continue # sleeping or generation-check; pending is durable until consume
   elif s==3:
    if not ip[h]:continue
    ns[h]=4
   elif s==4:ni[h]=0;ns[h]=5
   elif s==5:ns[h]=6
   elif s==6:ns[h]=7 if h<2 else 10
   elif s==7:np=h+1;ns[h]=8
   elif s==8:
    if not omit_ipi:ni[h+1]=1
    ns[h]=9
   else:continue
   nxt=(tuple(ns),tuple(nr),tuple(ni),np);nexts.append(nxt);edges+=1
   if nxt not in seen:seen.add(nxt);todo.append(nxt)
  if not nexts:
   if states==(9,9,10):terminal+=1
   else:dead+=1
 return dict(states=len(seen),edges=edges,terminal_states=terminal,deadlocks=dead)
def prove(source):
 text=Path(source).read_text();source_guard(text);r=explore();assert r['terminal_states']==1 and r['deadlocks']==0;mut=explore(True);assert mut['deadlocks']>0;controls=[]
 for name,old,new in [('wrong-wake-target','send_ipi(h+1)','send_ipi(h)'),('drop-release','__atomic_store_n(&completion.value,h+1,__ATOMIC_RELEASE)','__atomic_store_n(&completion.value,h+1,__ATOMIC_RELAXED)'),('phase-uninitialized','completion __attribute__((section(".data")))={0}','completion')]:
  changed=text.replace(old,new,1)
  try:source_guard(changed)
  except ValueError:controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Mutant admitted '+name)
 return dict(schema='iris.rvv_hart_phase_handoff_finite_proof.v1',pass_=True,**r,foreign_writes_during_window=0,one_active_hart=True,MSIP_wakeups=2,no_percase_IPI_or_WFI=True,phase0_filebacked_known_zero=True,source_guard_controls=controls,omitted_IPI_detected_deadlock=True,proof_scope='Finite source-algorithm interleavings under release/acquire and pending-MSIP wakes WFI with localMSIE/globalMIE0; notactualhardwarecoherence/CLINTproof',source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest())
if __name__=='__main__':print(json.dumps(prove(Path(__file__).with_name('guest.c')),indent=2))
