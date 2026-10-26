#include "fetch_parcel_buffer.hpp"
#include <cassert>
#include <iostream>
using spike_timing::FetchParcelBuffer;
int main(){
 FetchParcelBuffer b;
 auto p=b.plan(0x1000,2);assert(p.address==0x1000&&p.bytes==4&&!p.retained);b.commit(0x1000,2,0x1002,false,p);
 p=b.plan(0x1002,2);assert(!p.bytes&&p.retained);b.commit(0x1002,2,0x1004,false,p);assert(b.plan(0x1004,2).bytes==4);
 p=b.plan(0x103e,4);assert(p.address==0x103c&&p.bytes==8);b.commit(0x103e,4,0x1042,false,p);
 p=b.plan(0x1042,4);assert(p.retained&&p.address==0x1044&&p.bytes==4);b.commit(0x1042,4,0x1046,false,p);
 assert(b.plan(0x1046,2).bytes==0);
 b.reset();assert(b.plan(0x1046,2).bytes==4);
 p=b.plan(0x2000,2);b.commit(0x2000,2,0x2002,true,p);assert(b.plan(0x2002,2).bytes==4);
 p=b.plan(0x2000,2);b.commit(0x2000,2,0x3000,false,p);assert(!b.plan(0x3000,2).retained);
 std::cout<<"IBuf one retained halfword, straddled instruction and redirect/fence ownership PASS\n";
}
