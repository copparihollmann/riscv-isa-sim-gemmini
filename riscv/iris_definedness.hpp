#pragma once
#include <algorithm>
#include <array>
#include <cstdint>
#include <limits>
#include <map>
#include <span>
#include <sstream>
#include <stdexcept>
#include <type_traits>
#include <vector>

// Shadow masks describe which value bits software has established. Placeholder
// data values are never evidence of reset initialization. Transport preserves
// these masks; observing unknown required bits is a model-capability refusal.
namespace iris_definedness {
template<typename T> struct Value {
  T value{};
  std::array<uint8_t,sizeof(T)> known{};
};
template<typename To,typename From> Value<To> extend_integer(const Value<From>& source) {
  static_assert(sizeof(To)>=sizeof(From));
  Value<To> result;result.value=static_cast<To>(source.value);result.known.fill(0xff);
  std::copy(source.known.begin(),source.known.end(),result.known.begin());
  if constexpr(std::is_signed_v<From>)
    if(!(source.known.back()&0x80))std::fill(result.known.begin()+sizeof(From),result.known.end(),0);
  return result;
}
template<typename To,typename From> Value<To> truncate(const Value<From>& source) {
  static_assert(sizeof(To)<=sizeof(From));
  Value<To> result;result.value=static_cast<To>(source.value);
  std::copy_n(source.known.begin(),sizeof(To),result.known.begin());return result;
}
struct Context {
  uint64_t hart=0,pc=0;
  const char* unit="unknown";
};
inline void bounds(size_t offset,size_t bytes,size_t size) {
  if(offset>size || bytes>size-offset)
    throw std::out_of_range("IRIS_DEFINEDNESS_RANGE: shadow byte range");
}
inline void require_byte(uint8_t known,uint8_t required,size_t byte,Context where) {
  if((known&required)==required)return;
  std::ostringstream out;
  out<<"IRIS_UNDEFINED_STATE hart="<<where.hart<<" pc=0x"<<std::hex<<where.pc
     <<" unit="<<where.unit<<" byte=0x"<<byte<<" required=0x"<<unsigned(required)
     <<" known=0x"<<unsigned(known);
  throw std::runtime_error(out.str());
}

class Bytes {
 public:
  explicit Bytes(size_t bytes=0):known_(bytes,0) {}
  void reset(size_t bytes) {known_.assign(bytes,0);}
  size_t size() const {return known_.size();}
  uint8_t byte(size_t offset) const {bounds(offset,1,size());return known_[offset];}
  void write(size_t offset,std::span<const uint8_t> masks) {
    bounds(offset,masks.size(),size());std::copy(masks.begin(),masks.end(),known_.begin()+offset);
  }
  void define(size_t offset,size_t bytes) {
    bounds(offset,bytes,size());std::fill_n(known_.begin()+offset,bytes,0xff);
  }
  void write_bits(size_t byte,uint8_t bits,bool defined=true) {
    bounds(byte,1,size());known_[byte]=(known_[byte]&~bits)|(defined?bits:0);
  }
  std::vector<uint8_t> read(size_t offset,size_t bytes) const {
    bounds(offset,bytes,size());return {known_.begin()+offset,known_.begin()+offset+bytes};
  }
  void require(size_t offset,size_t bytes,Context where) const {
    bounds(offset,bytes,size());
    for(size_t i=0;i<bytes;++i)require_byte(known_[offset+i],0xff,offset+i,where);
  }
  void require_bits(size_t byte,uint8_t bits,Context where) const {
    bounds(byte,1,size());require_byte(known_[byte],bits,byte,where);
  }
  void copy_from(size_t dest,const Bytes& source,size_t offset,size_t bytes) {
    // Snapshot first: physical vector groups and context buffers may overlap.
    const auto masks=source.read(offset,bytes);write(dest,masks);
  }
 private:
  std::vector<uint8_t> known_;
};

class Memory {
  static constexpr uint64_t page_bytes=4096;
  using Page=std::array<uint8_t,page_bytes>;
  std::map<uint64_t,Page> pages_;
  static void range(uint64_t address,size_t bytes) {
    if(bytes && bytes-1>std::numeric_limits<uint64_t>::max()-address)
      throw std::out_of_range("IRIS_DEFINEDNESS_RANGE: physical address wraps");
  }
 public:
  // Canonical physical addresses only; all harts must share this object.
  // Device/ROM reset policies are separate. Missing RAM pages mean unknown.
  std::vector<uint8_t> read(uint64_t address,size_t bytes) const {
    range(address,bytes);std::vector<uint8_t> masks(bytes,0);
    for(size_t i=0;i<bytes;++i) {
      auto page=pages_.find((address+i)/page_bytes);
      if(page!=pages_.end())masks[i]=page->second[(address+i)%page_bytes];
    }
    return masks;
  }
  void read_into(uint64_t address,std::span<uint8_t> masks) const {
    range(address,masks.size());
    for(size_t i=0;i<masks.size();++i) {
      auto page=pages_.find((address+i)/page_bytes);
      masks[i]=page==pages_.end()?0:page->second[(address+i)%page_bytes];
    }
  }
  void write(uint64_t address,std::span<const uint8_t> masks) {
    range(address,masks.size());
    for(size_t i=0;i<masks.size();++i) {
      const uint64_t page=(address+i)/page_bytes;
      if(!masks[i] && !pages_.contains(page))continue;
      pages_[page][(address+i)%page_bytes]=masks[i];
    }
  }
  void define(uint64_t address,size_t bytes) {
    range(address,bytes);
    // Explicit ELF/BSS/runtime writes may define bytes. Backing allocation and
    // host memset during simulator reset may not call this operation.
    const std::array<uint8_t,page_bytes> full=[] {Page p;p.fill(0xff);return p;}();
    while(bytes) {size_t n=std::min<size_t>(bytes,page_bytes);write(address,std::span(full).first(n));address+=n;bytes-=n;}
  }
  void require(uint64_t address,size_t bytes,Context where) const {
    const auto masks=read(address,bytes);
    for(size_t i=0;i<bytes;++i)require_byte(masks[i],0xff,i,where);
  }
};

template<unsigned width> class CsrBits {
  static_assert(width>0&&width<64);
  static constexpr uint64_t all=(uint64_t(1)<<width)-1;
  uint64_t known_=0;
 public:
  uint64_t known() const {return known_;}
  void reset() {known_=0;}
  void write() {known_=all;}
  // OR cannot bless an old unknown zero. It does establish every forced-one bit.
  void accumulate(uint64_t flags) {known_|=flags&all;}
  // CSRRS/CSRRC with rd=x0 need no observation; untouched bits remain unknown.
  void set_or_clear(uint64_t bits) {known_|=bits&all;}
  void require(uint64_t requested,Context where) const {
    requested&=all;
    if((known_&requested)!=requested) {
      for(unsigned i=0;i<width;i+=8)
        require_byte(uint8_t(known_>>i),uint8_t(requested>>i),i/8,where);
    }
  }
};
}
