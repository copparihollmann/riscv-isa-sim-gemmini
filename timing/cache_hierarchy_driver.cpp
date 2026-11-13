#include "cache_hierarchy.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
using namespace iris::cache;
int main(int argc,char**argv){try{
 if(argc!=3&&argc!=4)throw std::invalid_argument("usage: cache-hierarchy shuttle|rocket|l2 seed [--explore-concrete-reset]");
 if(argc==4&&std::string(argv[3])!="--explore-concrete-reset")throw std::invalid_argument("unknown cache policy flag");
 std::string name=argv[1];Component c;
 if(name=="shuttle")c=Component::ShuttleL1D;else if(name=="rocket")c=Component::RocketL1D;
 else if(name=="l2")c=Component::InclusiveL2;else throw std::invalid_argument("unknown component");
 Model model(c,std::stoul(argv[2]),argc==4?UnresetReplayPolicy::ExploreConcreteReset:UnresetReplayPolicy::RefuseUse);std::string command;
 while(std::cin>>command){
  if(command=="eval"){
   std::vector<Bits> input(model.input_fields().size());
   for(auto &field:input)for(auto &word:field.limbs)if(!(std::cin>>std::hex>>word))throw std::invalid_argument("truncated physical cache input frame");
   model.evaluate(input);
  }else if(command=="sample"){
   const auto output=model.sample();std::cout<<"CACHE "<<std::dec<<model.edges();
   for(const auto&field:output)for(auto word:field.limbs)std::cout<<' '<<std::hex<<word;
   std::cout<<'\n';
  }else if(command=="commit")model.commit();
  else throw std::invalid_argument("unknown physical cache command");
 }
 return 0;
}catch(const std::exception&e){std::cerr<<"IRIS_CACHE_REFUSAL: "<<e.what()<<'\n';return 2;}}
