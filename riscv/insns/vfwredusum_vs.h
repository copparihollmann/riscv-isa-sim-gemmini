if (P.VU.iris_mode && P.VU.vsew == 8) {
#include "iris_fp8_reduction_body.h"
} else if (P.VU.iris_mode) {
#include "iris_ieee_reduction_body.h"
} else {
// vfwredsum.vs vd, vs2, vs1
bool is_propagate = true;
VI_VFP_VV_LOOP_WIDE_REDUCTION
({
  vd_0 = f32_add(vd_0, vs2);
},
{
  vd_0 = f64_add(vd_0, vs2);
})

}
