#include "execute_operand_pipeline.hpp"
#include "execute_mesh_tags.hpp"
#include <cassert>
#include <iostream>
#include <map>
using namespace gemmini_annotated_spike;
using C=ExecuteOperandCounters;
int main(){
 // Real preload C tag appears on the following compute's row stream. The
 // final request's garbage tag may remain resident, exactly as in RTL.
 ExecuteOperandPipeline source(C({C::Operand{},C::Operand{},C::Operand{0,0,true,true}},4,16,4096,4),4);
 MeshOperandRegisters mesh(4);ExecuteMeshTags tags;unsigned phase=0,clock=0;std::map<std::uint64_t,unsigned>output_rows;bool full=false;
 do{
   if(source.source_consumed()&&phase<19){++phase;source.begin(C({C::Operand{},C::Operand{},C::Operand{0,0,true,true}},4,16,4096,4),phase);}
   std::optional<ExecuteMeshTags::Row>row;if(mesh.row_fire())row=ExecuteMeshTags::Row{mesh.owner(),mesh.row(),4,mesh.last()};
   auto tag_edge=tags.edge(clock,row);if(!tag_edge.request_ready)full=true;
   for(auto output:tag_edge.outputs){assert(output.row==output_rows[output.owner]++);if(output.owner==0)assert(!output.tag_owner);else assert(output.tag_owner==std::optional<std::uint64_t>{output.owner-1});}
   auto edge=source.step({true,true,true,true},mesh.signals(tag_edge.request_ready));
   if(edge.request_fire)tags.accept(edge.request_owner,edge.request_rows,edge.request_owner);
   mesh.step(edge);++clock;assert(clock<250);
 }while(phase<19||!source.source_consumed()||!source.empty()||mesh.busy()||tags.pending());
 assert(full&&tags.tag_peak()==6&&tags.total_peak()<=6&&output_rows.size()==20);
 for(auto item:output_rows)assert(item.second==4);
 // Last real tag has no following compute yet; it remains live and cannot
 // be completed by a software drain that invents a subsequent mesh request.
 assert(tags.live_tag());
 std::cout<<"source five matmul ids, six original tag/row-count slots, registered full release and exact delayed stream ownership PASS\n";
}
