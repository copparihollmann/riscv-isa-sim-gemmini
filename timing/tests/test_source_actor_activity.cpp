#include "timing/source_actor_activity.hpp"
#include <cassert>
using A=spike_timing::SourceActorActivity;using R=spike_timing::SourceActorRoleV1;
int main(){
 A a;a.edge(R::reader_slot,1,2,true);a.advance(4);a.begin(5);
 a.edge(R::execute_feed,2,7,true);a.edge(R::execute_feed,2,11,false);
 a.edge(R::reader_slot,3,8,true);a.edge(R::reader_slot,1,10,false);a.advance(9);
 a.edge(R::reader_slot,3,14,false);a.end(12);
 assert(a.complete());assert(a.rows()[7].active==7&&a.rows()[7].units==9&&a.rows()[7].peak==2);
 assert(a.rows()[6].active==4&&a.pairs()[0].active==4);
 assert(a.rows()[7].starts==1); // prefix reservation clipped, not recounted
 A b;b.edge(R::writer_state,1,4,true);b.begin(5);b.end(8);assert(b.complete()&&b.rows()[8].active==3);
 A c;c.edge(R::reader_slot,1,0,false);assert(!c.reason().empty());
 A d;d.edge(R::reader_slot,1,0,true);d.edge(R::reader_slot,1,1,true);assert(!d.reason().empty());
 A e(1);e.edge(R::reader_slot,1,0,true);e.edge(R::reader_slot,1,2,false);assert(!e.reason().empty());
 A f;f.advance(3);f.edge(R::reader_slot,1,2,true);assert(!f.reason().empty());
 A g;g.begin(0);g.end(2);assert(g.complete()&&g.rows()[7].active==0);
 A h;h.unavailable("missing provider");h.begin(0);h.end(2);assert(!h.complete());
}
