if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfmul.vf vd, vs2, rs1, vm
require_zvfbfa

VI_VFP_VF_LOOP
({
  vd = VFP_OP_16(mul, vs2, rs1);
},
{
  vd = f32_mul(vs2, rs1);
},
{
  vd = f64_mul(vs2, rs1);
})

}
