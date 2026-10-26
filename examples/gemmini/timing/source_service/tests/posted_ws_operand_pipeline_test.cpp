#define main inherited_ws_total_rows_main
#include "posted_ws_total_rows_test.cpp"
#undef main
int main(){
 for(unsigned rows:{1,2,3,4,5,15,16}){
  auto single=run(rows,true,false,false,true);
  auto garbage=run(rows,true,true,false,true);
  auto paired=run(rows,true,false,true,true,false);
  auto same_bank=run(rows,true,false,true,true,true);
  assert(single.written==rows&&garbage.written==rows);
  assert(paired.pairings==1&&same_bank.pairings==1&&paired.written==2*rows&&same_bank.written==2*rows);
  assert(same_bank.completion>paired.completion);
 }
 std::cout<<"posted original PRELOAD/COMPUTE/MUL_PRE same-bank pipeline, floor4 padding, actual row publication and full fence PASS\n";
}
