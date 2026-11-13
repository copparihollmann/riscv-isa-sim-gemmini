if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfmsac: vd[i] = +(f[rs1] * vs2[i]) - vd[i]

require_zvfbfa

VI_VFP_VF_LOOP
({
  vd = P.VU.altfmt ? bf16_mulAdd(rs1, vs2, bf16(vd.v ^ BF16_SIGN))
                   :  f16_mulAdd(rs1, vs2,  f16(vd.v ^  F16_SIGN));
},
{
  vd = f32_mulAdd(rs1, vs2, f32(vd.v ^ F32_SIGN));
},
{
  vd = f64_mulAdd(rs1, vs2, f64(vd.v ^ F64_SIGN));
})

}
