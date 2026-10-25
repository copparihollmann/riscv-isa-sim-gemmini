#ifndef GEMMINI_STREAMED_READOUT_HPP
#define GEMMINI_STREAMED_READOUT_HPP
#include "provider.hpp"
#include <deque>

namespace gemmini_annotated_spike {
// Selected non-normalizing, aligned full ACC row path. Memory service remains
// the existing model; this network supplies arrivals and finite backpressure.
struct ReadoutStreamConfig {
  std::size_t dispatch, norm_metadata, norm_passthrough, scale_metadata, issue_metadata;
  std::size_t scale_stages, transactions, beat_bytes;
};
struct ReadoutStreamResult {
  std::optional<Cycle> complete;
  std::vector<Cycle> scale_accept, writer_accept, memory_start, memory_complete;
  std::size_t max_transactions=0, max_issue_metadata=0;
};
inline ReadoutStreamResult stream_readout(const ReadoutStreamConfig &c,
    std::size_t rows, std::size_t row_bytes, Cycle begin,
    const std::function<Result(std::size_t,Cycle,Cycle)> &memory) {
  ReadoutStreamResult out;
  if (!rows || rows>256 || !c.beat_bytes || !row_bytes || row_bytes%c.beat_bytes ||
      !c.dispatch || !c.norm_metadata || !c.norm_passthrough || !c.scale_metadata ||
      !c.issue_metadata || !c.scale_stages || c.scale_stages>256 ||
      c.transactions<2 || c.transactions>256 ||
      begin>std::numeric_limits<Cycle>::max()-1048576) return out;
  const std::size_t beats=row_bytes/c.beat_bytes;
  if (beats>256) return out;
  struct Beat {std::size_t row, index;};
  std::deque<std::size_t> dispatch,norm;
  std::optional<std::size_t> response,writer;
  std::vector<std::optional<std::size_t>> scale(c.scale_stages);
  std::optional<Beat> tlb,translated;
  std::vector<bool> live(rows,false),reserved(rows,false);
  std::vector<std::optional<Cycle>> starts(rows),complete(rows);
  std::size_t next=0,issued_metadata=0,norm_metadata=0,scale_metadata=0;
  std::size_t next_beat=0,finished=0;
  out.scale_accept.resize(rows);out.writer_accept.resize(rows);
  out.memory_start.resize(rows);out.memory_complete.resize(rows);
  for (Cycle t=begin;t<begin+1048576;++t) {
    // D acknowledgement updates xactBusy at the edge, so a credit is reusable
    // on the following cycle. No credit is released at A submission.
    for(std::size_t r=0;r<rows;++r) if(complete[r] && *complete[r]<t) live[r]=false;
    const auto live_count=static_cast<std::size_t>(std::count(live.begin(),live.end(),true));
    const auto old_dispatch=dispatch.size(),old_norm=norm.size();
    const auto old_norm_meta=norm_metadata,old_scale_meta=scale_metadata;
    if(translated) {
      const auto r=translated->row;
      if(!reserved[r]) {
        const auto result=memory(r,t,beats);
        if(!result.start || !result.ready || *result.start<t ||
            *result.start>std::numeric_limits<Cycle>::max()-beats ||
            *result.ready<*result.start+beats) return out;
        starts[r]=result.start;complete[r]=result.ready;reserved[r]=true;
        out.memory_start[r]=*result.start;out.memory_complete[r]=*result.ready;
      }
      if(t>=*starts[r]) {
        if(translated->index+1==beats) {
          // The memory contract may not acknowledge a transaction before its
          // last accepted beat. Unexplained downstream gaps stay unresolved.
          if(*complete[r]<t+1)return out;
          ++finished;
        }
        translated.reset();
      }
    }
    // Both selected translation queues are one-entry registered pipe queues.
    // A miss/retry is outside this explicit translation-hit approximation.
    if(!translated && tlb) {translated=tlb;tlb.reset();}
    if(writer && !tlb && live_count<c.transactions) {
      const auto r=*writer;
      if(!next_beat) live[r]=true;
      tlb=Beat{r,next_beat++};
      if(next_beat==beats) {writer.reset();next_beat=0;}
    }
    // StreamWriter can capture the next row on its last untranslated beat.
    // Newly captured data first issues a beat on the following cycle.
    if(!writer && scale.back()) {
      writer=*scale.back();out.writer_accept[*writer]=t;
      scale.back().reset();--issued_metadata;
    }
    for(std::size_t s=scale.size()-1;s>0;--s)
      if(!scale[s] && scale[s-1]) {scale[s]=scale[s-1];scale[s-1].reset();}
    if(!scale[0] && !norm.empty() && issued_metadata<c.issue_metadata) {
      const auto r=norm.front();norm.pop_front();--scale_metadata;
      scale[0]=r;++issued_metadata;out.scale_accept[r]=t;
    }
    // Normalizer passthrough is a TWO-entry registered queue, not a wire.
    if(response && old_norm<c.norm_passthrough && old_scale_meta<c.scale_metadata) {
      norm.push_back(*response);response.reset();--norm_metadata;++scale_metadata;
    }
    // ACC synchronous read response is one cycle, with a one-entry flow/pipe
    // response queue. Execute/ACC conflicts are held by the enclosing model.
    if(!response && !dispatch.empty() && old_norm_meta<c.norm_metadata) {
      response=dispatch.front();dispatch.pop_front();++norm_metadata;
    }
    if(next<rows && old_dispatch<c.dispatch) dispatch.push_back(next++);
    out.max_transactions=std::max(out.max_transactions,
        static_cast<std::size_t>(std::count(live.begin(),live.end(),true)));
    out.max_issue_metadata=std::max(out.max_issue_metadata,issued_metadata);
    if(finished==rows) {
      Cycle end=t+1;
      for(const auto &r:complete) {if(!r)return out;end=std::max(end,*r);}
      out.complete=end;return out;
    }
  }
  return out; // bounded observer work: unresolved, never a guessed completion
}
} // namespace gemmini_annotated_spike
#endif
