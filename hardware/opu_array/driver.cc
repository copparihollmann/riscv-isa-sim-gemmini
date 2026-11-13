#include "VOuterArray.h"
#include <verilated.h>
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

// Physical coordinates are deliberately independent of sequencer tile packing:
// 16x16 cells, each with16MRF slots; four-by-four clusters/readout chain.
class Check {
 public:
  VOuterArray top;
#include "port_bindings.inc"
  struct Word {uint32_t bits=0;bool known=false;};
  using Matrix=std::array<std::array<Word,16>,16>;
  std::array<Matrix,16> state{};
  std::array<std::array<Word,4>,4> pipe{};
  struct Write {unsigned slot,row,col;uint32_t bits;uint64_t edge;};
  std::vector<Write> pending;
  std::array<std::array<uint32_t,16>,16> golden{};
  bool golden_valid=false;
  uint64_t edges=0,output_checks=0,scans=0,integer_cells=0,fp8_cells=0,row_moves=0,col_moves=0,fp8_pipeline_groups=0;

  Check(){top.clock=0;top.reset=1;quiet();tick();tick();top.reset=0;initialize();}
  static uint32_t pack(const std::array<CData*,4>& bytes){
    uint32_t word=0;for(unsigned i=0;i<4;++i)word|=uint32_t(*bytes[i])<<(8*i);return word;
  }
  void quiet(){
    top.io_op_fp8=0;top.io_op_signed_l=0;top.io_op_signed_t=0;
    top.io_op_e5m2_l=0;top.io_op_e5m2_t=0;top.io_op_rm=0;
    for(unsigned i=0;i<4;++i){
      *macc[i]=0;*zero[i]=0;*mvin[i]=0;*mvin_col[i]=0;*shift[i]=0;
      *mrf[i]=0;*row_idx[i]=0;*col_idx[i]=0;*mv_en[i]=1;
      for(unsigned j=0;j<4;++j){*left[i][j]=0;*upper[i][j]=0;*row_en[i][j]=1;*col_en[i][j]=1;}
    }
  }
  void tick(){
    ++edges;
    auto next_pipe=pipe;
    for(unsigned cr=0;cr<4;++cr)for(unsigned cc=0;cc<4;++cc){
      next_pipe[cr][cc]=(cr&&*shift[cr])?pipe[cr-1][cc]:
        state[*mrf[cr]][cr*4+*row_idx[cr]][cc*4+*col_idx[cr]];
    }
    for(unsigned r=0;r<16;++r)for(unsigned c=0;c<16;++c){
      const unsigned cr=r/4,cc=c/4,slot=*mrf[cr];
      const bool enabled=*row_en[cr][r%4]&&*col_en[cc][c%4];
      bool completed=false;
      for(const auto& w:pending)if(w.edge==edges&&w.row==r&&w.col==c){
        state[w.slot][r][c]={w.bits,true};completed=true;
      }
      if(top.io_op_fp8&&*macc[cr]&&enabled){
        if(!golden_valid||!state[slot][r][c].known)throw std::runtime_error("missing independent FP8 golden/defined accumulator");
        pending.push_back({slot,r,c,golden[r][c],edges+2});++fp8_cells;
      }
      if(completed)continue;
      if(!top.io_op_fp8&&*macc[cr]&&enabled){
        auto& word=state[slot][r][c];
        if(!word.known)throw std::runtime_error("oracle reads undefined accumulator");
        unsigned a=*left[cr][r%4],b=*upper[cc][c%4];
        int64_t lhs=top.io_op_signed_l&&a>=128?int(a)-256:int(a);
        int64_t rhs=top.io_op_signed_t&&b>=128?int(b)-256:int(b);
        word.bits=uint32_t(uint64_t(word.bits)+uint64_t(lhs*rhs));++integer_cells;
      }else if(*zero[cr]&&enabled){state[slot][r][c]={0,true};}
      else{
        bool row=*mvin[cr]&&r%4==*row_idx[cr]&&c%4==*col_idx[cr]&&*mv_en[cc];
        bool col=*mvin_col[cc]&&c%4==*row_idx[cr]&&r%4==*col_idx[cr]&&*mv_en[cr];
        if(row||col){
          state[slot][r][c]={pack(*mvin_col[cc]?left[cr]:upper[cc]),true};
          if(row)++row_moves;if(col)++col_moves;
        }
      }
    }
    std::erase_if(pending,[&](const Write& w){return w.edge==edges;});
    top.clock=0;top.eval();top.clock=1;top.eval();top.clock=0;top.eval();
    pipe=next_pipe;
    for(unsigned cc=0;cc<4;++cc)if(pipe[3][cc].known){
      ++output_checks;
      if(*output[cc]!=pipe[3][cc].bits)throw std::runtime_error("readout mismatch edge="+std::to_string(edges)+" column="+std::to_string(cc)+" got="+std::to_string(*output[cc])+" expected="+std::to_string(pipe[3][cc].bits));
    }
  }
  void initialize(){
    if(!pending.empty())throw std::runtime_error("initialization overlaps in-flight FP8");
    quiet();for(unsigned e=0;e<16;++e){for(unsigned cr=0;cr<4;++cr){*mrf[cr]=e;*zero[cr]=1;}tick();}
    quiet();scan();
  }
  void scan(){
    if(!pending.empty())throw std::runtime_error("scan overlaps in-flight FP8");
    quiet();for(unsigned e=0;e<16;++e)for(unsigned lr=0;lr<4;++lr)for(unsigned lc=0;lc<4;++lc){
      for(unsigned cr=0;cr<4;++cr){*mrf[cr]=e;*row_idx[cr]=lr;*col_idx[cr]=lc;*shift[cr]=0;}
      tick();for(unsigned cr=1;cr<4;++cr)*shift[cr]=1;
      tick();tick();tick();
    }
    ++scans;quiet();
  }
  static uint32_t pattern(unsigned e,unsigned r,unsigned c,unsigned salt){
    return 0x87654321u^(e*0x1020304u)^(r*0x934567u)^(c*0x1234567u)^(salt*0x31415927u);
  }
  static void unpack(std::array<CData*,4>& bytes,uint32_t word){for(unsigned i=0;i<4;++i)*bytes[i]=word>>(8*i);}
  void moves(){
    for(unsigned e=0;e<16;++e)for(unsigned r=0;r<16;++r)for(unsigned lc=0;lc<4;++lc){
      quiet();const unsigned cr=r/4;*mrf[cr]=e;*row_idx[cr]=r%4;*col_idx[cr]=lc;*mvin[cr]=1;
      for(unsigned cc=0;cc<4;++cc)unpack(upper[cc],pattern(e,r,cc*4+lc,0));tick();
    }
    scan();
    for(unsigned e=0;e<16;++e)for(unsigned c=0;c<16;++c)for(unsigned lr=0;lr<4;++lr){
      quiet();const unsigned cc=c/4;*mvin_col[cc]=1;
      for(unsigned cr=0;cr<4;++cr){*mrf[cr]=e;*row_idx[cr]=c%4;*col_idx[cr]=lr;unpack(left[cr],pattern(e,cr*4+lr,c,1));}
      tick();
    }
    scan();
    // Independent per-cluster-row indices and partial VL group enables.
    for(unsigned trial=0;trial<32;++trial){
      quiet();for(unsigned i=0;i<4;++i){*mrf[i]=(trial+3*i)%16;*row_idx[i]=(trial+i)%4;*col_idx[i]=(trial+2*i)%4;
        *mvin[i]=trial&1;*mvin_col[i]=!(trial&1);*mv_en[i]=((trial+i)%3)!=0;
        unpack(left[i],pattern(trial%16,i,trial%16,3));unpack(upper[i],pattern(trial%16,trial%16,i,4));}
      tick();
    }
    scan();
  }
  void integer(){
    constexpr unsigned limits[]={0,1,3,4,5,7,8,15,16};
    unsigned trial=0;
    for(unsigned sa=0;sa<2;++sa)for(unsigned sb=0;sb<2;++sb)
      for(unsigned rows:limits)for(unsigned cols:limits){
        quiet();top.io_op_signed_l=sa;top.io_op_signed_t=sb;
        for(unsigned i=0;i<4;++i){*mrf[i]=(trial+3*i)%16;*macc[i]=1;
          for(unsigned j=0;j<4;++j){*row_en[i][j]=i*4+j<rows;*col_en[i][j]=i*4+j<cols;
            *left[i][j]=(trial*37+i*17+j*83)&255;*upper[i][j]=(trial*53+i*71+j*29)&255;}}
        tick();if(++trial%27==0)scan();
      }
    scan();
  }
  void fp8(const std::string& path){
    initialize();std::ifstream file(path);std::string magic;unsigned count;
    if(!(file>>magic>>count)||(magic!="IRIS_ARRAY_FP8_V1"&&magic!="IRIS_ARRAY_FP8_V2")||count!=80)throw std::runtime_error("invalid FP8 corpus header");
    const bool pipeline=magic=="IRIS_ARRAY_FP8_V2";
    for(unsigned index=0;index<count;++index){
      quiet();unsigned id,fa,fb,rm,rowmask,colmask;
      if(!(file>>id>>fa>>fb>>rm>>rowmask>>colmask)||id!=index||fa>1||fb>1||rm>4||rowmask>65535||colmask>65535)throw std::runtime_error("invalid FP8 record");
      top.io_op_fp8=1;top.io_op_e5m2_l=fa;top.io_op_e5m2_t=fb;top.io_op_rm=rm;
      for(unsigned cr=0;cr<4;++cr){unsigned slot;if(!(file>>slot)||slot>=16)throw std::runtime_error("invalid FP8 slot");*mrf[cr]=slot;*macc[cr]=1;}
      for(auto& row:left)for(auto* byte:row){unsigned v;if(!(file>>v)||v>255)throw std::runtime_error("invalid left operand");*byte=v;}
      for(auto& row:upper)for(auto* byte:row){unsigned v;if(!(file>>v)||v>255)throw std::runtime_error("invalid upper operand");*byte=v;}
      for(unsigned i=0;i<4;++i)for(unsigned j=0;j<4;++j){*row_en[i][j]=(rowmask>>(i*4+j))&1;*col_en[i][j]=(colmask>>(i*4+j))&1;}
      for(auto& row:golden)for(auto& value:row){uint64_t v;if(!(file>>v)||v>UINT32_MAX)throw std::runtime_error("truncated/out-of-range FP8 golden");value=v;}
      golden_valid=true;tick();golden_valid=false;
      // A group keeps format/rm stable and names four distinct accumulator
      // entries per physical cell. It therefore exercises one issue per edge
      // while preceding FMAs are in flight, without same-entry RAW hazards.
      if(!pipeline||index%4==3){
        for(auto* enable:macc)*enable=0;
        tick();tick();quiet();
        if(pipeline)++fp8_pipeline_groups;
      }
      if(index%16==15)scan();
    }
    if(file>>magic)throw std::runtime_error("unexpected trailing FP8 record");scan();
  }
};

int main(int argc,char** argv){
  try{
    if(argc!=2)throw std::runtime_error("independent array FP8 corpus required");
    Verilated::commandArgs(argc,argv);Verilated::randSeed(1);Verilated::randReset(2);
    Check test;test.moves();test.integer();test.fp8(argv[1]);
    std::cout<<"{\"status\":\"passed_saved_opu_array\",\"native_edges\":"<<test.edges
      <<",\"defined_output_checks\":"<<test.output_checks<<",\"full_entry_scans\":"<<test.scans
      <<",\"integer_cell_macs\":"<<test.integer_cells<<",\"fp8_cell_macs\":"<<test.fp8_cells
      <<",\"fp8_pipeline_groups\":"<<test.fp8_pipeline_groups
      <<",\"row_cell_moves\":"<<test.row_moves<<",\"column_cell_moves\":"<<test.col_moves<<"}\n";
  }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
