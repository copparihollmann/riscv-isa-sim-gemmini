if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfmul.vv vd, vs1, vs2, vm
require_zvfbfa

VI_VFP_VV_LOOP
({
  vd = VFP_OP_16(mul, vs1, vs2);
},
{
  vd = f32_mul(vs1, vs2);
},
{
  vd = f64_mul(vs1, vs2);
})

}
