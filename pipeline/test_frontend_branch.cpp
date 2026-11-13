#include "frontend_branch.hpp"
#include <array>
#include <fstream>
#include <iostream>
#include <stdexcept>

using iris::frontend::ShuttleBranch;
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("actual MEM branch corpus required");
  std::ifstream file(argv[1]);std::array<uint64_t,38> row{};uint64_t rows=0,selected=0,checks=0,jalr=0,conditional=0,false_prediction=0,short_pairs=0;
  while(file>>row[0]) {
    for(unsigned i=1;i<row.size();++i)if(!(file>>row[i]))throw std::runtime_error("truncated actual branch corpus");
    std::array<ShuttleBranch::Uop,2> packet;
    for(unsigned lane=0;lane<2;++lane) {
      auto& u=packet[lane];const unsigned i=lane*14;
      u.valid=row[i];u.branch=row[i+1];u.jal=row[i+2];u.jalr=row[i+3];u.sfence=row[i+4];u.expanded=row[i+5];u.pc=row[i+6];u.wdata=row[i+7];
      u.compressed=row[i+8];u.taken=row[i+9];u.predicted_valid=row[i+10];u.predicted_pc=row[i+11];u.ras_head=row[i+12];u.sfb_branch=row[i+13];
    }
    const auto got=ShuttleBranch::resolve(packet);
    if(got.selected!=bool(row[28]) || got.predictor_update!=bool(row[29]))throw std::runtime_error("actual MEM selection/update differs row="+std::to_string(rows));
    checks+=2;
    if(got.selected) {
      if(got.taken!=bool(row[30]) || got.mispredict!=bool(row[31]) || got.short_forward_pair!=bool(row[32]) || got.core_call!=bool(row[33]) || got.next_pc!=(row[34]&~uint64_t(1)) || got.lane!=row[35])
        throw std::runtime_error("actual MEM resolution differs row="+std::to_string(rows));
      ++selected;checks+=6;const auto& u=packet[got.lane];jalr+=u.jalr;conditional+=u.branch;false_prediction+=!u.branch&&!u.jal&&!u.jalr&&u.predicted_valid;short_pairs+=got.short_forward_pair;
    }
    ++rows;
  }
  if(!file.eof() || rows<160000 || selected<100 || !jalr || !conditional)throw std::runtime_error("missing actual MEM branch regimes");
  // Explicit source controls: false-positive BTB, JALR bit clearing and bad
  // virtual address encoding, distinct predecode/MEM call+return conventions.
  auto u=ShuttleBranch::Uop{};u.valid=true;u.pc=0x80000006;u.predicted_valid=true;u.predicted_pc=u.pc+4;
  auto p=std::array<ShuttleBranch::Uop,2>{u,{}};auto r=ShuttleBranch::resolve(p);
  if(!r.mispredict || !r.redirect || r.branch_pc!=0x80000008 || r.fetch_pc!=0x80000008)throw std::runtime_error("false-positive BTB control");
  p[0].sfb_branch=true;p[1].valid=true;r=ShuttleBranch::resolve(p);if(r.redirect || r.predictor_update || !r.mispredict)throw std::runtime_error("short-forward suppression");
  p={};p[0]=u;p[0].predicted_valid=false;p[0].jalr=true;p[0].expanded=0x00008067;p[0].wdata=0x80012345;p[0].ras_head=0;
  r=ShuttleBranch::resolve(p);if(r.next_pc!=0x80012344 || !r.core_return || r.redirect_ras_head!=5)throw std::runtime_error("MEM return control");
  p[0].expanded=0x00028067;r=ShuttleBranch::resolve(p);if(r.core_return || r.redirect_ras_head!=0)throw std::runtime_error("MEM x5 is not corrective x1 return");
  p[0].expanded=0x000082e7;r=ShuttleBranch::resolve(p);if(r.core_call)throw std::runtime_error("MEM x5 is not corrective x1 call");
  p[0].expanded=0x000080e7;p[0].ras_head=5;r=ShuttleBranch::resolve(p);if(!r.core_call || !r.ras_update || r.ras_update_head!=0 || r.ras_address!=0x80012345)throw std::runtime_error("MEM core RAS update is wdata");
  p[0].wdata=0x10000000000;r=ShuttleBranch::resolve(p);if(r.next_pc!=(uint64_t(1)<<39))throw std::runtime_error("noncanonical JALR marker");
  std::cout<<"PASS actual MEM branch rows="<<rows<<" selected="<<selected<<" checks="<<checks<<" jalr="<<jalr<<" conditional="<<conditional<<" false_predictions="<<false_prediction<<" short_pairs="<<short_pairs<<" plus source controls\n";
}
