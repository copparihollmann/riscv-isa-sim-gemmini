// NEW conditional physical producer fixture, never an executed native ELF.
#define main old_source_scalar_write_fixture_not_called
#include "shuttle_memory_system_write_v1.cpp"
#undef main
#include "saturn_storefront_v1.hpp"
#include "rvv_memory_fabric_boundary_v1.hpp"
namespace T=iris::saturn_storefront;
namespace U=iris::rvv_memory_boundary_v1;
namespace {
bool omit_preparation=false,wrong_D_source=false,wrong_read_data=false,undefined_backing=false,wrong_write_data=false,write_corrupted=false;
constexpr unsigned fragments=64,arena_bytes=fragments*16,clean_lines=15;
constexpr std::uint64_t arena_base(unsigned hart){return 0x80020000ULL+hart*4096;}
std::uint64_t fragment_address(unsigned h,unsigned fragment){return arena_base(h)+(fragment/4)*0x20000+(fragment%4)*16;}
std::uint64_t clean_address(unsigned h,unsigned line){return arena_base(h)+(16+line)*0x20000;}
unsigned dense_offset(unsigned h,std::uint64_t address){const auto delta=address-arena_base(h),line=delta/0x20000,byte=delta%0x20000;need(line<16&&byte<64,"source conflict-line physical address mapping");return line*64+byte;}
unsigned writer_at(std::uint64_t address){const auto within=(address-arena_base(0))%0x20000;need(within<64||(within>=4096&&within<4160),"source arena writer domain");return within>=4096;}
std::vector<T::Domain>source_domains(){std::vector<T::Domain>domains;for(unsigned h=0;h<2;++h)for(unsigned n=0;n<16+clean_lines;++n)domains.push_back({arena_base(h)+n*0x20000,64});return domains;}
std::uint8_t golden(unsigned hart,unsigned offset){return std::uint8_t(0x51+67*hart+13*(offset%64)+29*(offset/64));}
struct Request {T::Owner owner;std::uint64_t address;unsigned ordinal;std::array<std::uint8_t,16>data;};
struct Client {
  std::unique_ptr<T::Model>transport;
  std::vector<T::Input>in;T::Outputs out;
  U::ComputeStoreRob rob;U::StoreOwners owners;
  U::RobOutput rob_out{};
  std::deque<Request>request_q;
  std::deque<unsigned>reservation_order;
  std::array<std::optional<T::Owner>,16>metadata;
  std::array<bool,arena_bytes>prepared_bytes{};
  unsigned reserved=0,released=0,read_sent=0,read_done=0;
  bool read_accepted=false;
  std::optional<T::Owner>read_owner;
  std::array<std::uint64_t,4>events{};
  explicit Client(unsigned h,unsigned seed):transport(std::make_unique<T::Model>(h,seed,std::vector<std::string>{},T::Calendar{2,0},source_domains())),owners(h){for(auto f:transport->input_fields())in.push_back(T::concrete(f.width));}
  void set(const char*n,std::uint64_t v){in[transport->input_index(n)].value.limbs[0]=v;}
  std::uint64_t get(const char*n)const{return out.words[transport->output_index(n)].limbs[0];}
};
struct Arena {
  Fixture f;
  std::array<std::unique_ptr<Client>,2>clients;
  enum Stage{Idle,Preparation,CleanEviction,Readback}stage=Idle;
  std::uint64_t vm_requests=0,physical_A=0,physical_D=0,vm_responses=0,checked_bytes=0,clean_checked_bytes=0;
  unsigned checkpoint_quiet=0;
  explicit Arena(unsigned seed):f(seed){
    // Immutable initial external backing, not a CPU write or cache seeding.
    // All additional line bytes are explicit; uninitialized lines stay unknown.
    for(unsigned h=0;h<2;++h)for(unsigned line=0;line<clean_lines;++line){const auto address=clean_address(h,line);std::vector<B::Byte>bytes;for(unsigned n=0;n<64;++n)bytes.push_back({std::uint8_t(pattern((address+n)&~std::uint64_t(7))>>(8*((address+n)&7))),255});f.service.initialize(address,bytes);}
    if(undefined_backing){const std::array<B::Byte,1>unknown{{{0,0}}};f.service.initialize(arena_base(0),unknown);}
    for(unsigned h=0;h<2;++h)clients[h]=std::make_unique<Client>(h,seed+31+h);
  }
  void stimulus(){for(unsigned h=0;h<2;++h){auto&c=*clients[h];c.set("reset",f.reset);c.set("io_vec_store_req_valid",!f.reset&&!c.request_q.empty());if(!c.request_q.empty()){const auto&q=c.request_q.front();c.set("io_vec_store_req_bits_addr",q.address);c.set("io_vec_store_req_bits_tag",q.owner.tag);c.set("io_vec_store_req_bits_mask",65535);auto&value=c.in[c.transport->input_index("io_vec_store_req_bits_data")].value;value={};for(unsigned n=0;n<16;++n)value.limbs[n/8]|=std::uint64_t(q.data[n])<<(8*(n%8));}
      const bool reading=stage==Readback||stage==CleanEviction;const unsigned read_goal=stage==CleanEviction?clean_lines:2*fragments;const bool offer=reading&&!c.read_owner&&c.read_sent<read_goal;
      if(offer){const auto ordinal=c.read_sent;const unsigned writer=ordinal<fragments?h:1-h,index=ordinal%fragments;const unsigned tag=ordinal%16;const bool clean=stage==CleanEviction;c.read_owner=T::Owner{h,tag,c.transport->reset_epoch(),clean?100u:200+ordinal/fragments,clean?1u:2+ordinal/16,0x80002000+4*ordinal,0x02056007};c.read_accepted=false;c.set("io_vec_load_req_bits_addr",clean?clean_address(h,ordinal):fragment_address(writer,index));c.set("io_vec_load_req_bits_tag",tag);}
      c.set("io_vec_load_req_valid",reading&&bool(c.read_owner)&&!c.read_accepted);}}
  void evaluate(){
    stimulus();
    for(unsigned iteration=0;iteration<32;++iteration){
      auto old_system=f.out;bool changed=false;
      for(unsigned h=0;h<2;++h){auto&c=*clients[h];auto previous=c.out.words;c.transport->evaluate_control(c.in,c.read_owner,c.request_q.empty()?std::nullopt:std::optional<T::Owner>(c.request_q.front().owner));c.out=c.transport->sample();changed|=previous!=c.out.words;const auto tile="shuttle"+std::to_string(h)+"_tile";
        for(const auto*field:{"a_valid","a_bits_opcode","a_bits_param","a_bits_size","a_bits_source","a_bits_address","a_bits_mask","a_bits_data","a_bits_corrupt","d_ready"}){const auto&value=c.out.words[c.transport->output_index("auto_atl_out_"+std::string(field))];f.in[f.ii(tile,"_vector_unit_auto_atl_out_"+std::string(field))].value.limbs=value.limbs;}}
      f.evaluate();changed|=old_system!=f.out;
      for(unsigned h=0;h<2;++h){auto&c=*clients[h];const auto tile="shuttle"+std::to_string(h)+"_tile";for(const auto*field:{"a_ready","d_valid","d_bits_opcode","d_bits_param","d_bits_size","d_bits_source","d_bits_sink","d_bits_denied","d_bits_data","d_bits_corrupt"}){auto value=f.out[f.oi(tile,"_tcm_adjuster_2_auto_in_"+std::string(field))];if(f.reset&&std::string(field)=="d_valid")value=P::Bits(0);if(wrong_D_source&&!f.reset&&std::string(field)=="d_bits_source")value=P::Bits(31);if(wrong_read_data&&stage==Readback&&std::string(field)=="d_bits_data")value.limbs[0]^=1;auto&input=c.in[c.transport->input_index("auto_atl_out_"+std::string(field))];changed|=input.value.limbs!=value.limbs;input.value.limbs=value.limbs;}}
      if(!changed){if(wrong_write_data&&!write_corrupted&&f.bin.w_valid.value&&f.bout.w_ready){auto corrupted=f.bin;corrupted.w.data.value^=1;f.service.evaluate(corrupted);f.bout=f.service.sample();write_corrupted=true;}return;}
    }throw std::runtime_error("source storefront/System/backing global fixed point");
  }
  void step(){
    evaluate();const bool edge=f.tick%2==0;
    if(edge)for(unsigned h=0;h<2;++h){auto&c=*clients[h];c.transport->prepare(f.tick);const unsigned goal=fragments-(omit_preparation&&h==0?1:0);const bool reserve=stage==Preparation&&c.reserved<goal&&c.request_q.size()<2&&c.reserved/4<=c.released/4;const bool ack=!f.reset&&c.get("io_vec_store_ack_valid");c.rob.evaluate({f.reset,reserve,ack,unsigned(c.get("io_vec_store_ack_bits_tag")),!c.reservation_order.empty(),true});c.rob_out=c.rob.sample();}
    f.ar+=!f.reset&&f.bin.ar_valid.value&&f.bout.ar_ready;f.aw+=!f.reset&&f.bin.aw_valid.value&&f.bout.aw_ready;f.w+=!f.reset&&f.bin.w_valid.value&&f.bout.w_ready;f.r+=!f.reset&&f.bout.r_valid&&f.bin.r_ready.value;f.b+=!f.reset&&f.bout.b_valid&&f.bin.b_ready.value;
    // Every selected peer consumes the same settled preedge pins. No peer is
    // evaluated after the first commit; transport receipts are postcommit only.
    f.system.commit({edge,edge,true,f.tick%10==0});f.service.commit();
    if(edge)for(unsigned h=0;h<2;++h){auto&c=*clients[h];c.transport->commit();c.rob.commit();for(const auto&e:c.transport->last_receipts()){
        need(e.owner.hart==h&&e.master_tick==f.tick&&e.source_edge+1==c.transport->committed_source_edges()&&e.master_tick==2*e.source_edge,"actual source owner/calendar receipt");++c.events[unsigned(e.phase)];
        if(e.phase==T::Phase::VMURequest){++vm_requests;if(!e.load){need(!c.request_q.empty()&&c.request_q.front().owner==e.owner,"actual VMU request identity/q ownership");c.request_q.pop_front();}else{need(c.read_owner&&*c.read_owner==e.owner,"actual load request identity");++c.read_sent;c.read_accepted=true;}}
        if(e.phase==T::Phase::TileA){++physical_A;if(!e.load)c.owners.accept_A(e.owner.tag,e.owner.generation);}
        if(e.phase==T::Phase::TileD){++physical_D;if(!e.load){auto owner=c.owners.ack(e.source,false,false,true);need(owner.generation==e.owner.generation&&owner.command==e.owner.command,"actual D immutable source generation");}}
        if(e.phase==T::Phase::VMUResponse){++vm_responses;if(!e.load){need(c.metadata[e.owner.tag]&&*c.metadata[e.owner.tag]==e.owner,"VMU response immutable reserved owner");const auto offset=dense_offset(h,e.address);need(offset+16<=arena_bytes,"prepared arena byte domain");for(unsigned n=0;n<16;++n){need(e.known[n]==255&&e.data[n]==golden(h,offset+n),"actual prepared payload changed");c.prepared_bytes[offset+n]=true;}}else{need(c.read_owner&&*c.read_owner==e.owner,"actual returned load owner");if(stage==CleanEviction){for(unsigned n=0;n<16;++n){const auto a=e.address+n;need(e.known[n]==255&&e.data[n]==std::uint8_t(pattern(a&~std::uint64_t(7))>>(8*(a&7))),"actual source clean-conflict immutable backing golden");++clean_checked_bytes;}}else{const unsigned writer=writer_at(e.address);const auto offset=dense_offset(writer,e.address);for(unsigned n=0;n<16;++n){need(e.known[n]==255&&e.data[n]==golden(writer,offset+n),"actual System source load independently prepared-byte golden");++checked_bytes;}}++c.read_done;c.read_owner.reset();}}
      }
      if(c.rob_out.deq_fire){need(!c.reservation_order.empty(),"ROB dequeue without reserved SIFQ owner");const auto tag=c.reservation_order.front();auto owner=c.owners.retire(tag);need(c.metadata[tag]&&c.metadata[tag]->generation==owner.generation,"ordered SIFQ generation release");c.metadata[tag].reset();c.reservation_order.pop_front();++c.released;}
      if(c.rob_out.reserve_fire){const unsigned tag=c.rob_out.reserve_tag,ordinal=c.reserved;auto owner=c.owners.reserve(tag,1+ordinal/4,16);unsigned index=ordinal;if(omit_preparation&&h==0&&index>=7)++index;need(index<fragments+(omit_preparation?1u:0u),"finite preparation source index");Request request;request.owner={h,tag,c.transport->reset_epoch(),owner.command,owner.generation,0x80001000+4*owner.command,0x02056027};request.address=fragment_address(h,index);request.ordinal=ordinal;for(unsigned n=0;n<16;++n)request.data[n]=golden(h,16*index+n);c.metadata[tag]=request.owner;c.reservation_order.push_back(tag);c.request_q.push_back(request);++c.reserved;}
    }
    if(edge)++f.core_edges;++f.tick;
  }
  void startup(){f.set("rocket_cache","io_cpu_req_bits_dprv",3);for(unsigned n=0;n<100;++n)step();f.reset=false;for(unsigned n=0;n<1200;++n)step();}
  bool prep_done()const{for(unsigned h=0;h<2;++h){const auto&p=clients[h];const unsigned goal=fragments-(omit_preparation&&h==0?1:0);if(p->released!=goal||p->owners.pending()||!p->request_q.empty()||!p->transport->drained())return false;}return true;}
  void run(){
    startup();stage=Preparation;for(unsigned n=0;n<240000&&!prep_done();++n)step();need(prep_done(),"bounded source preparation did not drain ordered owners");
    stage=CleanEviction;for(auto&p:clients){p->read_sent=p->read_done=0;}
    for(unsigned n=0;n<240000&&(clients[0]->read_done!=clean_lines||clients[1]->read_done!=clean_lines);++n)step();
    for(const auto&p:clients)need(p->read_done==clean_lines&&p->transport->drained(),"source clean-conflict evictions did not drain");
    // Prep groups are exactly four sixteen-byte requests, line serialized.
    // This is a finite client scope, not source VMU throughput qualification.
    // Finite external-fixture checkpoint. This does not simulate a CPU FENCE or
    // prove when another coherent observer could first see a pending write.
    for(unsigned n=0;n<4000&&checkpoint_quiet<32;++n){step();if(f.service.ledger().idle()&&!f.axi("ar_valid")&&!f.axi("aw_valid")&&!f.axi("w_valid"))++checkpoint_quiet;else checkpoint_quiet=0;}
    need(checkpoint_quiet==32,"backing not quiescent at finite external checkpoint");for(const auto&p:clients)need(std::all_of(p->prepared_bytes.begin(),p->prepared_bytes.end(),[](bool x){return x;}),"IRIS_STOREFRONT_ARENA_PREPARATION_INCOMPLETE");need(f.aw==32&&f.w==256&&f.b==32,"actual vector dirty eviction AW/W/B counts");
    for(unsigned h=0;h<2;++h)for(unsigned fragment=0;fragment<fragments;++fragment)for(unsigned n=0;n<16;++n){const auto byte=f.service.ledger().inspect(fragment_address(h,fragment)+n);need(byte.known==255&&byte.value==golden(h,fragment*16+n),"actual vector-induced B-published backing byte golden");}
    f.service.acknowledge_external_fence();stage=Readback;for(auto&p:clients){p->read_sent=p->read_done=0;}
    for(unsigned n=0;n<240000&&(clients[0]->read_done!=2*fragments||clients[1]->read_done!=2*fragments);++n)step();
    for(const auto&p:clients){need(p->read_done==2*fragments&&p->transport->drained()&&!p->owners.pending(),"bounded source readback did not drain");need(p->events[0]==3*fragments+clean_lines&&p->events[1]==p->events[0]&&p->events[2]==p->events[0]&&p->events[3]==p->events[0],"source request/A/D/response joins incomplete");}
    need(!f.system.concretized_unknown_replay_timing(),"System RPQ unknown state was concretized");
    std::cout<<"{\"pass\":true,\"source_VMU_requests\":"<<vm_requests<<",\"actual_TL_A\":"<<physical_A<<",\"actual_TL_D\":"<<physical_D<<",\"actual_VMU_responses\":"<<vm_responses<<",\"independent_read_bytes\":"<<checked_bytes<<",\"clean_read_bytes\":"<<clean_checked_bytes<<",\"ordered_prep_fragments_per_hart\":"<<fragments<<",\"AXI_AR\":"<<f.ar<<",\"AW\":"<<f.aw<<",\"W\":"<<f.w<<",\"R\":"<<f.r<<",\"B\":"<<f.b<<",\"master_ticks\":"<<f.tick<<",\"native_ELF_or_architectural_FENCE_qualified\":false}\n";
  }
};
}
int main(int argc,char**argv){try{const auto mode=argc==2?std::string(argv[1]):"";omit_preparation=mode=="--omit-preparation";wrong_D_source=mode=="--wrong-D-source";wrong_read_data=mode=="--wrong-read-data";undefined_backing=mode=="--undefined-backing";wrong_write_data=mode=="--wrong-write-data";Arena fixture(mode=="--seed17"?17:1);fixture.run();return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
