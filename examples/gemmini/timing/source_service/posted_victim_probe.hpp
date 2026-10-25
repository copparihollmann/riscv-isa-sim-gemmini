#ifndef GEMMINI_POSTED_VICTIM_PROBE_HPP
#define GEMMINI_POSTED_VICTIM_PROBE_HPP
#include "registered_transport.hpp"
#include <map>
#include <set>
#include <tuple>

namespace gemmini_annotated_spike {
// Selected one-client inclusive-cache victim rprobe (not target-line pprobe).
// No Engine booking, Directory lookup, RNG step, cache mutation or outer-C
// service occurs here. The owner supplies those actors and exact identities.
class PostedVictimProbe {
 public:
  using Q = merlin_timing::PostedTimeline;
  using Token = Q::Token;
  using Cycle = merlin_timing::Cycle;
  struct Identity {
    std::uint64_t line, set, way, generation;
  };
  struct Law {
    // Independently selected source contract; never inferred from capacity.
    std::string source_identity;
    std::size_t sets, ways, line_bytes, inner_beat_bytes, outer_beat_bytes;
    Cycle lookup_stages, dirty_enter, data_pipeline, metadata_stages;
  };
  struct Guards {
    std::optional<Cycle> client_ready;
    // The original owner must establish these over the private transaction.
    // They are not a fixed fee for unobserved CPU/cache activity.
    bool cpu_s1_s2_closed = false;
    bool grant_and_postgrant_closed = false;
    bool release_and_releaseack_closed = false;
    bool lrsc_closed = false;
    bool private_data_and_metadata_ports_owned = false;
  };
  struct Request {
    Identity victim;
    std::uint64_t target_line;
    bool target_private_hit, llc_dirty, private_dirty;
    Law law;
    Guards guards;
  };
  struct Result {
    Identity victim;
    std::uint64_t target_line;
    std::string source_identity;
    bool effective_dirty;
    Token sourceb_request, b_accepted, private_last_accepted, first_response, last_response;
    Token metadata_done, client_released;
    std::vector<Token> beat_publication;
    std::size_t line_bytes, inner_beat_bytes, outer_beat_bytes;
    // MSHR first response opens release, but NEVER publishes all data bytes.
    // SourceC's own set/way SourceD evict_safe and queue readiness remain owned
    // by its caller; the helper supplies only the original victim dependencies.
    std::vector<Token> read_dependencies(std::size_t outer_beat) const {
      if (outer_beat >= line_bytes / outer_beat_bytes)
        throw std::invalid_argument("victim SourceC beat outside original line");
      std::vector<Token> out{first_response};
      if (!beat_publication.empty())
        out.push_back(beat_publication.at(outer_beat * outer_beat_bytes / inner_beat_bytes));
      return out;
    }
  };
  // Called at the actual non-flow SinkC Queue1 output, not at a future booked
  // cycle. Complete `stored` only at the settled SRAM arbiter's real write.
  using Publish = std::function<void(std::size_t, std::uint64_t, std::uint64_t, Cycle, Token)>;

 private:
  struct Pending { Request request; Result result; };
  Q& q_;
  Publish publish_;
  PostedRegisteredTransport inner_c_;
  PostedRegisteredTransport sinkc_;
  std::optional<Token> sourceb_free_, client_free_;
  std::optional<Cycle> last_arrival_;
  std::set<std::tuple<std::uint64_t,std::uint64_t,std::uint64_t>> owners_;
  std::size_t live_ = 0, peak_ = 0;

  Token token() {
    auto t = q_.token();
    if (!t) throw std::runtime_error("victim probe token bound");
    return *t;
  }
  bool valid(const Request& r, Cycle at) {
    const auto& l = r.law;
    const auto& g = r.guards;
    if (l.source_identity.empty() || !l.sets || !l.ways || l.line_bytes != 64 ||
        l.inner_beat_bytes != 16 || l.outer_beat_bytes != 8 || l.lookup_stages != 2 ||
        l.dirty_enter != 1 || l.data_pipeline != 2 || l.metadata_stages != 1)
      return q_.fail("victim probe differs from explicitly selected one-client source law");
    if (!g.client_ready || !g.cpu_s1_s2_closed || !g.grant_and_postgrant_closed ||
        !g.release_and_releaseack_closed || !g.lrsc_closed || !g.private_data_and_metadata_ports_owned)
      return q_.fail("victim probe has unknown Rocket readiness or private-port ownership");
    if (r.target_private_hit || r.target_line == r.victim.line)
      return q_.fail("cold TARGET private hit is not a victim rprobe");
    if (!r.victim.generation || r.victim.way >= l.ways || r.victim.set != r.victim.line % l.sets ||
        r.target_line % l.sets != r.victim.set || r.victim.line > (UINT64_MAX - 63) / 64 ||
        r.target_line > (UINT64_MAX - 63) / 64)
      return q_.fail("victim probe lost original tag/set/way/generation identity");
    if (at > UINT64_MAX - 32 || *g.client_ready > UINT64_MAX - 32 ||
        (last_arrival_ && at < *last_arrival_))
      return q_.fail("victim probe has nonmonotone or overflowing arrival");
    if (live_ >= 16 || owners_.count({r.victim.set,r.victim.way,r.victim.generation}))
      return q_.fail("victim probe has duplicate or unbounded MSHR ownership");
    return true;
  }
  void respond(const std::shared_ptr<Pending>& p, std::size_t beat, Cycle at) {
    const bool dirty = p->request.private_dirty;
    const auto beats = dirty ? p->result.beat_publication.size() : 1;
    // SinkC response is qualified by C acceptance / Queue ENQUEUE readiness
    // (SinkC107/134), not by downstream SRAM publication. MSHR first/last
    // registers update one edge later (MSHR470--473).
    if (!beat || beat + 1 == beats)
      q_.post(at + 1, {}, [p,beat,beats](Q& q, Cycle) {
        if (!beat) q.complete(p->result.first_response);
        if (beat + 1 == beats) q.complete(p->result.last_response);
      }, Q::Kind::response_beat);
  }
  void private_response(const std::shared_ptr<Pending>& p, std::size_t beat, Cycle at) {
    // Selected innerBuf.c is Queue2 non-flow/non-pipe (SinkC73, FIR54060),
    // separate from the Queue1 pipe in front of the SRAM port (SinkC97).
    auto captured = inner_c_.push([this,p,beat](Cycle now, Token consumed) {
      if (!p->request.private_dirty) {
        respond(p,beat,now);q_.complete(consumed);return;
      }
      auto enqueued = sinkc_.push([this,p,beat](Cycle now, Token stored_input) {
        auto stored = token();
        const auto address = p->request.victim.line * 64 + beat * 16;
        publish_(beat,address,0xffff,now,stored);
        q_.post(now,{stored},[p,beat,stored_input](Q& q, Cycle) {
          q.complete(p->result.beat_publication.at(beat));
          q.complete(stored_input);
        },Q::Kind::local_publish);
      },now);
      q_.post(now,{enqueued},[this,p,beat,consumed](Q&,Cycle accepted) {
        respond(p,beat,accepted);q_.complete(consumed);
      },Q::Kind::response_beat);
    },at);
    q_.post(at,{captured},[this,p,beat](Q&,Cycle accepted) {
      const auto beats=p->request.private_dirty?p->result.beat_publication.size():1;
      if (beat+1==beats) {
        q_.complete(p->result.private_last_accepted);
        q_.post(accepted+p->request.law.metadata_stages,{},[p](Q& q,Cycle) {
          // DCache906--912 follows the private channel's last acceptance,
          // independently of later SinkC/LLC response and publication.
          q.complete(p->result.metadata_done);
        },Q::Kind::command_retire);
      } else {
        q_.post(accepted+1,{},[this,p,beat](Q&,Cycle next) {
          private_response(p,beat+1,next);
        },Q::Kind::response_beat);
      }
    },Q::Kind::response_beat);
  }
  void start(const std::shared_ptr<Pending>& p, Cycle at) {
    q_.complete(p->result.b_accepted);
    // DCache s1/s2 lookup and dirty reply/data pipeline are selected facts,
    // usable only under the explicit closed idle/ready and port premise.
    Cycle first = at + p->request.law.lookup_stages;
    if (p->request.private_dirty) {
      first += p->request.law.dirty_enter + p->request.law.data_pipeline;
      q_.post(first,{},[this,p](Q&,Cycle now) { private_response(p,0,now); },Q::Kind::response_beat);
    } else {
      q_.post(first,{},[this,p](Q&,Cycle now) { private_response(p,0,now); },Q::Kind::response_beat);
    }
  }

 public:
  PostedVictimProbe(Q& q, Publish publish)
      : q_(q), publish_(std::move(publish)), inner_c_(q,{{2,false}}), sinkc_(q,{{1,true}}) {
    if (!publish_) throw std::invalid_argument("victim probe requires actual SinkC SRAM publication owner");
  }
  std::optional<Result> push(const Request& request, Cycle at) {
    if (!valid(request,at)) return {};
    last_arrival_ = at;
    Result out{request.victim,request.target_line,request.law.source_identity,
      request.llc_dirty || request.private_dirty,token(),token(),token(),token(),token(),token(),token(),{},64,16,8};
    if (request.private_dirty) for (unsigned i=0;i<4;++i) out.beat_publication.push_back(token());
    auto p=std::make_shared<Pending>(Pending{request,out});
    auto b_free=token();
    std::vector<Token> source_wait,client_wait;
    if (sourceb_free_) source_wait.push_back(*sourceb_free_);
    if (client_free_) client_wait.push_back(*client_free_);
    sourceb_free_=b_free; client_free_=out.client_released;
    ++live_; peak_=std::max(peak_,live_);
    owners_.insert({request.victim.set,request.victim.way,request.victim.generation});
    q_.post(at,std::move(source_wait),[this,p,b_free,client_wait=std::move(client_wait)](Q&,Cycle now) mutable {
      q_.complete(p->result.sourceb_request);
      // Selected SourceB.io.b is directly wired (no guessed B queue).
      q_.post(std::max(now,*p->request.guards.client_ready),std::move(client_wait),
        [this,p,b_free](Q&,Cycle accepted) {
          start(p,accepted);
          // SourceB.remain clears on B.fire; registered req.ready next edge.
          q_.post(accepted+1,{},[b_free](Q& q,Cycle) { q.complete(b_free); },Q::Kind::source_arrival);
        },Q::Kind::source_arrival);
    },Q::Kind::source_arrival);
    q_.post(at,{out.metadata_done},[p](Q& q,Cycle accepted) {
      // DCache912 writes release_state=s_ready on metadata fire. Like the
      // SourceB and MSHR registers, this enables the next edge, not another
      // B handshake retroactively on that already accepted metadata edge.
      q.post(accepted+1,{},[p](Q& q,Cycle) {q.complete(p->result.client_released);},Q::Kind::command_retire);
    },Q::Kind::command_retire);
    std::vector<Token> finished=out.beat_publication;
    finished.push_back(out.metadata_done); finished.push_back(out.last_response); finished.push_back(b_free);
    finished.push_back(out.client_released);
    q_.post(at,std::move(finished),[this,p](Q&,Cycle) {
      if (!live_ || !owners_.erase({p->request.victim.set,p->request.victim.way,p->request.victim.generation})) {
        q_.fail("victim probe ownership underflow"); return;
      }
      --live_;
    },Q::Kind::completion);
    return out;
  }
  bool busy() const { return live_ || inner_c_.busy() || sinkc_.busy(); }
  std::size_t peak() const { return peak_; }
};
}
#endif
