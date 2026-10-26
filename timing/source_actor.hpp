#ifndef SPIKE_TIMING_SOURCE_ACTOR_HPP
#define SPIKE_TIMING_SOURCE_ACTOR_HPP
#include <cstdint>
#include <cstddef>
namespace spike_timing {
// Optional observation-only ABI. No token, queue, resource or timing authority.
enum class SourceActorRoleV1 : std::uint32_t {
 load_command, store_command, execute_command, load_rs_wait, store_rs_wait,
 execute_rs_wait, execute_feed, reader_slot, writer_state, writer_slot, count
};
struct SourceActorSinkV1 {
 std::uint32_t version=1;std::size_t size=sizeof(SourceActorSinkV1);void*opaque=nullptr;
 void(*role)(void*,SourceActorRoleV1,std::uint64_t)=nullptr; // zero: envelope has no capacity law
 void(*edge)(void*,SourceActorRoleV1,std::uint64_t,std::uint64_t,bool)=nullptr;
};
using InstallSourceActorSinkV1=bool(*)(void*,const SourceActorSinkV1*);
}
#endif
