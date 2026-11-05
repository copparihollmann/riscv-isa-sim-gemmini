#define main inherited_ws_total_rows_main
#include "posted_ws_total_rows_test.cpp"
#undef main
int main(){
 for(unsigned rows:{1u,4u,16u}){
   const auto old=run(rows,true,false,true,true,true,1,0,false,4,4096);
   const auto merged=run(rows,true,false,true,true,true,1,0,false,2,4096);
   const auto repaired=run(rows,true,false,true,true,true,1,0,false,2,8192);
   const auto more=run(rows,true,false,true,true,true,1,0,false,8,4096);
   assert(merged.completion>old.completion);
   assert(repaired.completion==old.completion&&more.completion==old.completion);
   assert(old.pairings==1&&merged.pairings==1&&repaired.pairings==1&&more.pairings==1);
   auto old_rows=old.sampled_rows,merged_rows=merged.sampled_rows,repaired_rows=repaired.sampled_rows,more_rows=more.sampled_rows;
   for(auto&row:repaired_rows)if(row>=8192&&row<8192+16)row-=4096;
   for(auto*sampled:{&old_rows,&merged_rows,&repaired_rows,&more_rows})std::sort(sampled->begin(),sampled->end());
   assert(old_rows==merged_rows&&old_rows==repaired_rows&&old_rows==more_rows);
 }
 for(unsigned mode:{1u,2u,3u}){
   bool refused=false;
   try{run(16,true,false,true,true,true,1,0,false,2,4096,mode);}
   catch(const std::invalid_argument&){refused=true;}
   assert(refused);
 }
 std::cout<<"posted 2/4/8-bank operand geometry preserves ACC publication/fences and exposes merged/repaired bank contention PASS\n";
}
