/* Experimental INT8 convolution packing for the compiler ablation corpus.
 *
 * No arithmetic/quantization changes: row=(batch, output_y, output_x),
 * reduction=(input_channel, kernel_y, kernel_x), zero padding is signed I8 0.
 * Each packed activation panel is K-major with its ACTUAL row count as stride.
 * Consumers must include packing, all primitive calls and completion in the
 * whole-operator ROI. This is a benchmark candidate, not a default lowering.
 */
#ifndef IRIS_COMPILER_CONV_PACK_H
#define IRIS_COMPILER_CONV_PACK_H
#include <stddef.h>
#include <stdint.h>

struct iris_conv_shape {
    size_t batch, ci, co, h, w, kh, kw, stride, pt, pl, oh, ow;
    unsigned nhwc, hwio;
};

static inline size_t iris_conv_rows(const struct iris_conv_shape *s) {
    return s->batch * s->oh * s->ow;
}

static inline size_t iris_conv_reduction(const struct iris_conv_shape *s) {
    return s->ci * s->kh * s->kw;
}

/* A zero-copy activation view exists only for this exact NCHW geometry. */
static inline int iris_conv_direct_a(const struct iris_conv_shape *s) {
    return s->batch == 1 && !s->nhwc && s->kh == 1 && s->kw == 1 &&
           s->stride == 1 && s->pt == 0 && s->pl == 0 &&
           s->oh == s->h && s->ow == s->w;
}

static inline void iris_conv_pack_b(const struct iris_conv_shape *s,
                                    const int8_t *weights, int8_t *packed) {
    const size_t k = iris_conv_reduction(s);
    for (size_t ch = 0; ch < s->ci; ++ch)
        for (size_t ky = 0; ky < s->kh; ++ky)
            for (size_t kx = 0; kx < s->kw; ++kx) {
                size_t ki = (ch * s->kh + ky) * s->kw + kx;
                for (size_t oc = 0; oc < s->co; ++oc) {
                    size_t source = s->hwio ?
                        ((ky * s->kw + kx) * s->ci + ch) * s->co + oc :
                        oc * k + ki;
                    packed[ki * s->co + oc] = weights[source];
                }
            }
}

/* first/count must describe a nonempty, in-range contiguous output-row panel.
 * Rolling coordinates avoid division in the inner input-byte copy loop.
 * Padding uses signed coordinates so top/left subtraction cannot underflow.
 */
static inline void iris_conv_pack_a(const struct iris_conv_shape *s,
                                    const int8_t *input, int8_t *packed,
                                    size_t first, size_t count) {
    const size_t plane = s->oh * s->ow;
    const size_t first_bi = first / plane;
    const size_t first_y = (first % plane) / s->ow;
    const size_t first_x = first % s->ow;
    for (size_t ch = 0; ch < s->ci; ++ch)
        for (size_t ky = 0; ky < s->kh; ++ky)
            for (size_t kx = 0; kx < s->kw; ++kx) {
                size_t ki = (ch * s->kh + ky) * s->kw + kx;
                size_t bi = first_bi, y = first_y, x = first_x;
                for (size_t p = 0; p < count; ++p) {
                    ptrdiff_t iy = (ptrdiff_t)(y * s->stride + ky) - (ptrdiff_t)s->pt;
                    ptrdiff_t ix = (ptrdiff_t)(x * s->stride + kx) - (ptrdiff_t)s->pl;
                    int8_t value = 0;
                    if (iy >= 0 && ix >= 0 && (size_t)iy < s->h && (size_t)ix < s->w) {
                        size_t at = s->nhwc ?
                            ((bi * s->h + (size_t)iy) * s->w + (size_t)ix) * s->ci + ch :
                            ((bi * s->ci + ch) * s->h + (size_t)iy) * s->w + (size_t)ix;
                        value = input[at];
                    }
                    packed[ki * count + p] = value;
                    if (++x == s->ow) {
                        x = 0;
                        if (++y == s->oh) { y = 0; ++bi; }
                    }
                }
            }
}
#endif
