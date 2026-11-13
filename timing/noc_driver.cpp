#include "noc_arbiter.hpp"
#include <charconv>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using iris::noc::Arbiter;
using iris::noc::Parameters;
using iris::noc::State;
static std::uint64_t number(const std::string& s) {
  std::uint64_t value=0;
  const auto result=std::from_chars(s.data(),s.data()+s.size(),value);
  if (result.ec!=std::errc{} || result.ptr!=s.data()+s.size())
    throw std::invalid_argument("Expected unsigned decimal integer: "+s);
  return value;
}
int main(int argc,char** argv) {
  try {
    if (argc!=9 || std::string(argv[1])!="--input-vcs" ||
        std::string(argv[3])!="--router-inputs" || std::string(argv[5])!="--output-vcs" ||
        std::string(argv[7])!="--local-input")
      throw std::invalid_argument("Required: --input-vcs N --router-inputs N --output-vcs N --local-input N");
    for (unsigned n:{2u,4u,6u,8u}) if(number(argv[n])>63)
      throw std::invalid_argument("Component parameter outside represented range");
    Parameters p{unsigned(number(argv[2])),unsigned(number(argv[4])),unsigned(number(argv[6])),unsigned(number(argv[8]))};
    (void)Arbiter(p,Arbiter::reset_state());
    std::unique_ptr<Arbiter> model;
    std::uint64_t pending=0;bool pending_seeded=false;
    std::string line;unsigned line_number=0;
    while (std::getline(std::cin,line)) {
      ++line_number;
      std::istringstream stream(line);std::vector<std::string> words;
      for(std::string word;stream>>word;)words.push_back(word);
      if(words.empty())continue;
      if(words[0]=="seed") {
        if(words.size()!=4)throw std::invalid_argument("seed needs exactly three masks");
        model=std::make_unique<Arbiter>(p,State{number(words[1]),number(words[2]),number(words[3])});continue;
      }
      if(words[0]=="reset") {
        if(words.size()!=1)throw std::invalid_argument("reset takes no masks");
        model=std::make_unique<Arbiter>(p,Arbiter::reset_state());continue;
      }
      if(words[0]=="pending") {
        if(words.size()!=2)throw std::invalid_argument("pending needs initial ready mask");
        pending=number(words[1]);pending_seeded=true;continue;
      }
      const bool isolated_egress=words[0]=="egress_step";
      if((words[0]!="step" && !isolated_egress) || words.size()!=7 || !model)
        throw std::invalid_argument("step needs seed/reset then TB waiting route_fire routed_vc eligible_inputs eligible_outputs");
      auto tb=number(words[1]);auto fire=number(words[3]);auto routed_vc=number(words[4]);
      if(fire>1 || routed_vc>63)throw std::invalid_argument("Invalid route boundary");
      iris::noc::Inputs input{number(words[2]),bool(fire),unsigned(routed_vc),number(words[5]),number(words[6])};
      std::uint64_t before_pending=0;
      if(isolated_egress) {
        if(!pending_seeded)throw std::invalid_argument("egress_step requires pending seed");
        const auto arrivals=number(words[2]);const auto free=number(words[5]);const auto bit=number(words[6]);
        if(free>1 || bit>=p.output_virtual_channels || (pending&arrivals))
          throw std::invalid_argument("Invalid arbiter-ready arrival/free-slot boundary");
        pending|=arrivals;before_pending=pending;
        input.waiting_vcs=pending;input.eligible_input_units=0;input.selected_eligible_output_vcs=0;
        const auto selected=model->preview(input).selected_vc;
        if(free && selected) {input.eligible_input_units=std::uint64_t{1}<<p.local_input_unit;input.selected_eligible_output_vcs=std::uint64_t{1}<<bit;}
      }
      auto r=model->step(input);
      if(isolated_egress && r.local_request_accepted)pending&=~r.selected_vc;
      std::cout<<tb<<' '<<r.selected_vc<<' '<<r.next.input_unit_mask<<' '<<r.input_unit_grants<<' '
               <<r.next.single_vc_input_mask<<' '<<r.islip_output_selection<<' '<<r.output_vc_grants<<' '
               <<r.next.islip_output_mask<<' '<<r.local_request_accepted;
      if(isolated_egress)std::cout<<' '<<before_pending<<' '<<pending;
      std::cout<<'\n';
    }
    if(!std::cin.eof())throw std::runtime_error("Input read failure");
    return 0;
  } catch(const std::exception& e) {std::cerr<<"NoC component refused: "<<e.what()<<'\n';return 2;}
}
