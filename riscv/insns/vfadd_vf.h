if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_native_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfadd.vf vd, vs2, rs1
require_zvfbfa

VI_VFP_VF_LOOP
({
  vd = VFP_OP_16(add, vs2, rs1);
},
{
  vd = f32_add(rs1, vs2);
},
{
  vd = f64_add(rs1, vs2);
})

}
