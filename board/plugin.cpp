#include "iris_boot.hpp"
#include "sim.h"
#include "dts.h"
#include <fdt/libfdt.h>
#include <sstream>

class iris_bootreg_t final : public iris_board::BootAddressRegister {
 public:
  using BootAddressRegister::BootAddressRegister;
};
class iris_bootrom_t final : public iris_board::ReadOnlyBootROM {
 public:
  using ReadOnlyBootROM::ReadOnlyBootROM;
};

static uint64_t parse_number(const std::string& text) {
  size_t used = 0;
  auto value = std::stoull(text, &used, 0);
  if (used != text.size()) throw std::invalid_argument("Invalid Iris board address");
  return value;
}

static void require_range(const void* fdt, const char* node_path, reg_t expected,
                          unsigned long size, reg_t* base) {
  int node = fdt_path_offset(fdt, node_path);
  unsigned long found_size = 0;
  if (node < 0 || fdt_get_node_addr_size(fdt, node, base, &found_size, "reg") ||
      *base != expected || found_size != size)
    throw std::invalid_argument(std::string("Iris board DTB range mismatch: ") + node_path);
}

static iris_bootreg_t* iris_bootreg_parse(const void* fdt, const sim_t*, reg_t* base,
                                        const std::vector<std::string>& args) {
  if (args.size() > 1) throw std::invalid_argument("iris_bootreg takes optional boot entry");
  require_range(fdt, "/soc/boot-address-reg@1000", iris_board::bootreg_base, 0x1000, base);
  return new iris_bootreg_t(args.empty() ? 0x80000000 : parse_number(args[0]));
}
static std::string iris_bootreg_dts(const sim_t*, const std::vector<std::string>&) {
  return "    boot-address-reg@1000 { reg = <0 0x1000 0 0x1000>; reg-names = \"control\"; };\n";
}
static iris_bootrom_t* iris_bootrom_parse(const void* fdt, const sim_t*, reg_t* base,
                                        const std::vector<std::string>& args) {
  if (args.size() != 2) throw std::invalid_argument("iris_bootrom requires ROM prefix and DTB paths");
  require_range(fdt, "/soc/rom@10000", iris_board::rom_base, iris_board::rom_size, base);
  const auto dtb = iris_board::read_binary(args[1]);
  if (dtb.size() < sizeof(fdt_header) || fdt_check_header(dtb.data()) ||
      fdt_totalsize(dtb.data()) != dtb.size() ||
      fdt_totalsize(fdt) != dtb.size() || !std::equal(dtb.begin(), dtb.end(), static_cast<const char*>(fdt)))
    throw std::invalid_argument("ROM-appended DTB must exactly match Spike's active DTB");
  return new iris_bootrom_t(iris_board::read_binary(args[0]), dtb);
}
static std::string iris_bootrom_dts(const sim_t*, const std::vector<std::string>&) {
  return "    rom@10000 { compatible = \"sifive,rom0\"; reg = <0 0x10000 0 0x10000>; reg-names = \"mem\"; };\n";
}

REGISTER_DEVICE(iris_bootreg, iris_bootreg_parse, iris_bootreg_dts);
REGISTER_DEVICE(iris_bootrom, iris_bootrom_parse, iris_bootrom_dts);
