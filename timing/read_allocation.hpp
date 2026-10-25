#ifndef SPIKE_TIMING_READ_ALLOCATION_HPP
#define SPIKE_TIMING_READ_ALLOCATION_HPP
#include "write_transaction.hpp"
#include <merlin_timing/engine.hpp>
namespace spike_timing {
// Optional source-owned replacement route. Existing SharedEffects and V1--V6
// service layouts remain unchanged. Only the immediately preceding native
// access may issue this batch; take() transfers its single ownership once.
struct ReadAllocationV7 {
 WriteMissV5 miss;
 std::optional<VictimProbeV6>victim;
 // The selected D$ cached request is AcquireBlock/GrantData+inner E;
 // I$ and DMA requests are Get/AccessAckData and create no coherent client.
 bool inner_acquire=false;
 bool resident=false; // exact native LLC hit: no outer acquire/fill/outer E
 std::uint64_t inner_address=0,inner_bytes=0;
};
struct ReadAllocationEffectsV7 {
 std::uint32_t size=sizeof(ReadAllocationEffectsV7),version=7;
 // Retains the ORIGINAL native value dependencies. The owning cache_access
 // removes captured lower fill/release service once, and replaces only that
 // LLC lookup component with Directory1/MSHRplan1 BEFORE later max joins.
 SharedEffects source_request;
 std::vector<ReadAllocationV7>allocations;
 // SourceD registered data-read stages, not an arbitrary command surcharge.
 merlin_timing::Cycle response_stages=2;
 std::string unavailable;
};
struct ReadAllocationServiceV7 {
 std::uint32_t size=sizeof(ReadAllocationServiceV7),version=7;
 // Revision2 introduces resident snapshots. Changing service size makes
 // mixed frozen V52/native or provider bundles refuse instead of reading
 // an older snapshot's unspecified padding as the new resident bit.
 std::uint32_t snapshot_revision=2;
 void*opaque=nullptr;
 // false means no captured allocation: ordinary effects stay unchanged.
 // true with unavailable means refusal; NEVER fall back to decomposed costs.
 bool(*take)(void*,ReadAllocationEffectsV7*)=nullptr;
 bool(*client_released)(void*,const VictimProbeV6*,merlin_timing::Cycle)=nullptr;
};
using InstallReadAllocationServiceV7=void(*)(void*,const ReadAllocationServiceV7*);
using ReadAllocationReadyV7=void(*)(void*,merlin_timing::Cycle);
// Copies the batch and origin before returning. Completion is asynchronous;
// it must not advance/step a timeline recursively from an actor callback.
// The CPU caller retains cookie until ready or terminal timeline failure.
using SubmitReadAllocationsV7=bool(*)(void*,const ReadAllocationEffectsV7*,
 const merlin_timing::StageOrigin*,merlin_timing::Cycle,void*,ReadAllocationReadyV7);
}
#endif
