if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_wide_fp8_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_fma_body.h"
} else {
// vfwadd.vv vd, vs2, vs1

require_zvfbfa

VI_VFP_VV_LOOP_WIDE
({
  vd = f32_add(vs2, vs1);
},
{
  vd = f64_add(vs2, vs1);
})

}
