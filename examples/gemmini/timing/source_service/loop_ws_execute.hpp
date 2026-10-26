#ifndef GEMMINI_LOOP_WS_EXECUTE_HPP
#define GEMMINI_LOOP_WS_EXECUTE_HPP
#include <cstdint>
#include <optional>
#include <stdexcept>
namespace gemmini_annotated_spike {
// LoopMatmulExecute, selected non-transposed WS domain. This is one of the
// six hardware generators, not a complete LOOP_WS timing implementation.
class LoopWsExecute {
 public:
 using Cycle=std::uint64_t;
 struct Origin {std::uint64_t pc,bits,sequence;};
 struct Request {
   unsigned max_i,max_j,max_k,pad_i,pad_j,pad_k;
   unsigned a_start,b_end,c_start,loop_id;
   bool accumulate=false,skip=false;Origin origin;
 };
 struct Progress {
   unsigned ld_ka=0,ld_kb=0,ld_i=0,ld_j=0;
   bool lda_complete=false,ldb_complete=false,ldd_complete=false,rob_overloaded=false;
 };
 struct Packet {unsigned funct;std::uint64_t rs1,rs2;Origin original;unsigned loop_id,i,j,k;};
 private:
 enum class State {idle,pre,compute};State state_=State::idle;
 std::optional<Request>request_;unsigned i_=0,j_=0,k_=0;
 Cycle visible_=0;std::optional<Cycle>last_edge_,retired_;
 static std::uint64_t pack(unsigned address,unsigned rows,unsigned cols){return address|(std::uint64_t(rows)<<48)|(std::uint64_t(cols)<<32);}
 public:
 bool idle()const{return state_==State::idle;}
 unsigned i()const{return i_;}unsigned j()const{return j_;}unsigned k()const{return k_;}
 void accept(Request r,Cycle at){
   if(!idle()||(retired_&&at<=*retired_)||at==UINT64_MAX)throw std::logic_error("loop EX request has no original idle-state credit");
   if(!r.max_i||!r.max_j||!r.max_k||r.max_i>65535||r.max_j>65535||r.max_k>65535||r.pad_i>15||r.pad_j>15||r.pad_k>15||r.loop_id>1)
     throw std::invalid_argument("selected loop EX iterator/pad/context domain");
   const auto a_rows=std::uint64_t(r.max_i)*r.max_k*16,b_rows=std::uint64_t(r.max_k)*r.max_j*16,c_rows=std::uint64_t(r.max_i)*r.max_j*16;
   if(r.a_start>=16384||r.b_end>16384||a_rows>16384-r.a_start||b_rows>r.b_end||r.c_start>=1024||c_rows>1024-r.c_start)
     throw std::invalid_argument("loop EX panel outside selected SP/ACC capacity; wrapping storage not admitted");
   request_=r;state_=State::pre;i_=j_=k_=0;visible_=at+1;
 }
 std::optional<Packet>peek(Cycle at,const Progress&p)const{
   if(idle()||at<visible_||request_->skip||p.rob_overloaded)return {};
   const bool a=p.lda_complete||p.ld_ka>k_||(p.ld_ka==k_&&p.ld_i>i_);
   // Keep the selected source's ld_ka comparison in the second B term.
   // Replacing it by ld_kb would silently implement different RTL.
   const bool b=p.ldb_complete||p.ld_kb>k_||(p.ld_ka==k_&&p.ld_j>j_);
   if(!a||!b||!p.ldd_complete)return {};
   const auto&r=*request_;const auto ar=16-(i_+1==r.max_i?r.pad_i:0),ac=16-(k_+1==r.max_k?r.pad_k:0);
   const auto br=ac,bc=16-(j_+1==r.max_j?r.pad_j:0);
   const auto a_address=r.a_start+(i_*r.max_k+k_)*16;
   const auto b_address=r.b_end-r.max_k*r.max_j*16+(k_*r.max_j+j_)*16;
   const auto c_address=0x80000000u|((r.accumulate||k_!=0)?0x40000000u:0u)|(r.c_start+(i_*r.max_j+j_)*16);
   if(state_==State::pre)return Packet{6,pack(i_==0?b_address:0xffffffffu,br,bc),pack(c_address,ar,bc),r.origin,r.loop_id,i_,j_,k_};
   return Packet{i_==0?4u:5u,pack(a_address,ar,ac),pack(0xffffffffu,16,16),r.origin,r.loop_id,i_,j_,k_};
 }
 std::optional<Packet>edge(Cycle at,bool downstream_ready,const Progress&p){
   if(last_edge_&&at<=*last_edge_)throw std::logic_error("loop EX edge repeated or reversed");
   last_edge_=at;auto packet=peek(at,p);
   if(request_&&request_->skip&&at>=visible_&&!idle()){state_=State::idle;retired_=at;return {};}
   if(!packet||!downstream_ready)return {};
   if(state_==State::pre)state_=State::compute;
   else{
     const auto&r=*request_;
     if(++i_==r.max_i){i_=0;if(++j_==r.max_j){j_=0;if(++k_==r.max_k){k_=0;state_=State::idle;retired_=at;}}}
     if(!idle())state_=State::pre;
   }
   return packet;
 }
};
}
#endif
