#include "loop_ws_execute.hpp"
#include <cassert>
#include <iostream>
using L=gemmini_annotated_spike::LoopWsExecute;
int main(){
 L generator;L::Request request{2,2,2,15,3,5,0,8192,0,1,false,false,{0x80001000,0x1000307b,42}};
 generator.accept(request,0);L::Progress loaded{0,0,0,0,true,true,true,false};assert(!generator.peek(0,loaded));
 auto first=generator.peek(1,loaded);assert(first&&first->funct==6&&std::uint32_t(first->rs1)==8128&&std::uint32_t(first->rs2)==0x80000000u);
 for(unsigned t=1;t<5;++t){assert(!generator.edge(t,false,loaded));auto held=generator.peek(t,loaded);assert(held&&held->rs1==first->rs1&&held->rs2==first->rs2&&held->original.sequence==42);}
 loaded.rob_overloaded=true;assert(!generator.edge(5,true,loaded));loaded.rob_overloaded=false;
 unsigned commands=0;for(unsigned t=6;!generator.idle();++t){
   auto packet=generator.edge(t,true,loaded);assert(packet&&packet->original.pc==request.origin.pc&&packet->original.bits==request.origin.bits&&packet->loop_id==1);
   const auto tile=commands/2;assert(packet->i==tile%2&&packet->j==(tile/2)%2&&packet->k==tile/4);
   if(commands%2==0){assert(packet->funct==6);assert((std::uint32_t(packet->rs1)==0xffffffffu)==(packet->i!=0));assert(bool(std::uint32_t(packet->rs2)&0x40000000u)==(packet->k!=0));}
   else{assert(packet->funct==(packet->i==0?4u:5u));assert(std::uint32_t(packet->rs2)==0xffffffffu);assert((packet->rs1>>48)==(packet->i==1?1:16));assert(((packet->rs1>>32)&65535)==(packet->k==1?11:16));}
   ++commands;assert(commands<=16);
 }
 assert(commands==16);
 // Progress is emission progress, not a fictitious data-completion signal.
 L waiting;waiting.accept(request,0);L::Progress partial{};assert(!waiting.peek(1,partial));partial.ld_i=1;partial.ld_j=1;partial.ldd_complete=true;assert(waiting.peek(1,partial));
 partial.ld_j=0;assert(!waiting.peek(1,partial));partial.ldb_complete=true;assert(waiting.peek(1,partial));
 // This source expression is intentionally not ld_kb == k. Reach k=1
 // and distinguish the two expressions with ld_kb=0, ld_ka=1.
 L source_b;source_b.accept(request,0);
 for(unsigned t=1;t<=8;++t)assert(source_b.edge(t,true,loaded));
 assert(source_b.k()==1);
 L::Progress b_expression{1,0,0,1,true,false,true,false};
 assert(source_b.peek(9,b_expression));
 b_expression.ld_ka=0;assert(!source_b.peek(9,b_expression));
 // Skip retires emission at its registered edge without producing work or
 // implying that another generator's memory/mesh work has completed.
 L skipped;auto skip_request=request;skip_request.skip=true;
 skipped.accept(skip_request,10);assert(!skipped.idle());
 assert(!skipped.edge(10,true,loaded));assert(!skipped.idle());
 assert(!skipped.edge(11,true,loaded));assert(skipped.idle());
 bool refused=false;try{skipped.accept(request,11);}catch(const std::logic_error&){refused=true;}assert(refused);
 skipped.accept(request,12);assert(!skipped.peek(12,loaded));assert(skipped.peek(13,loaded));
 // Large iteration counts do not silently wrap or enlarge physical panels.
 L invalid;auto oversized=request;oversized.max_i=65535;
 refused=false;try{invalid.accept(oversized,0);}catch(const std::invalid_argument&){refused=true;}assert(refused&&invalid.idle());
 std::cout<<"source LOOP_WS EX PRE/COMPUTE FSM, original loop identity, i/j/k/pad/reuse, RS/output backpressure and source load-progress predicates PASS\n";
}
