if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_wide_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfwsub.wv vd, vs2, vs1
VI_VFP_WV_LOOP_WIDE
({
  vd = f32_sub(vs2, vs1);
},
{
  vd = f64_sub(vs2, vs1);
})

}
