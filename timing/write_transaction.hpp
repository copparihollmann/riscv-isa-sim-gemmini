#ifndef SPIKE_TIMING_WRITE_TRANSACTION_HPP
#define SPIKE_TIMING_WRITE_TRANSACTION_HPP
#include "provider.hpp"
#include <limits>
namespace spike_timing {
// Optional typed side channel. Transaction coverage and actually modified
// bytes are different facts; no unmasked byte becomes a write dependency.
// This initial ABI admits a single complete client beat with a nonempty,
// contiguous useful mask. Multibeat, sparse and zero-mask transactions refuse.
struct WriteTransactionV1 {
 std::uint32_t size=sizeof(WriteTransactionV1),version=1;
 std::uint64_t address=0,transaction_bytes=0,beat_bytes=0,mask=0;
 merlin_timing::Cycle accepted=0;
};
struct WriteUsefulBytes {std::uint64_t address,bytes;};
inline std::optional<WriteUsefulBytes> one_beat_write_useful(const WriteTransactionV1&r){
 if(r.version!=1||r.size!=sizeof(r)||!r.beat_bytes||r.beat_bytes>64||
    (r.beat_bytes&(r.beat_bytes-1))||r.transaction_bytes!=r.beat_bytes||
    r.address%r.beat_bytes||r.address>UINT64_MAX-(r.beat_bytes-1)||!r.mask||
    (r.beat_bytes<64&&(r.mask>>r.beat_bytes)))return {};
 std::uint64_t begin=0;while(!(r.mask&(std::uint64_t{1}<<begin)))++begin;
 auto end=begin;while(end<r.beat_bytes&&(r.mask&(std::uint64_t{1}<<end)))++end;
 if(end<64&&(r.mask>>end))return {};
 return WriteUsefulBytes{r.address+begin,end-begin};
}
struct WriteTransactionEffectsV1 {
 // Owner stops at SourceD request readiness, BEFORE S2/S3/ACK/publication.
 SharedEffects source_request;
 bool sram_read_required=false;
 std::string unavailable;
};
struct WriteTransactionServiceV1 {
 std::uint32_t size=sizeof(WriteTransactionServiceV1),version=1;
 void*opaque=nullptr;
 bool(*admit)(void*,const WriteTransactionV1*,WriteTransactionEffectsV1*)=nullptr;
};
using InstallWriteTransactionServiceV1=void(*)(void*,const WriteTransactionServiceV1*);
// V1 remains resident/no-probe. V2 optionally exposes a separate selected
// private-probe actor; its busy interval and response readiness are distinct.
struct WriteProbeV2 {
 merlin_timing::ResourceId resource;
 merlin_timing::Cycle lookup,dirty_enter,data_pipeline,metadata;
 std::uint64_t line_bytes,beat_bytes;
 bool dirty;
};
struct WriteTransactionEffectsV2 {
 std::uint32_t size=sizeof(WriteTransactionEffectsV2),version=2;
 WriteTransactionEffectsV1 base;
 std::optional<WriteProbeV2> probe;
};
struct WriteTransactionServiceV2 {
 std::uint32_t size=sizeof(WriteTransactionServiceV2),version=2;
 void*opaque=nullptr;
 bool(*admit)(void*,const WriteTransactionV1*,WriteTransactionEffectsV2*)=nullptr;
};
using InstallWriteTransactionServiceV2=void(*)(void*,const WriteTransactionServiceV2*);
// Optional full-packet side channel: ONE Directory/MSHR/probe request and ONE
// D acknowledgement, even when the original PutFull has several A beats.
// This deliberately does not admit masked, crossing-line or split packets.
struct FullWritePacketV3 {
 std::uint32_t size=sizeof(FullWritePacketV3),version=3;
 std::uint64_t address=0,transaction_bytes=0,beat_bytes=0;
 merlin_timing::Cycle accepted=0;
};
inline bool full_write_packet_valid(const FullWritePacketV3&r){
 return r.version==3&&r.size==sizeof(r)&&r.beat_bytes==16&&
   r.transaction_bytes>=16&&r.transaction_bytes<=64&&
   !(r.transaction_bytes&(r.transaction_bytes-1))&&
   !(r.address%r.transaction_bytes)&&r.address<=UINT64_MAX-(r.transaction_bytes-1);
}
struct FullWritePacketServiceV3 {
 std::uint32_t size=sizeof(FullWritePacketServiceV3),version=3;
 void*opaque=nullptr;
 bool(*admit)(void*,const FullWritePacketV3*,WriteTransactionEffectsV2*)=nullptr;
};
using InstallFullWritePacketServiceV3=void(*)(void*,const FullWritePacketServiceV3*);
// Optional cold-output extension. A miss is a real allocation event, not a
// pre-warmed resident hit. Lower service retains the selected model's prices;
// the source actor owns A/C/D transport, MSHR credit and cache publication.
// Old service layouts/symbols remain unchanged and cannot admit this route.
struct WriteMissV4 {
 std::uint64_t line=0,set=0,slot=0,generation=0;
 std::optional<std::uint64_t> evicted_line;
 bool dirty_eviction=false,acquire_block=false;
 // Independent lower transactions, before source transport. Each includes
 // only the original DRAM service (never Directory/MSHR or a guessed fee).
 merlin_timing::Cycle fill_latency=0,fill_bus=0,release_latency=0,release_bus=0;
};
struct WriteTransactionEffectsV4 {
 std::uint32_t size=sizeof(WriteTransactionEffectsV4),version=4;
 WriteTransactionEffectsV2 resident;
 std::optional<WriteMissV4> miss;
};
struct ColdWriteServiceV4 {
 std::uint32_t size=sizeof(ColdWriteServiceV4),version=4;
 void*opaque=nullptr;
 bool(*beat)(void*,const WriteTransactionV1*,WriteTransactionEffectsV4*)=nullptr;
 bool(*packet)(void*,const FullWritePacketV3*,WriteTransactionEffectsV4*)=nullptr;
};
using InstallColdWriteServiceV4=void(*)(void*,const ColdWriteServiceV4*);
// Dirty eviction has two distinct storage owners: old DRAM bytes complete
// on writeback acknowledgment; new cache bytes complete on SourceD S4.
// Keep V4 binary layout/guards unchanged and expose this optional ABI instead.
struct WriteMissV5:WriteMissV4 {std::vector<merlin_timing::ValueId>release_writes;};
struct WriteTransactionEffectsV5 {
 std::uint32_t size=sizeof(WriteTransactionEffectsV5),version=5;
 WriteTransactionEffectsV2 resident;
 std::optional<WriteMissV5>miss;
};
struct ColdWriteServiceV5 {
 std::uint32_t size=sizeof(ColdWriteServiceV5),version=5;
 void*opaque=nullptr;
 bool(*beat)(void*,const WriteTransactionV1*,WriteTransactionEffectsV5*)=nullptr;
 bool(*packet)(void*,const FullWritePacketV3*,WriteTransactionEffectsV5*)=nullptr;
};
using InstallColdWriteServiceV5=void(*)(void*,const ColdWriteServiceV5*);
// Optional victim-rprobe snapshot. Its identity is the ORIGINAL replaced
// Directory entry, not the new allocation or a synthetic target-line probe.
struct VictimProbeV6 {
 std::uint64_t line=0,set=0,way=0,generation=0,private_slot=0;
 bool llc_dirty=false,private_dirty=false;
 merlin_timing::Cycle client_ready=0;
 std::string source_identity;
};
struct WriteTransactionEffectsV6 {
 std::uint32_t size=sizeof(WriteTransactionEffectsV6),version=6;
 WriteTransactionEffectsV2 resident;
 std::optional<WriteMissV5>miss;
 std::optional<VictimProbeV6>victim;
};
struct ColdWriteServiceV6 {
 std::uint32_t size=sizeof(ColdWriteServiceV6),version=6;
 void*opaque=nullptr;
 bool(*beat)(void*,const WriteTransactionV1*,WriteTransactionEffectsV6*)=nullptr;
 bool(*packet)(void*,const FullWritePacketV3*,WriteTransactionEffectsV6*)=nullptr;
 bool(*client_released)(void*,const VictimProbeV6*,merlin_timing::Cycle)=nullptr;
};
using InstallColdWriteServiceV6=void(*)(void*,const ColdWriteServiceV6*);
}
#endif
