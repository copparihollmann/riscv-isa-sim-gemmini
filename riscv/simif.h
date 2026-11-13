// See LICENSE for license details.

#ifndef _RISCV_SIMIF_H
#define _RISCV_SIMIF_H

#include <map>
#include <exception>
#include "decode.h"
#include "cfg.h"
#include "iris_definedness.hpp"

class processor_t;
class mmu_t;
struct insn_fetch_t;
struct iris_timing_wait {};

// this is the interface to the simulator used by the processors and memory
class simif_t
{
public:
  // Shared canonical physical RAM shadow. Allocation/reset of host backing
  // storage does not establish target RAM bits; explicit writes do.
  iris_definedness::Memory iris_memory_definedness;
  // should return NULL for MMIO addresses
  virtual char* addr_to_mem(reg_t paddr) = 0;
  virtual bool reservable(reg_t paddr) { return addr_to_mem(paddr); }
  // used for MMIO addresses
  virtual bool mmio_fetch(reg_t paddr, size_t len, uint8_t* bytes) { return mmio_load(paddr, len, bytes); }
  virtual bool mmio_load(reg_t paddr, size_t len, uint8_t* bytes) = 0;
  virtual bool mmio_store(reg_t paddr, size_t len, const uint8_t* bytes) = 0;
  virtual bool is_debug_module_access(reg_t, size_t) { return false; }
  // Callback for processors to let the simulation know they were reset.
  virtual void proc_reset(unsigned id) = 0;
  virtual const insn_fetch_t* iris_completion_fetch(unsigned) const { return nullptr; }
  virtual std::exception_ptr iris_completion_exception(unsigned) const { return {}; }
  virtual void iris_issue(unsigned, reg_t, const insn_fetch_t&) {}
  virtual void iris_retired(unsigned, size_t) {}
  virtual void iris_counter_read(unsigned, reg_t, uint32_t, unsigned, reg_t, unsigned, const char*) {}
  virtual std::optional<reg_t> iris_mcycle_pre_edge(unsigned) const { return {}; }
  virtual void iris_validate_interrupts(unsigned, bool = false) const {}

  virtual const cfg_t &get_cfg() const = 0;
  virtual const std::map<size_t, processor_t*>& get_harts() const = 0;

  virtual const char* get_symbol(uint64_t paddr) = 0;

  virtual ~simif_t() = default;

  unsigned nprocs() const { return get_cfg().nprocs(); }

  mmu_t* debug_mmu;  // debug port into main memory, for use by debug_module
};

#endif
