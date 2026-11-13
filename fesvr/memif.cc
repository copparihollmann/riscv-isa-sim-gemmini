// See LICENSE for license details.

#include <algorithm>
#include <stdlib.h>
#include <string.h>
#include <stdexcept>
#include "memif.h"
#include "htif.h"

static void read_host_chunk(chunked_memif_t* port,addr_t addr,size_t bytes,void* data,
                            uint8_t* known) {
  if(auto* htif=dynamic_cast<htif_t*>(port))htif->iris_read_transport(addr,bytes,data,known);
  else {port->read_chunk(addr,bytes,data);std::fill_n(known,bytes,0xff);}
}
static void write_host_chunk(chunked_memif_t* port,addr_t addr,size_t bytes,const void* data,
                             const uint8_t* known) {
  if(auto* htif=dynamic_cast<htif_t*>(port))htif->iris_write_transport(addr,bytes,data,known);
  else port->write_chunk(addr,bytes,data);
}

void memif_t::read(addr_t addr, size_t len, void* bytes)
{
  size_t align = cmemif->chunk_align();
  if (len && (addr & (align-1)))
  {
    size_t this_len = std::min(len, align - size_t(addr & (align-1)));
    std::vector<uint8_t> chunk(align);
    std::vector<uint8_t> known(align);
    read_host_chunk(cmemif,addr&~(align-1),align,chunk.data(),known.data());
    for(size_t i=0;i<this_len;++i)if(known[(addr&(align-1))+i]!=0xff)
      throw std::runtime_error("IRIS_UNDEFINED_HOST_READ: requested bytes unknown");
    memcpy(bytes, &chunk[addr & (align-1)], this_len);

    bytes = (char*)bytes + this_len;
    addr += this_len;
    len -= this_len;
  }

  if (len & (align-1))
  {
    size_t this_len = len & (align-1);
    size_t start = len - this_len;
    std::vector<uint8_t> chunk(align);
    std::vector<uint8_t> known(align);
    read_host_chunk(cmemif,addr+start,align,chunk.data(),known.data());
    for(size_t i=0;i<this_len;++i)if(known[i]!=0xff)
      throw std::runtime_error("IRIS_UNDEFINED_HOST_READ: requested bytes unknown");
    memcpy((char*)bytes + start, &chunk[0], this_len);

    len -= this_len;
  }

  // now we're aligned
  size_t max_chunk = cmemif->chunk_max_size();
  for (size_t pos = 0; pos < len; pos += max_chunk)
    cmemif->read_chunk(addr + pos, std::min(max_chunk, len - pos), (char*)bytes + pos);
}

void memif_t::write(addr_t addr, size_t len, const void* bytes)
{
  size_t align = cmemif->chunk_align();
  if (len && (addr & (align-1)))
  {
    size_t this_len = std::min(len, align - size_t(addr & (align-1)));
    std::vector<uint8_t> chunk(align);
    std::vector<uint8_t> known(align);
    read_host_chunk(cmemif,addr&~(align-1),align,chunk.data(),known.data());
    memcpy(&chunk[addr & (align-1)], bytes, this_len);
    std::fill_n(known.begin()+(addr&(align-1)),this_len,0xff);
    write_host_chunk(cmemif,addr&~(align-1),align,chunk.data(),known.data());

    bytes = (char*)bytes + this_len;
    addr += this_len;
    len -= this_len;
  }

  if (len & (align-1))
  {
    size_t this_len = len & (align-1);
    size_t start = len - this_len;
    std::vector<uint8_t> chunk(align);
    std::vector<uint8_t> known(align);
    read_host_chunk(cmemif,addr+start,align,chunk.data(),known.data());
    memcpy(&chunk[0], (char*)bytes + start, this_len);
    std::fill_n(known.begin(),this_len,0xff);
    write_host_chunk(cmemif,addr+start,align,chunk.data(),known.data());

    len -= this_len;
  }

  // now we're aligned
  bool all_zero = len != 0;
  for (size_t i = 0; i < len; i++)
    all_zero &= ((const char*)bytes)[i] == 0;

  if (all_zero) {
    cmemif->clear_chunk(addr, len);
  } else {
    size_t max_chunk = cmemif->chunk_max_size();
    for (size_t pos = 0; pos < len; pos += max_chunk)
      cmemif->write_chunk(addr + pos, std::min(max_chunk, len - pos), (char*)bytes + pos);
  }
}

#define MEMIF_READ_FUNC \
  if(addr & (sizeof(val)-1)) \
    throw std::runtime_error("misaligned address"); \
  this->read(addr, sizeof(val), &val); \
  return val

#define MEMIF_WRITE_FUNC \
  if(addr & (sizeof(val)-1)) \
    throw std::runtime_error("misaligned address"); \
  this->write(addr, sizeof(val), &val)

target_endian<uint8_t> memif_t::read_uint8(addr_t addr)
{
  target_endian<uint8_t> val;
  MEMIF_READ_FUNC;
}

target_endian<int8_t> memif_t::read_int8(addr_t addr)
{
  target_endian<int8_t> val;
  MEMIF_READ_FUNC;
}

void memif_t::write_uint8(addr_t addr, target_endian<uint8_t> val)
{
  MEMIF_WRITE_FUNC;
}

void memif_t::write_int8(addr_t addr, target_endian<int8_t> val)
{
  MEMIF_WRITE_FUNC;
}

target_endian<uint16_t> memif_t::read_uint16(addr_t addr)
{
  target_endian<uint16_t> val;
  MEMIF_READ_FUNC;
}

target_endian<int16_t> memif_t::read_int16(addr_t addr)
{
  target_endian<int16_t> val;
  MEMIF_READ_FUNC;
}

void memif_t::write_uint16(addr_t addr, target_endian<uint16_t> val)
{
  MEMIF_WRITE_FUNC;
}

void memif_t::write_int16(addr_t addr, target_endian<int16_t> val)
{
  MEMIF_WRITE_FUNC;
}

target_endian<uint32_t> memif_t::read_uint32(addr_t addr)
{
  target_endian<uint32_t> val;
  MEMIF_READ_FUNC;
}

target_endian<int32_t> memif_t::read_int32(addr_t addr)
{
  target_endian<int32_t> val;
  MEMIF_READ_FUNC;
}

void memif_t::write_uint32(addr_t addr, target_endian<uint32_t> val)
{
  MEMIF_WRITE_FUNC;
}

void memif_t::write_int32(addr_t addr, target_endian<int32_t> val)
{
  MEMIF_WRITE_FUNC;
}

target_endian<uint64_t> memif_t::read_uint64(addr_t addr)
{
  target_endian<uint64_t> val;
  MEMIF_READ_FUNC;
}

target_endian<int64_t> memif_t::read_int64(addr_t addr)
{
  target_endian<int64_t> val;
  MEMIF_READ_FUNC;
}

void memif_t::write_uint64(addr_t addr, target_endian<uint64_t> val)
{
  MEMIF_WRITE_FUNC;
}

void memif_t::write_int64(addr_t addr, target_endian<int64_t> val)
{
  MEMIF_WRITE_FUNC;
}
