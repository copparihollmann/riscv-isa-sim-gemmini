#include "rocket_writeback.hpp"
#include <cassert>
#include <iostream>
using W=spike_timing::RocketWriteback;
int main(){
 W wb;W::Identity divide{1,0x80001000,0x02004033,7},rocc{2,0x80001004,0x0000707b,8},vector{3,0x80001008,0x00000057,9};
 wb.accept_divide({divide,0,5,100,7});
 for(unsigned at=0;at<5;++at){assert(!wb.divide_response_valid(at)&&!wb.divide_request_ready(at));assert(!wb.edge(at,{},{},{},{}));}
 // Valid holds through ordinary WB contention and a higher-priority original
 // D$ replay. No destination/scoreboard publication or unit release occurs.
 for(unsigned at=5;at<8;++at){assert(wb.divide_response_valid(at));assert(!wb.edge(at,{true,true},{},rocc,vector));assert(wb.pending_divide()->instruction.pc==divide.pc&&wb.pending_divide()->lhs==100&&wb.pending_divide()->rhs==7);}
 W::Replay replay{true,true,true,{4,0x8000100c,0x00003003,10}};
 auto load=wb.edge(8,{},replay,rocc,vector);assert(load&&load->source==W::Source::replayed_load&&load->instruction.rd==10&&wb.pending_divide());
 auto result=wb.edge(9,{}, {},rocc,vector);assert(result&&result->source==W::Source::divide&&result->instruction.sequence==1&&result->instruction.pc==divide.pc&&result->instruction.bits==divide.bits&&result->instruction.rd==7&&result->clears_scoreboard&&result->original_divide->lhs==100&&result->original_divide->rhs==7);
 assert(!wb.divide_request_ready(9)&&wb.divide_request_ready(10));
 // FPU/no-data responses do not steal XPR WB. Divider > RoCC > vector.
 wb.accept_divide({{5,0x80001010,0x0200603b,0},10,12});
 assert(wb.edge(10,{}, {},rocc,vector)->source==W::Source::rocc);
 assert(wb.edge(11,{}, {},{},vector)->source==W::Source::vector);
 replay.xpu=false;assert(wb.edge(12,{},replay,rocc,vector)->source==W::Source::divide);
 assert(!wb.divide_request_ready(12)&&wb.divide_request_ready(13));
 bool refused=false;try{wb.edge(12,{},{});}catch(const std::logic_error&){refused=true;}assert(refused);
 std::cout<<"Rocket WB priority, held original divide identity/result availability, same-edge scoreboard bypass and next-edge MulDiv request release PASS\n";
}
