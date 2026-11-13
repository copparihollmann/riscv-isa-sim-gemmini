if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_wide_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfwmacc.vv vd, vs2, vs1
VI_VFP_VV_LOOP_WIDE
({
  vd = f32_mulAdd(vs1, vs2, vd);
},
{
  vd = f64_mulAdd(vs1, vs2, vd);
})

}
