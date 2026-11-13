// Additional source System admission controls, using the unchanged positive
// fixture translation unit. No synthetic mutation of private RTL state.
#define main positive_fixture_main_not_invoked
#include "shuttle_memory_system_write_v1.cpp"
#undef main
int main(int argc,char**argv){
  if(argc!=2){std::cerr<<"explicit control required\n";return 2;}
  try{
    Fixture f(1);f.startup();const std::string mode=argv[1];
    if(mode=="--cold-store"){f.issue(1,1,0,0x80010008,0x13579);for(unsigned n=0;n<20;++n)f.core_step();}
    else if(mode=="--undefined-line"){f.issue(0,0,0,0x80030000);for(unsigned n=0;n<20000;++n)f.core_step();}
    else if(mode=="--outside-domain"){f.issue(0,0,0,0x80400000);for(unsigned n=0;n<20000;++n)f.core_step();}
    else throw std::runtime_error("unknown control");
    std::cerr<<"negative control unexpectedly completed\n";return 0;
  }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
