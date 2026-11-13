if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfnmsac: vd[i] = -(f[rs1] * vs2[i]) + vd[i]

require_zvfbfa

VI_VFP_VF_LOOP
({
  vd = P.VU.altfmt ? bf16_mulAdd(rs1, bf16(vs2.v ^ BF16_SIGN), vd)
                   :  f16_mulAdd(rs1,  f16(vs2.v ^  F16_SIGN), vd);
},
{
  vd = f32_mulAdd(rs1, f32(vs2.v ^ F32_SIGN), vd);
},
{
  vd = f64_mulAdd(rs1, f64(vs2.v ^ F64_SIGN), vd);
})

}
