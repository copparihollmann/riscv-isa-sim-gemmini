#define main inherited_ws_total_rows_main
#include "posted_ws_total_rows_test.cpp"
#undef main
int main(){
 for(unsigned stride:{2u,3u})for(unsigned rows:{1u,3u,4u,16u}){
   auto observed=run(rows,true,false,false,true,false,stride,4090);
   assert(observed.written==rows&&observed.sampled_rows.size()==rows);
   for(unsigned i=0;i<rows;++i)assert(observed.sampled_rows[i]==4090+i*stride);
   auto unit=run(rows,true,false,false,true,false,1,4090);
   assert(observed.completion==unit.completion); // no synthetic stride fee
 }
 // Row1 is NOT an actual stride2 SRAM read, but lies in the hardware RS
 // interval [0,rows*stride). Its pending LOAD command must still delay EX.
 auto blocked=run(4,true,false,false,true,false,2,0,true);
 assert(blocked.first>=100&&blocked.sampled_rows==std::vector<ValueId>({0,2,4,6}));
 std::cout<<"posted finite A sampling2/3, padded floor4, bank crossing, actual ACC publication and unchanged completion service PASS\n";
}
