if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_wide_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfwmul.vf vd, vs2, rs1
VI_VFP_VF_LOOP_WIDE
({
  vd = f32_mul(vs2, rs1);
},
{
  vd = f64_mul(vs2, rs1);
})

}
