#ifndef GEMMINI_EXECUTE_MESH_TAGS_HPP
#define GEMMINI_EXECUTE_MESH_TAGS_HPP
#include <algorithm>
#include <cstdint>
#include <deque>
#include <optional>
#include <stdexcept>
#include <vector>
namespace gemmini_annotated_spike {
// Selected MeshWithDelays / Mesh / TagQueue. DIM16, tile1, tile_latency0,
// output_delay1, one shifter bank: input row -> response after16+1+15 edges.
// Request ids wrap at5; both original queues have6 entries and no flow/pipe.
class ExecuteMeshTags {
 public:
 struct Row {std::uint64_t owner;unsigned row,total;bool last;};
 struct Output:Row {std::optional<std::uint64_t>tag_owner;};
 struct Edge {bool request_ready;std::vector<Output>outputs;};
 private:
 struct Tag {unsigned id;std::optional<std::uint64_t>owner;};
 struct Total {unsigned id,rows;};
 struct InFlight {std::uint64_t at;Row row;unsigned id;};
 std::deque<Tag>tags_;std::deque<Total>totals_;std::deque<InFlight>pipeline_;
 unsigned matmul_id_=0,current_id_=0,tag_peak_=0,total_peak_=0;
 std::optional<std::uint64_t>current_owner_,last_edge_;
 bool admission_ready_=false,admitted_=false;
 public:
 unsigned tag_peak()const{return tag_peak_;}
 unsigned total_peak()const{return total_peak_;}
 bool pending()const{return !pipeline_.empty();}
 bool live_tag()const{for(const auto&t:tags_)if(t.owner)return true;return false;}
 Edge edge(std::uint64_t at,std::optional<Row>row={}){
   if(last_edge_&&(at<=*last_edge_||(at!=*last_edge_+1&&!pipeline_.empty())))throw std::logic_error("mesh clock skipped a live source edge");
   last_edge_=at;admitted_=false;admission_ready_=tags_.size()<6&&totals_.size()<6;
   Edge result{admission_ready_,{}};
   // Readiness sees old registered length: a FULL queue cannot recycle a
   // just-dequeued credit on the same edge.
   while(!pipeline_.empty()&&pipeline_.front().at==at){
     auto output=pipeline_.front();pipeline_.pop_front();std::optional<std::uint64_t>tag;
     if(!tags_.empty()&&tags_.front().id==output.id){tag=tags_.front().owner;if(output.row.last)tags_.pop_front();}
     auto total=16u;if(!totals_.empty()&&totals_.front().id==output.id){total=totals_.front().rows;if(output.row.last)totals_.pop_front();}
     if(total!=output.row.total)throw std::logic_error("original mesh total_rows identity mismatch");
     result.outputs.push_back({output.row,tag});
   }
   if(!pipeline_.empty()&&pipeline_.front().at<at)throw std::logic_error("mesh output edge lost");
   if(row){
     if(!current_owner_||*current_owner_!=row->owner||row->total<4||row->total>16||row->row>=row->total||row->last!=(row->row+1==row->total))
       throw std::logic_error("mesh input row lost its original request");
     pipeline_.push_back({at+32,*row,current_id_});
     if(pipeline_.size()>32)throw std::logic_error("mesh delay registers exceeded physical row capacity");
   }
   return result;
 }
 void accept(std::uint64_t owner,unsigned rows,std::optional<std::uint64_t>tag_owner={}){
   if(!last_edge_||!admission_ready_||admitted_||rows<4||rows>16)
     throw std::logic_error("mesh request accepted without original finite tag/row-count credit");
   admitted_=true;tags_.push_back({(matmul_id_+2)%5,tag_owner});
   current_id_=(matmul_id_+1)%5;totals_.push_back({current_id_,rows});
   matmul_id_=current_id_;current_owner_=owner;
   tag_peak_=std::max(tag_peak_,unsigned(tags_.size()));total_peak_=std::max(total_peak_,unsigned(totals_.size()));
 }
};
}
#endif
