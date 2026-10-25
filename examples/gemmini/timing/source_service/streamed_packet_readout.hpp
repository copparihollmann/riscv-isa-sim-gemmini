#ifndef GEMMINI_STREAMED_PACKET_READOUT_HPP
#define GEMMINI_STREAMED_PACKET_READOUT_HPP
#include "streamed_readout.hpp"
#include "writer_packets.hpp"
namespace gemmini_annotated_spike {
// Existing ACC/scale arrival network, exact StreamWriter packets and separate
// xactBusy credits. Only PutFull packets; no masked SourceD/RMW assumption.
inline ReadoutStreamResult stream_packet_readout(const ReadoutStreamConfig &c,
    const std::vector<std::vector<WriterPacket>> &packets,Cycle begin,
    const std::function<Result(std::size_t,std::size_t,Cycle,Cycle)> &memory) {
  ReadoutStreamResult out;
  const auto rows=packets.size();std::size_t packet_count=0;
  if(!rows || rows>256 || !c.beat_bytes || !c.dispatch || !c.norm_metadata ||
      !c.norm_passthrough || !c.scale_metadata || !c.issue_metadata ||
      !c.scale_stages || c.scale_stages>256 || c.transactions<2 || c.transactions>256 ||
      begin>std::numeric_limits<Cycle>::max()-1048576)return out;
  std::vector<std::size_t> offsets;
  for(const auto &row:packets) {
    offsets.push_back(packet_count);
    if(row.empty())return out;
    for(const auto &p:row) {
      if(!p.full || !p.bytes || p.bytes%c.beat_bytes || p.bytes/c.beat_bytes>256)return out;
      ++packet_count;
    }
  }
  if(packet_count>4096)return out;
  struct Beat {std::size_t row,packet,index;};
  std::deque<std::size_t> dispatch,norm;
  std::size_t response=rows,writer=rows;
  std::vector<std::optional<std::size_t>> scale(c.scale_stages);
  std::deque<Beat> tlb,translated;
  std::vector<bool> live(packet_count,false),reserved(packet_count,false);
  std::vector<std::optional<Cycle>> starts(packet_count),complete(packet_count);
  std::size_t next=0,issued_metadata=0,norm_metadata=0,scale_metadata=0;
  std::size_t next_packet=0,next_beat=0,finished=0;
  out.scale_accept.resize(rows);out.writer_accept.resize(rows);
  out.memory_start.resize(packet_count);out.memory_complete.resize(packet_count);
  for(Cycle t=begin;t<begin+1048576;++t) {
    for(std::size_t q=0;q<packet_count;++q)if(complete[q]&&*complete[q]<t)live[q]=false;
    const auto live_count=static_cast<std::size_t>(std::count(live.begin(),live.end(),true));
    const auto old_dispatch=dispatch.size(),old_norm=norm.size();
    const auto old_norm_meta=norm_metadata,old_scale_meta=scale_metadata;
    if(!translated.empty()) {
      const auto &active=translated.front();
      const auto r=active.row,p=active.packet,q=offsets[r]+p;
      const auto beats=packets[r][p].bytes/c.beat_bytes;
      if(!reserved[q]) {
        const auto result=memory(r,p,t,beats);
        if(!result.start || !result.ready || *result.start<t ||
            *result.start>std::numeric_limits<Cycle>::max()-beats ||
            *result.ready<*result.start+beats)return out;
        starts[q]=result.start;complete[q]=result.ready;reserved[q]=true;
        out.memory_start[q]=*result.start;out.memory_complete[q]=*result.ready;
      }
      if(t>=*starts[q]) {
        if(active.index+1==beats) {
          if(*complete[q]<t+1)return out;
          ++finished;
        }
        translated.pop_front();
      }
    }
    if(translated.empty()&&!tlb.empty()){translated.push_back(tlb.front());tlb.pop_front();}
    // StreamWriter tests !xactBusy.andR for every beat, including an existing
    // multibeat transaction; retain that conservative literal gate.
    if(writer!=rows&&tlb.empty()&&live_count<c.transactions) {
      const auto r=writer,q=offsets[r]+next_packet;
      if(!next_beat)live[q]=true;
      tlb.push_back(Beat{r,next_packet,next_beat++});
      if(next_beat==packets[r][next_packet].bytes/c.beat_bytes) {
        next_beat=0;
        if(++next_packet==packets[r].size()){writer=rows;next_packet=0;}
      }
    }
    if(writer==rows&&scale.back()) {
      writer=*scale.back();out.writer_accept[writer]=t;
      scale.back().reset();--issued_metadata;
    }
    for(std::size_t s=scale.size()-1;s>0;--s)
      if(!scale[s]&&scale[s-1]){scale[s]=scale[s-1];scale[s-1].reset();}
    if(!scale[0]&&!norm.empty()&&issued_metadata<c.issue_metadata) {
      const auto r=norm.front();norm.pop_front();--scale_metadata;
      scale[0]=r;++issued_metadata;out.scale_accept[r]=t;
    }
    if(response!=rows&&old_norm<c.norm_passthrough&&old_scale_meta<c.scale_metadata) {
      norm.push_back(response);response=rows;--norm_metadata;++scale_metadata;
    }
    if(response==rows&&!dispatch.empty()&&old_norm_meta<c.norm_metadata) {
      response=dispatch.front();dispatch.pop_front();++norm_metadata;
    }
    if(next<rows&&old_dispatch<c.dispatch)dispatch.push_back(next++);
    out.max_transactions=std::max(out.max_transactions,
        static_cast<std::size_t>(std::count(live.begin(),live.end(),true)));
    out.max_issue_metadata=std::max(out.max_issue_metadata,issued_metadata);
    if(finished==packet_count) {
      Cycle end=t+1;
      for(const auto &p:complete){if(!p)return out;end=std::max(end,*p);}
      out.complete=end;return out;
    }
  }
  return out;
}
}
#endif
