#include "fast_shuttle_predictor.hpp"
#include "VShuttleBTB.h"
#include "verilated.h"
#include <iostream>
#include <memory>
#include <stdexcept>
using Model=iris::frontend::FastShuttlePredictor;
int main(int argc,char**argv){
 if(argc!=2)throw std::invalid_argument("seed required");VerilatedContext context;context.randSeed(std::stoul(argv[1]));context.randReset(2);context.threads(1);auto dut=std::make_unique<VShuttleBTB>(&context);auto&d=*dut;Model model;uint64_t random=0x9e3779b97f4a7c15ULL^std::stoul(argv[1]);auto rng=[&]{random^=random<<13;random^=random>>7;random^=random<<17;return random;};unsigned active=0,checks=0;
 for(unsigned edge=0;edge<200016;++edge){
  Model::Inputs in;in.reset=edge<16;const auto t=rng();in.pc=((t&63)<<3)|((t&256)?0x80000000ULL:0x10000ULL);in.advance=bool(t&128);in.flush=(t%127)==0;
  const auto predicted=model.evaluate(in);const bool update=t%3==0;in.btb={update,true,bool(t&512),predicted.valid?predicted.entry:32,unsigned((t>>12)&3),in.pc,((t>>20)&63)*8+((t&1024)?0x80000000ULL:0x10000ULL),in.pc+((t>>18)&3)*2};
  in.bht={update,true,bool(t&512),bool(t&2048),predicted.history,predicted.value,in.pc};
  d.reset=in.reset;d.io_req_bits_addr=in.pc;d.io_flush=in.flush;d.io_btb_update_valid=in.btb.valid;d.io_btb_update_bits_prediction_entry=in.btb.prediction_entry;d.io_btb_update_bits_pc=in.btb.pc;d.io_btb_update_bits_target=in.btb.target;d.io_btb_update_bits_isValid=in.btb.is_valid;d.io_btb_update_bits_br_pc=in.btb.branch_pc;d.io_btb_update_bits_cfiType=in.btb.cfi_type;d.io_btb_update_bits_mispredict=in.btb.mispredict;
  d.io_bht_update_valid=in.bht.valid;d.io_bht_update_bits_prediction_history=in.bht.history;d.io_bht_update_bits_prediction_value=in.bht.value;d.io_bht_update_bits_pc=in.bht.pc;d.io_bht_update_bits_branch=in.bht.branch;d.io_bht_update_bits_taken=in.bht.taken;d.io_bht_update_bits_mispredict=in.bht.mispredict;d.io_bht_advance_valid=in.advance&&predicted.valid;d.io_bht_advance_bits_bht_value=predicted.value;d.clock=0;d.eval();
  if(edge>=16){
   auto equal=[&](uint64_t got,uint64_t expected,const char*field){++checks;if(got!=expected)throw std::runtime_error(std::string("predictor ")+field+" edge="+std::to_string(edge)+" got="+std::to_string(got)+" expected="+std::to_string(expected));};
   equal(predicted.valid,d.io_resp_valid,"valid");equal(predicted.history,d.io_resp_bits_bht_history,"history");equal(predicted.value,d.io_resp_bits_bht_value,"counter");
   if(predicted.valid){++active;equal(predicted.taken,d.io_resp_bits_taken,"taken");equal(predicted.entry,d.io_resp_bits_entry,"entry");equal(predicted.index,d.io_resp_bits_bridx,"bridx");equal(predicted.target,d.io_resp_bits_target,"target");}
  }
  model.commit(in);d.clock=1;d.eval();context.timeInc(1);d.clock=0;d.eval();context.timeInc(1);
 }
 std::cout<<"{\"pass\":true,\"edges\":200000,\"checks\":"<<checks<<",\"active_predictions\":"<<active<<",\"duplicate_clear_edges\":"<<model.duplicate_clear_edges()<<"}\n";
}
