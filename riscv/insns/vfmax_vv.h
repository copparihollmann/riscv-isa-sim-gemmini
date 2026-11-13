if(P.VU.iris_mode){
#include "iris_fpcomp_body.h"
}else{
// vfmax

require_zvfbfa

VI_VFP_VV_LOOP
({
  vd = VFP_OP_16(max, vs2, vs1);
},
{
  vd = f32_max(vs2, vs1);
},
{
  vd = f64_max(vs2, vs1);
})

}
