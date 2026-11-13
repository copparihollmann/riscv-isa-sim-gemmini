// See LICENSE for license details.
#ifndef _RISCV_VECTOR_UNIT_H
#define _RISCV_VECTOR_UNIT_H

#include <array>
#include <cstdint>
#include <optional>
#include <stdexcept>

#include "decode.h"
#include "csrs.h"
#include "iris_definedness.hpp"

class processor_t;

enum VRM{
  RNU = 0,
  RNE,
  RDN,
  ROD,
  INVALID_RM
};

template<uint64_t N>
struct type_usew_t;

template<>
struct type_usew_t<8>
{
  using type=uint8_t;
};

template<>
struct type_usew_t<16>
{
  using type=uint16_t;
};

template<>
struct type_usew_t<32>
{
  using type=uint32_t;
};

template<>
struct type_usew_t<64>
{
  using type=uint64_t;
};

template<uint64_t N>
struct type_sew_t;

template<>
struct type_sew_t<8>
{
  using type=int8_t;
};

template<>
struct type_sew_t<16>
{
  using type=int16_t;
};

template<>
struct type_sew_t<32>
{
  using type=int32_t;
};

template<>
struct type_sew_t<64>
{
  using type=int64_t;
};

// Element Group of 4 32 bits elements (128b total).
using EGU32x4_t = std::array<uint32_t, 4>;

// Element Group of 8 32 bits elements (256b total).
using EGU32x8_t = std::array<uint32_t, 8>;

// Element Group of 4 64 bits elements (256b total).
using EGU64x4_t = std::array<uint64_t, 4>;

// Element Group of 16 8 bits elements (128b total).
using EGU8x16_t = std::array<uint8_t, 16>;

class vectorUnit_t
{
public:

  // Iris MRF cells are not reset by RTL. Guard reads until software writes them.
  bool iris_mode = false;
  uint64_t iris_hart = 0, iris_pc = 0, iris_insn = 0;
  bool iris_executing = false;
  iris_definedness::Bytes iris_vrf_definedness, iris_tile_definedness;
  // Handler macros may obtain a writable destination reference before reading
  // aliased sources. Source masks must describe instruction-entry bits, never
  // the destination allocation's freshly marked bits. Save lazily on first
  // write so scalar instructions do not copy the VRF shadow.
  std::optional<iris_definedness::Bytes> iris_vrf_instruction_input;
  const iris_definedness::Bytes& iris_vrf_input() const {
    return iris_executing&&iris_vrf_instruction_input?*iris_vrf_instruction_input:iris_vrf_definedness;
  }
  void iris_vrf_before_write() {
    if(iris_mode&&iris_executing&&!iris_vrf_instruction_input)
      iris_vrf_instruction_input.emplace(iris_vrf_definedness);
  }
  struct iris_instruction_scope {
    vectorUnit_t& unit;uint64_t pc,bits;bool executing;
    std::optional<iris_definedness::Bytes> inputs;
    iris_instruction_scope(vectorUnit_t& v,uint64_t instruction,uint64_t at)
      :unit(v),pc(v.iris_pc),bits(v.iris_insn),executing(v.iris_executing),
       inputs(std::move(v.iris_vrf_instruction_input)) {
      unit.iris_vrf_instruction_input.reset();
      unit.iris_executing=unit.iris_mode;unit.iris_pc=at;unit.iris_insn=instruction;
    }
    ~iris_instruction_scope() {
      unit.iris_vrf_instruction_input=std::move(inputs);
      unit.iris_pc=pc;unit.iris_insn=bits;unit.iris_executing=executing;
    }
  };
  bool iris_integer_self_constant() const {
    if ((iris_insn&0x707f)!=0x57 || ((iris_insn>>15)&31)!=((iris_insn>>20)&31)) return false;
    unsigned f6=iris_insn>>26;
    return f6==2||f6==11||(f6>=0x18&&f6<=0x1d);
  }
  bool iris_vd_read_modify_write() const {
    unsigned f3=(iris_insn>>12)&7,f6=iris_insn>>26;
    return (iris_insn&0x7f)==0x57&&(f3==2||f3==6)&&
      (f6==0x29||f6==0x2b||f6==0x2d||f6==0x2f||(f6>=0x3c&&f6<=0x3f));
  }
  bool iris_unmasked_move() const {
    const unsigned f3=(iris_insn>>12)&7;
    return iris_mode&&iris_executing&&(iris_insn&0x7f)==0x57&&(iris_insn>>26)==0x17&&
      ((iris_insn>>25)&1)&&(f3==0||f3==3||f3==4||f3==5);
  }
  std::vector<uint8_t> iris_initialized;
  template<typename T> void iris_cell(T& cell, bool write) {
    if (!iris_mode) return;
    if (sizeof(T) != 4) throw std::runtime_error("Iris VME supports 32-bit tile cells only");
    const size_t index = (reinterpret_cast<char*>(&cell) - mt.data()) / 4;
    if (index >= iris_initialized.size()) throw std::runtime_error("Iris VME cell out of range");
    if (write) {iris_initialized[index]=1;iris_tile_definedness.define(index*4,4);}
    else iris_tile_definedness.require(index*4,4,{iris_hart,iris_pc,"tile"});
  }
  processor_t* p = nullptr;
  void *reg_file = nullptr;
  int setvl_count = 0;
  reg_t vlmax = 0;
  reg_t vlenb = 0;
  vector_csr_t_p vxrm = 0, vstart = 0, vl = 0, vtype = 0, mtype = 0;
  reg_t vma = 0, vta = 0;
  reg_t vsew = 0;
  float vflmul = 0;
  reg_t altfmt = 0;
  reg_t ELEN = 0, VLEN = 0;
  bool vill = false;
  bool vstart_alu = false;
  std::vector<char> mt;
  reg_t widen = 0;
  reg_t tm = 0;
  reg_t tk = 0;
  reg_t TE = 0;

  // vector element for various SEW
  template<typename T> T& elt(reg_t vReg, reg_t n, bool is_write = false) {
    assert(vsew != 0);
    assert((VLEN >> 3)/sizeof(T) > 0);
    reg_t elts_per_reg = (VLEN >> 3) / (sizeof(T));
    vReg += n / elts_per_reg;
    n = n % elts_per_reg;
#ifdef WORDS_BIGENDIAN
    // "V" spec 0.7.1 requires lower indices to map to lower significant
    // bits when changing SEW, thus we need to index from the end on BE.
    n ^= elts_per_reg - 1;
#endif
    const size_t offset=vReg*(VLEN>>3)+n*sizeof(T);
    if (iris_mode) {
      if (is_write) {
        iris_vrf_before_write();
        if (iris_executing&&iris_vd_read_modify_write())
          iris_vrf_input().require(offset,sizeof(T),{iris_hart,iris_pc,"VRF-accumulator"});
        if(!(iris_unmasked_move()&&((iris_insn>>12)&7)==0))iris_vrf_definedness.define(offset,sizeof(T));
      } else if (iris_executing&&!iris_integer_self_constant()&&!(iris_unmasked_move()&&((iris_insn>>12)&7)==0))
        iris_vrf_input().require(offset,sizeof(T),{iris_hart,iris_pc,"VRF"});
    }
    if (is_write)
      log_elt_write_if_needed(vReg);

    T *regStart = (T*)((char*)reg_file + vReg * (VLEN >> 3));
    return regStart[n];
  }

  template<typename T> size_t iris_element_offset(reg_t reg,reg_t element) const {
    const reg_t per=(VLEN>>3)/sizeof(T);reg+=element/per;element%=per;
#ifdef WORDS_BIGENDIAN
    element^=per-1;
#endif
    return reg*(VLEN>>3)+element*sizeof(T);
  }
  template<typename T> iris_definedness::Value<T> read_transport(reg_t reg,reg_t element) {
    const auto offset=iris_element_offset<T>(reg,element);
    iris_definedness::Value<T> value;value.value=*(T*)((char*)reg_file+offset);
    if(iris_mode) {
      auto masks=iris_vrf_input().read(offset,sizeof(T));std::copy(masks.begin(),masks.end(),value.known.begin());
    } else value.known.fill(0xff);
    return value;
  }
  template<typename T> void write_transport(reg_t reg,reg_t element,const iris_definedness::Value<T>& value) {
    const auto offset=iris_element_offset<T>(reg,element);
    iris_vrf_before_write();
    log_elt_write_if_needed(offset/(VLEN>>3));
    *(T*)((char*)reg_file+offset)=value.value;
    if(iris_mode)iris_vrf_definedness.write(offset,value.known);
  }
  void copy_element_mask(reg_t dest,reg_t source,reg_t element) {
    if(!iris_mode)return;
    const size_t bytes=vsew/8;
    const size_t dst=iris_element_offset<uint8_t>(dest,element*bytes),src=iris_element_offset<uint8_t>(source,element*bytes);
    iris_vrf_before_write();
    iris_vrf_definedness.copy_from(dst,iris_vrf_input(),src,bytes);
  }
  template<typename T> iris_definedness::Value<T> read_tile_transport(const T& cell) {
    iris_definedness::Value<T> value;value.value=cell;
    if(iris_mode) {
      const size_t offset=(const char*)&cell-mt.data();
      auto masks=iris_tile_definedness.read(offset,sizeof(T));std::copy(masks.begin(),masks.end(),value.known.begin());
    } else value.known.fill(0xff);
    return value;
  }
  template<typename T> void write_tile_transport(T& cell,const iris_definedness::Value<T>& value) {
    cell=value.value;
    if(iris_mode) {
      const size_t offset=(char*)&cell-mt.data();iris_tile_definedness.write(offset,value.known);
      for(size_t cell=offset/4;cell<=(offset+sizeof(T)-1)/4;++cell) {
        const auto masks=iris_tile_definedness.read(cell*4,4);
        iris_initialized[cell]=std::all_of(masks.begin(),masks.end(),[](uint8_t mask){return mask==0xff;});
      }
    }
  }

  // vector element group access, where EG is a std::array<T, N>.
  // The logic differences between 'elt()' and 'elt_group()' come from
  // the fact that, while 'elt()' requires that the element is fully
  // contained in a single vector register, the element group may span
  // multiple registers in a single register group (LMUL>1).
  //
  // Notes:
  // - We do NOT check that a single element - i.e., the T in the element
  //   group type std::array<T, N> - fits within a single register, or that
  //   T is smaller or equal to VSEW. Implementations of the instructions
  //   sometimes use a different T than what the specification suggests.
  //   Instructon implementations should 'require()' what the specification
  //   dictates.
  // - We do NOT check that 'vReg' is a valid register group, or that
  //   'n+1' element groups fit in the register group 'vReg'. It is
  //   the responsibility of the caller to validate those preconditions.

  template<typename EG> EG&
  elt_group(reg_t vReg, reg_t n, bool is_write = false) {
#ifdef WORDS_BIGENDIAN
    fputs("vectorUnit_t::elt_group is not compatible with WORDS_BIGENDIAN setup.\n",
            stderr);
    abort();
#endif
    using T = typename EG::value_type;
    constexpr std::size_t N = std::tuple_size<EG>::value;
    assert(N > 0);

    assert(vsew != 0);
    constexpr reg_t elt_group_size = N * sizeof(T);
    const reg_t reg_group_size = (VLEN >> 3) * vflmul;
    assert(((n + 1) * elt_group_size) <= reg_group_size);

    const reg_t start_byte = n * elt_group_size;
    const reg_t bytes_per_reg = VLEN >> 3;

    // Inclusive first/last register indices.
    const reg_t reg_first = vReg + start_byte / bytes_per_reg;
    const reg_t reg_last = vReg + (start_byte + elt_group_size - 1) / bytes_per_reg;
    if(iris_mode) {
      const size_t offset=vReg*bytes_per_reg+start_byte;
      if(is_write) {
        iris_vrf_before_write();
        if(iris_executing&&iris_vd_read_modify_write())iris_vrf_input().require(offset,elt_group_size,{iris_hart,iris_pc,"VRF-accumulator"});
        iris_vrf_definedness.define(offset,elt_group_size);
      } else if(iris_executing)iris_vrf_input().require(offset,elt_group_size,{iris_hart,iris_pc,"VRF-group"});
    }

    // Element groups per register groups
    for (reg_t vidx = reg_first; vidx <= reg_last; ++vidx)
      if (is_write)
        log_elt_write_if_needed(vidx);

    return *(EG*)((char*)reg_file + vReg * (VLEN >> 3) + start_byte);
  }

  bool mask_elt(reg_t vReg, reg_t n)
  {
    const auto offset=iris_element_offset<uint8_t>(vReg,n/8);
    const unsigned f6=iris_insn>>26;
    const bool self_constant=(iris_insn&0x707f)==0x2057&&((iris_insn>>15)&31)==((iris_insn>>20)&31)&&
      (f6==0x18||f6==0x1b||f6==0x1c||f6==0x1f);
    if(iris_mode&&iris_executing&&!self_constant)
      iris_vrf_input().require_bits(offset,1u<<(n%8),{iris_hart,iris_pc,"predicate"});
    return (((uint8_t*)reg_file)[offset]>>(n%8))&1;
  }

  void set_mask_elt(reg_t vReg, reg_t n, bool value)
  {
    const auto offset=iris_element_offset<uint8_t>(vReg,n/8);
    iris_vrf_before_write();
    auto& e=((uint8_t*)reg_file)[offset];
    log_elt_write_if_needed(offset/(VLEN>>3));
    if(iris_mode)iris_vrf_definedness.write_bits(offset,1u<<(n%8));
    e = (e & ~(1U << (n % 8))) | (value << (n % 8));
  }

private:

  void log_elt_write_if_needed(reg_t vReg) const;

public:

  void reset();

  vectorUnit_t() {}

  ~vectorUnit_t() {
    free(reg_file);
    reg_file = 0;
  }

  reg_t set_vl(int rd, int rs1, reg_t reqVL, reg_t newType);

  reg_t get_vlen() { return VLEN; }
  reg_t get_elen() { return ELEN; }
  reg_t get_slen() { return VLEN; }

  VRM get_vround_mode() {
    return (VRM)(vxrm->read_defined(iris_pc));
  }

  reg_t read_mtype() const;
  void msetmtype(reg_t newMType, reg_t newType);
  reg_t msettn(reg_t atn);
  reg_t msettm(reg_t atm);
  reg_t msettk(reg_t atk);

  reg_t ete(reg_t eew) {
    return widen == 0 ? 0 : eew == 64 ? TE / 2 : TE;
  }

  reg_t ete() {
    return ete(tew());
  }

  reg_t eve() {
    return std::max(reg_t(1), VLEN / vsew);
  }

  reg_t tn(reg_t eew) {
    return std::min(vl->read(), ete(eew));
  }

  reg_t tn() {
    return tn(tew());
  }

  reg_t tew() {
    return vsew * widen;
  }

  reg_t kmax() {
    return widen == 0 ? 0 : std::max(reg_t(1), 32 / vsew);
  }

  reg_t mt_align(reg_t eew)
  {
    return eew <= 32 ? eew / 8 : 2;
  }

  reg_t tss_tile(reg_t tss, reg_t eew)
  {
    return (tss >> 27) & 0xF & -mt_align(eew);
  }

  reg_t tss_type(reg_t tss)
  {
    return (tss >> 24) & 1;
  }

  reg_t tss_index(reg_t tss, reg_t eew)
  {
    return tss & (ete(eew) - 1);
  }

  template<typename T>
  T& tss_elt(reg_t tss, reg_t minor_idx)
  {
    auto eew = 8 * sizeof(T);
    auto tile = tss_tile(tss, eew);
    auto major_idx = tss_index(tss, eew);

    switch (tss_type(tss)) {
      case 0: return mt_elt<T>(tile, major_idx, minor_idx);
      case 1: return mt_elt<T>(tile, minor_idx, major_idx);
      default: abort();
    }
  }

  template<typename T>
  T& mt_elt(reg_t tile, reg_t row, reg_t col)
  {
    reg_t ptile, minor_offset, major_offset;
    switch (sizeof(T)) {
      case 1:
        ptile = tile;
        minor_offset = (row % 4) * 4 + (col % 4);
        major_offset = (row / 4) * (TE / 4) + (col / 4);
        break;
      case 2:
        ptile = tile + ((row & 2) >> 1);
        minor_offset = (row % 2) * 4 + (col % 2) * 2 + ((col / 2) % 2) * 8;
        major_offset = (row / 4) * (TE / 4) + (col / 4);
        break;
      case 4:
        ptile = tile + (row & 2) + ((col & 2) >> 1);
        minor_offset = (row % 2) * 8 + (col % 2) * 4;
        major_offset = (row / 4) * (TE / 4) + (col / 4);
        break;
      case 8:
        ptile = tile + (row & 1);
        minor_offset = (col % 2) * 8;
        major_offset = (row / 2) * (TE / 4) + (col / 2);
        break;
      default:
        abort();
    }

    assert(ptile < 16);
    assert(minor_offset < 16);
    assert(major_offset * 16 < TE * TE);

    return *(T*)&mt[ptile * TE * TE + major_offset * 16 + minor_offset];
  }

  static const unsigned kmaxmax = 8;

  template<typename T>
  std::array<T, kmaxmax> mt_vector(int rs, size_t idx)
  {
    const int vreg_stride = kmaxmax / kmax();
    std::array<T, kmaxmax> res{};
    for (size_t ki = 0; ki < tk; ki++)
      res[ki] = elt<T>(rs + ki * vreg_stride, idx);
    return res;
  }
};
#endif
