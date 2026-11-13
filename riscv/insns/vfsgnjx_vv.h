if(P.VU.iris_mode){
#include "iris_fpcomp_body.h"
}else{
// vfsgnx
VI_VFP_VV_LOOP
({
  vd = P.VU.altfmt ? bfsgnj16(vs2.v, vs1.v, false, true)
                   :  fsgnj16(vs2.v, vs1.v, false, true);
},
{
  vd = fsgnj32(vs2.v, vs1.v, false, true);
},
{
  vd = fsgnj64(vs2.v, vs1.v, false, true);
})

}
