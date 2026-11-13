if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_wide_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfwnmacc.vf vd, vs2, rs1
VI_VFP_VF_LOOP_WIDE
({
  vd = f32_mulAdd(f32(rs1.v ^ F32_SIGN), vs2, vd);
},
{
  vd = f64_mulAdd(f64(rs1.v ^ F64_SIGN), vs2, vd);
})

}
