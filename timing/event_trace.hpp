#ifndef SPIKE_TIMING_EVENT_TRACE_HPP
#define SPIKE_TIMING_EVENT_TRACE_HPP
#include "model.hpp"
#include "integer_divider_timing.hpp"
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace spike_timing {
// Operator diagnostic, not physical timing or a qualification record. Fixed
// bounds stop collection without modifying scheduling or silently dropping rows.
class EventTrace {
public:
  static constexpr std::size_t default_max_events = 32768, default_max_bytes = 16 * 1024 * 1024;
  explicit EventTrace(const std::string &path,std::size_t events=default_max_events,std::size_t bytes=default_max_bytes)
      : out_(path, std::ios::out | std::ios::trunc),max_events(events),max_bytes(bytes) {
    if(!events||events>1048576||bytes<1024||bytes>1024ull*1024*1024)
      throw std::invalid_argument("event trace diagnostic work bound");
    if (!out_) throw std::runtime_error("cannot open timing event trace");
  }
  void header(const std::string &model, const std::string &elf, const std::string &scope) {
    append("{\"schema\":\"merlin.modeled_event_trace.v1\",\"model_sha256\":" + json_string(model) +
           ",\"elf_sha256\":" + json_string(elf) + ",\"scope_binding_sha256\":" + json_string(scope) +
           ",\"meaning\":\"modeled constraints; not physical stalls\"}");
  }
  bool full() const { return truncated_; }
  void record(const merlin_timing::Trace &r, std::uint64_t pc, std::uint64_t bits,
              const char *cpu_kind, std::uint64_t instruction) {
    if (truncated_) return;
    if (events_ >= max_events) { truncated_ = true; return; }
    const auto &origin=r.event.origin;
    if(origin){pc=origin->pc;bits=origin->bits;}
    std::ostringstream s;
    s << "{\"event\":" << events_ << ",\"pc\":" << pc << ",\"instruction_bits\":" << bits
      << ",\"instruction_index\":" << (origin?number(origin->committed_instruction):std::to_string(instruction)) << ",\"cpu_kind\":" << json_string(origin?"actor_source":cpu_kind)
      << ",\"actor_origin\":" << (origin?"true":"false") << ",\"actor\":" << json_string(origin?origin->actor:"observer_bookkeeping")
      << ",\"action\":" << json_string(r.action) << ",\"earliest\":" << r.event.earliest
      << ",\"frontier_before\":" << number(r.frontier_before) << ",\"frontier_after\":" << number(r.frontier_after)
      << ",\"horizon_before\":" << r.horizon_before << ",\"horizon_after\":" << r.horizon_after
      << ",\"token\":" << number(r.token) << ",\"requested\":" << number(r.requested)
      << ",\"latency\":" << number(r.event.latency)
      << ",\"hold_reads_until_ready\":" << (r.event.hold_reads_until_ready ? "true" : "false")
      << ",\"issue\":" << number(r.result.issue) << ",\"start\":" << number(r.result.start)
      << ",\"ready\":" << number(r.result.ready) << ",\"unknown\":" << json_string(merlin_timing::name(r.result.unknown));
    ids(s, "reads", r.event.reads); ids(s, "retained_reads", r.event.retained_reads); ids(s, "writes", r.event.writes);
    s << ",\"values_before\":["; bool first = true;
    for (const auto &v : r.values) { comma(s, first); s << "{\"id\":" << v.id << ",\"writer\":" << number(v.writer) << ",\"readers\":" << number(v.readers) << '}'; }
    s << "],\"resources_before\":["; first = true;
    for (std::size_t i = 0; i < r.resources.size(); ++i) {
      const auto &v = r.resources[i]; const auto &d = r.event.demands[i]; comma(s, first);
      s << "{\"id\":" << v.id << ",\"units\":" << d.units << ",\"occupancy\":" << number(d.occupancy)
        << ",\"queue_capacity\":" << v.queue_capacity << ",\"known\":" << (v.known ? "true" : "false");
      ids(s, "lanes", merlin_timing::View<merlin_timing::Cycle>{v.lanes.data(), v.lanes.size()});
      ids(s, "queued_starts", merlin_timing::View<merlin_timing::Cycle>{v.queued_starts.data(), v.queued_starts.size()}); s << '}';
    }
    s << "]}";
    if (append(s.str())) ++events_;
  }
  void divider(std::uint64_t pc,std::uint64_t bits,std::uint64_t instruction,const IntegerDividerService&service){
    if(truncated_)return;
    if(events_>=max_events){truncated_=true;return;}
    std::ostringstream s;s<<"{\"kind\":\"integer_divider_operands\",\"pc\":"<<pc
      <<",\"instruction_bits\":"<<bits<<",\"instruction_index\":"<<instruction
      <<",\"lhs\":"<<service.lhs<<",\"rhs\":"<<service.rhs
      <<",\"request_to_valid_cycles\":"<<service.latency<<",\"response_ready\":\"assumed_immediate\"}";
    if(append(s.str()))++events_;
  }
  void finish(bool completed) {
    // Reserve 256 bytes in append for this explicit completion/truncation row.
    out_ << "{\"summary\":true,\"events\":" << events_ << ",\"truncated\":" << (truncated_ ? "true" : "false")
         << ",\"execution_completed\":" << (completed ? "true" : "false") << "}\n";
    out_.flush();
    if (!out_) throw std::runtime_error("cannot finish timing event trace");
  }
private:
  std::ofstream out_;
  const std::size_t max_events,max_bytes;
  std::size_t events_ = 0, bytes_ = 0;
  bool truncated_ = false;
  static std::string number(std::optional<std::uint64_t> n) { return n ? std::to_string(*n) : "null"; }
  static void comma(std::ostream &s, bool &first) { if (!first) s << ','; first = false; }
  template<class T> static void ids(std::ostream &s, const char *name, merlin_timing::View<T> values) {
    s << ",\"" << name << "\":[";
    for (std::size_t i = 0; i < values.size; ++i) { if (i) s << ','; s << values[i]; } s << ']';
  }
  bool append(const std::string &line) {
    if (line.size() + 1 > max_bytes - 256 - bytes_) { truncated_ = true; return false; }
    out_ << line << '\n'; bytes_ += line.size() + 1;
    if (!out_) throw std::runtime_error("cannot write timing event trace");
    return true;
  }
};
}
#endif
