#include "frontend_engine.hpp"

#include <algorithm>
#include <iomanip>
#include <limits>
#include <ostream>
#include <stdexcept>

namespace iris {
namespace {
constexpr Cycle never = std::numeric_limits<Cycle>::max();
Cycle add(Cycle a, Cycle b) {
  // UINT64_MAX is the event queue's no-event marker, not a usable timestamp.
  if (b >= never - a) throw std::overflow_error("modeled cycle horizon reached");
  return a + b;
}
Cycle align(Cycle value, Cycle period) {
  Cycle remainder = value % period;
  return remainder ? add(value, period - remainder) : value;
}
void string_json(std::ostream& out, const std::string& value) {
  out << '"';
  for (unsigned char c : value) {
    if (c == '"' || c == '\\') out << '\\' << c;
    else if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                         << unsigned(c) << std::dec;
    else out << c;
  }
  out << '"';
}
}

Machine::Machine(unsigned harts, uint64_t cycles_per_rtc_tick)
    : harts_(harts), rtc_divider_(cycles_per_rtc_tick), retired_(harts, 0),
      compares_(harts, never), software_irq_(harts, false) {
  if (!harts || !rtc_divider_) throw std::invalid_argument("explicit hart count and RTC divider required");
  delivered_timer_irq_.resize(harts, false);
}
void Machine::check_hart(unsigned hart) const {
  if (hart >= harts_) throw std::out_of_range("invalid hart");
}
void Machine::configure_resource(const std::string& name, unsigned lanes) {
  if (name.empty() || !lanes || resources_.count(name))
    throw std::invalid_argument("resource name/capacity invalid or already configured");
  resources_[name] = Resource{std::vector<Cycle>(lanes, 0)};
}
NodeId Machine::issue(Op op) {
  check_hart(op.hart);
  if (!op.latency || !op.interval || !op.issue_period || op.earliest == never || !resources_.count(op.resource))
    throw std::invalid_argument("unknown resource or missing explicit latency/interval");
  for (auto dep : op.deps)
    if (dep >= nodes_.size()) throw std::invalid_argument("dependency must name an existing node");
  NodeId id = nodes_.size();
  nodes_.push_back(Node{id, std::move(op), false, false, now_, 0, 0, 0});
  pending_.insert(id);
  return id;
}
void Machine::cancel(NodeId id, const std::string& reason) {
  if(id>=nodes_.size() || reason.empty())throw std::invalid_argument("explicit cancellation node/reason required");
  auto& n=nodes_[id];
  if(!n.op.cancellable)throw std::logic_error("accepted memory/device actor is not cancellable");
  if(n.completed || n.cancelled || completing_==std::optional<NodeId>(id))throw std::logic_error("completed/cancelled/active callback cannot be cancelled");
  n.cancelled=true;n.cancel_cycle=now_;n.cancel_reason=reason;
  if(!n.issued)n.start=now_;
  n.end=now_;n.op.on_complete={};pending_.erase(id);inflight_.erase(id);
  // The launch reservation already consumed is not refunded. For source CPU
  // stages it lasts one owning clock edge, independently of completion/kill.
}
void Machine::mark_squashed(NodeId id, const std::string& reason) {
  if(id>=nodes_.size() || reason.empty())throw std::invalid_argument("explicit squash node/reason required");
  auto& n=nodes_[id];
  if(!n.op.cancellable || !n.completed || n.cancelled)throw std::logic_error("only completed owned CPU work can be squash-annotated");
  n.squashed=true;n.squash_cycle=now_;n.squash_reason=reason;
}
Cycle Machine::next_event() const {
  Cycle next = never;
  if (interrupt_callback_) {
    const uint64_t current = mtime();
    const Cycle phase = (now_ - rtc_origin_) % rtc_divider_;
    for (unsigned hart = 0; hart < harts_; ++hart) {
      if (mtip(hart) != delivered_timer_irq_[hart]) { next = now_; continue; }
      // An asserted timer deasserts when the unsigned mtime counter wraps,
      // unless mtimecmp is zero. A deasserted timer asserts at its compare,
      // including UINT64_MAX (which is a valid mtimecmp value).
      if (delivered_timer_irq_[hart] && compares_[hart] == 0) continue;
      const uint64_t ticks = delivered_timer_irq_[hart]
          ? never - current + 1 : compares_[hart] - current;
      const Cycle first_tick = rtc_divider_ - phase;
      if (first_tick >= never - now_) continue;
      const Cycle first_time = now_ + first_tick;
      if (ticks - 1 <= (never - 1 - first_time) / rtc_divider_)
        next = std::min(next, first_time + (ticks - 1) * rtc_divider_);
    }
  }
  for (auto id : inflight_) next = std::min(next, nodes_[id].end);
  for (auto id : pending_) {
    const auto& n = nodes_[id];
    bool ready = true;
    for (auto dep : n.op.deps) ready &= nodes_[dep].completed;
    if (!ready) continue;
    const auto& lanes = resources_.at(n.op.resource).next_issue;
    Cycle slot = *std::min_element(lanes.begin(), lanes.end());
    next = std::min(next, align(std::max({now_, n.op.earliest, slot}), n.op.issue_period));
  }
  return next;
}
std::optional<Cycle> Machine::next_event_cycle() const {
  Cycle event = next_event();
  return event == never ? std::nullopt : std::optional<Cycle>(event);
}
void Machine::on_advance(std::function<void(Cycle, Cycle)> callback) {
  advance_callback_ = std::move(callback);
}
bool Machine::run_next() {
  Cycle next = next_event();
  if (next == never) return false;
  Cycle before = now_; now_ = next;
  if (advance_callback_ && before != now_) advance_callback_(before, now_);
  refresh_interrupts();
  // Finish same-cycle operations in node order; callbacks may submit more nodes.
  // Copy callbacks before invocation: issue() may reallocate nodes_.
  std::vector<NodeId> completed;
  for (auto id : inflight_) if (nodes_[id].end == now_) completed.push_back(id);
  for (auto i : completed) {
      if(nodes_[i].cancelled)continue;
      auto callback = nodes_[i].op.on_complete;
      completing_=i;
      try {if(callback)callback();}catch(...) {completing_.reset();throw;}
      completing_.reset();
      nodes_[i].completed = true;
      nodes_[i].op.on_complete = {};
      inflight_.erase(i);
      if (nodes_[i].op.retires) ++retired_[nodes_[i].op.hart];
  }
  for (auto it = pending_.begin(); it != pending_.end();) {
    auto& n = nodes_[*it];
    if (n.op.earliest > now_ || now_ % n.op.issue_period) { ++it; continue; }
    bool ready = true;
    for (auto dep : n.op.deps) ready &= nodes_[dep].completed;
    if (!ready) { ++it; continue; }
    auto& lanes = resources_.at(n.op.resource).next_issue;
    auto lane = std::min_element(lanes.begin(), lanes.end());
    if (*lane > now_) { ++it; continue; }
    Cycle end = align(add(now_, n.op.latency), n.op.issue_period);
    Cycle available = add(now_, n.op.interval);
    n.start = now_; n.end = end; n.issued = true;
    n.lane = unsigned(lane - lanes.begin());
    *lane = available;
    inflight_.insert(n.id);
    it = pending_.erase(it);
  }
  return true;
}
void Machine::run_until(Cycle limit) {
  if (limit == never) throw std::overflow_error("modeled cycle horizon reached");
  if (limit < now_) throw std::invalid_argument("cannot reverse modeled time");
  while (next_event() <= limit && next_event() != never) run_next();
  Cycle before = now_; now_ = limit;
  if (advance_callback_ && before != now_) advance_callback_(before, now_);
}
void Machine::drain() { while (run_next()) {} }
Cycle Machine::mcycle(unsigned hart) const { check_hart(hart); return now_; }
uint64_t Machine::minstret(unsigned hart) const { check_hart(hart); return retired_[hart]; }
uint64_t Machine::mtime() const { return rtc_value_ + (now_ - rtc_origin_) / rtc_divider_; }
void Machine::write_mtime(uint64_t value) {
  rtc_value_ = value;
  // A register write changes the counter value, not the free-running tick phase.
  rtc_origin_ = now_ - now_ % rtc_divider_;
  refresh_interrupts();
}
void Machine::set_msip(unsigned hart, bool pending) {
  check_hart(hart);
  bool changed = software_irq_[hart] != pending;
  software_irq_[hart] = pending;
  if (changed && interrupt_callback_) {
    auto callback = interrupt_callback_;
    callback(hart, pending, mtip(hart));
  }
}
bool Machine::msip(unsigned hart) const { check_hart(hart); return software_irq_[hart]; }
void Machine::write_mtimecmp(unsigned hart, uint64_t value) {
  check_hart(hart); compares_[hart] = value; refresh_interrupts();
}
bool Machine::mtip(unsigned hart) const { check_hart(hart); return mtime() >= compares_[hart]; }
void Machine::on_interrupt(std::function<void(unsigned, bool, bool)> callback) {
  interrupt_callback_ = std::move(callback);
  if (interrupt_callback_) {
    for (unsigned hart = 0; hart < harts_; ++hart) {
      if (!interrupt_callback_) break;
      delivered_timer_irq_[hart] = mtip(hart);
      auto callback_copy = interrupt_callback_;
      callback_copy(hart, software_irq_[hart], delivered_timer_irq_[hart]);
    }
  }
}
void Machine::refresh_interrupts() {
  if (!interrupt_callback_) return;
  for (unsigned hart = 0; hart < harts_; ++hart) {
    if (!interrupt_callback_) break;
    bool timer = mtip(hart);
    if (timer != delivered_timer_irq_[hart]) {
      delivered_timer_irq_[hart] = timer;
      auto callback = interrupt_callback_;
      callback(hart, software_irq_[hart], timer);
    }
  }
}
void Machine::write_json(std::ostream& out, bool snapshot) const {
  if (!snapshot && (!pending_.empty() || !inflight_.empty()))
      throw std::logic_error("cannot export a final profile with unfinished operations");
  out << "{\"schema_version\":1,\"status\":\"experimental_uncalibrated\",\"cycles\":" << now_
      << ",\"harts\":" << harts_ << ",\"partial\":" << (snapshot ? "true" : "false")
      << ",\"pending_operations\":" << pending_.size() + inflight_.size() << ",\"resources\":{";
  bool first_resource = true;
  for (const auto& resource : resources_) {
    if (!first_resource) out << ',';
    first_resource = false;
    string_json(out, resource.first); out << ':' << resource.second.next_issue.size();
  }
  out << "},\"events\":[";
  bool first = true;
  for (const auto& n : nodes_) {
    if (!n.completed && !n.cancelled && (!snapshot || !n.issued || n.start >= now_)) continue;
    if (!first) out << ',';
    first = false;
    out << "{\"id\":" << n.id << ",\"hart\":" << n.op.hart << ",\"name\":";
    string_json(out, n.op.name); out << ",\"resource\":"; string_json(out, n.op.resource);
    out << ",\"region\":"; string_json(out, n.op.region);
    out << ",\"completed\":" << (n.completed ? "true" : "false")
        << ",\"pc\":" << n.op.pc << ",\"start\":" << n.start << ",\"end\":" << std::min(n.end, now_)
        << ",\"submitted\":" << n.submitted << ",\"lane\":" << n.lane
        << ",\"bytes\":" << n.op.bytes << ",\"macs\":" << n.op.macs << ",\"deps\":[";
    for (size_t d = 0; d < n.op.deps.size(); ++d) { if (d) out << ','; out << n.op.deps[d]; }
    out << ']';
    if(n.cancelled) {
      out<<",\"cancelled\":true,\"issued\":"<<(n.issued?"true":"false")<<",\"cancel_cycle\":"<<n.cancel_cycle<<",\"cancel_reason\":";
      string_json(out,n.cancel_reason);
    }
    if(n.squashed) {
      out<<",\"squashed\":true,\"squash_cycle\":"<<n.squash_cycle<<",\"squash_reason\":";
      string_json(out,n.squash_reason);
    }
    out << '}';
  }
  out << "]}";
}

Memory::Memory(unsigned harts, uint64_t reservation_granule)
    : granule_(reservation_granule), reservations_(harts) {
  if (!harts || !granule_ || (granule_ & (granule_ - 1)))
    throw std::invalid_argument("explicit power-of-two reservation granule required");
}
void Memory::map(Region region) {
  if (!region.size || region.size - 1 > never - region.base)
    throw std::invalid_argument("invalid memory region");
  for (const auto& old : regions_)
    if (region.base <= old.base + old.size - 1 && old.base <= region.base + region.size - 1)
      throw std::invalid_argument("overlapping memory region");
  regions_.push_back(std::move(region));
}
const Region& Memory::check(uint64_t address, unsigned bytes, char mode, bool atomic) const {
  if (!bytes || bytes > 8 || (bytes & (bytes - 1)) || bytes - 1 > never - address)
    throw std::invalid_argument("invalid access size/address");
  if (atomic && ((bytes != 4 && bytes != 8) || address % bytes))
    throw std::runtime_error("misaligned/invalid atomic access");
  for (const auto& r : regions_) {
    if (address < r.base || address - r.base >= r.size || bytes > r.size - (address - r.base)) continue;
    if ((mode == 'r' && !r.read) || (mode == 'w' && !r.write) ||
        (mode == 'x' && !r.execute) || (atomic && !r.atomics)) break;
    return r;
  }
  throw std::runtime_error("unmapped or denied memory access");
}
uint64_t Memory::load(uint64_t address, unsigned bytes, bool instruction) const {
  check(address, bytes, instruction ? 'x' : 'r');
  uint64_t result = 0;
  for (unsigned i = 0; i < bytes; ++i) {
    auto pos = data_.find(address + i);
    if (pos != data_.end()) result |= uint64_t(pos->second) << (i * 8);
  }
  return result;
}
void Memory::invalidate(uint64_t address, unsigned bytes) {
  uint64_t first = address / granule_, last = (address + bytes - 1) / granule_;
  for (auto& r : reservations_) {
    if (r.valid && first <= (r.address + r.bytes - 1) / granule_ && r.address / granule_ <= last)
      r.valid = false;
  }
}
void Memory::store(uint64_t address, unsigned bytes, uint64_t value) {
  check(address, bytes, 'w');
  invalidate(address, bytes);
  for (unsigned i = 0; i < bytes; ++i) data_[address + i] = uint8_t(value >> (i * 8));
}
uint64_t Memory::lr(unsigned hart, uint64_t address, unsigned bytes) {
  if (hart >= reservations_.size()) throw std::out_of_range("invalid hart");
  check(address, bytes, 'r', true);
  uint64_t value = load(address, bytes);
  reservations_[hart] = Reservation{true, address, bytes};
  return value;
}
bool Memory::sc(unsigned hart, uint64_t address, unsigned bytes, uint64_t value) {
  if (hart >= reservations_.size()) throw std::out_of_range("invalid hart");
  check(address, bytes, 'w', true);
  auto r = reservations_[hart];
  reservations_[hart].valid = false;
  bool success = r.valid && r.address == address && r.bytes == bytes;
  if (success) store(address, bytes, value);
  return success;
}
uint64_t Memory::amo_add(uint64_t address, unsigned bytes, uint64_t value) {
  check(address, bytes, 'r', true); check(address, bytes, 'w', true);
  uint64_t old = load(address, bytes);
  store(address, bytes, old + value);
  return old;
}
}  // namespace iris
