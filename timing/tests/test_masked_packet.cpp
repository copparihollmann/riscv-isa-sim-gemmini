#include "write_transaction.hpp"
#include <cassert>
using namespace spike_timing;
int main(){
 MaskedWritePacketV8 p;p.address=0x81000000;p.transaction_bytes=64;p.masks={0,0xff00,0xffff,0x1f};
 auto useful=masked_write_packet_useful(p);assert(useful&&useful->address==p.address+24&&useful->bytes==29);
 p.masks[2]=0xfffe;assert(!masked_write_packet_useful(p));
 p.masks={0,0,0,0};assert(!masked_write_packet_useful(p));
 p.transaction_bytes=32;p.masks={0x8000,0x7fff};useful=masked_write_packet_useful(p);assert(useful&&useful->address==p.address+15&&useful->bytes==16);
 p.masks[0]|=1ull<<16;assert(!masked_write_packet_useful(p));
 p.masks={0xffff,0xffff};p.address+=16;assert(!masked_write_packet_useful(p));
}
