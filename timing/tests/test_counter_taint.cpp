#include "counter_taint.hpp"
#include <cassert>
#include <limits>

int main() {
  spike_timing::CounterMemoryTaint labels(8);
  assert(!labels.read(100, 8));
  labels.write(100, 8, true);
  assert(labels.read(99, 2) && labels.read(107, 1));
  assert(!labels.read(108, 8));
  labels.write(102, 4, false);
  assert(labels.size() == 4 && !labels.read(102, 4));
  assert(labels.read(101, 2) && labels.read(105, 2));
  labels.write(100, 8, false);
  assert(labels.size() == 0);
  labels.write(100, 8, true);
  bool limited = false;
  try { labels.write(99, 2, true); } catch (const std::length_error &) { limited = true; }
  assert(limited && labels.size() == 8 && !labels.read(99, 1));
  bool wrapped = false;
  try { labels.read(std::numeric_limits<std::uint64_t>::max(), 2); }
  catch (const std::overflow_error &) { wrapped = true; }
  assert(wrapped);
  labels.write(std::numeric_limits<std::uint64_t>::max(), 1, false);
}
