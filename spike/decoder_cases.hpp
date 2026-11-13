// Generated from independently parsed Saturn Scala; do not edit.
struct DecoderCase { const char* name; uint32_t match, mask; };
static const DecoderCase decoder_cases[] = {
  {"SF_MM_INT", 0xf0000077u, 0xfc00707fu},
  {"SF_MM_FP8", 0xf0001077u, 0xfc00707fu},
  {"SF_VTMV_V_T", 0x41f06057u, 0xfdf0707fu},
  {"SF_VTMV_T_V", 0x5c006057u, 0xfc00707fu},
  {"SF_VTZERO_T", 0x41e06057u, 0xfdfff07fu},
  {"SF_VTDISCARD", 0x41c06057u, 0xfdfff07fu},
};
