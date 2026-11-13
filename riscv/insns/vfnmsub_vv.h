if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfnmsub: vd[i] = -(vd[i] * vs1[i]) + vs2[i]

require_zvfbfa

VI_VFP_VV_LOOP
({
  vd = P.VU.altfmt ? bf16_mulAdd(bf16(vd.v ^ BF16_SIGN), vs1, vs2)
                   :  f16_mulAdd( f16(vd.v ^  F16_SIGN), vs1, vs2);
},
{
  vd = f32_mulAdd(f32(vd.v ^ F32_SIGN), vs1, vs2);
},
{
  vd = f64_mulAdd(f64(vd.v ^ F64_SIGN), vs1, vs2);
})

}
