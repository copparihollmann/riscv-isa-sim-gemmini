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
 // Native device-path capture AFTER original coherent_access. Only a hit
 // with no private probe may retire its Get MSHR at SourceD request capture.
 bool device_resident_no_probe=false;
 std::uint64_t inner_address=0,inner_bytes=0;
 // Exact effects captured in this cache-access child walk, before any parent
 // max/probe joins. Never clone the enclosing CPU request onto each record.
 SharedEffects source_request;
};
struct ReadParentWritebackV11 {
 // Original private-victim ReleaseData, observed before its lower read child.
 // Service remains included once in the existing residual request bound.
 std::uint64_t address=0,bytes=0,before_child=0;
 std::vector<merlin_timing::ValueId>writes;
};
struct ReadAllocationEffectsV7 {
 std::uint32_t size=sizeof(ReadAllocationEffectsV7),version=7,snapshot_revision=5;
 // Residual ORIGINAL parent service, excluding per-allocation child walks.
 // It is submitted once. Its private fill/CPU destination writes publish after
 // EVERY child; separately observed parent_writebacks publish at prefix-ready.
 // Children own their lookup/lower effects and source-stage replacements.
 SharedEffects source_request;
 std::vector<ReadAllocationV7>allocations;
 std::vector<ReadParentWritebackV11>parent_writebacks;
 // SourceD registered data-read stages, not an arbitrary command surcharge.
 merlin_timing::Cycle response_stages=2;
 std::string unavailable;
};
struct ReadAllocationServiceV7 {
 std::uint32_t size=sizeof(ReadAllocationServiceV7),version=7;
 // Revision5 distinguishes original private writeback publications from the
 // later private fill/CPU destination publication. Native and provider must
 // agree; older snapshots cannot manufacture that phase distinction.
 std::uint32_t snapshot_revision=5;
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
// Optional CPU request intake. The native private-cache preview is read-only:
// it supplies the original LLC line requests, never a speculative LLC lookup.
// Classification runs only after those requests own the finite source MSHRs.
// V7 layouts and existing callers remain unchanged.
struct CpuReadAdmissionV10 {
 std::uint32_t size=sizeof(CpuReadAdmissionV10),version=10;
 std::vector<std::uint64_t>line_addresses;
};
enum class CpuReadLookupStatusV10 {accepted,retry,refused};
using ClassifyCpuReadV10=CpuReadLookupStatusV10(*)(void*,merlin_timing::Cycle,ReadAllocationEffectsV7*);
using SubmitCpuReadV10=bool(*)(void*,const CpuReadAdmissionV10*,const merlin_timing::StageOrigin*,
 merlin_timing::Cycle,void*,ClassifyCpuReadV10,ReadAllocationReadyV7);
}
#endif
