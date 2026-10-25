#include "model.hpp"
#include <stdexcept>
#include <string>
int main(int argc, char **argv) {
  if (argc != 3) return 2;
  const std::string mode(argv[2]);
  bool refused = false;
  try {
    spike_timing::Model model(argv[1]);
    if (mode == "reject") return 1;
    if (model.fp_operand_timing != (mode == "selected")) return 1;
  } catch (const std::exception &) { refused = true; }
  return refused == (mode == "reject") ? 0 : 1;
}
