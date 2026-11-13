#include "iris_uart.hpp"
#include <iostream>
#include <vector>

using iris_board::UartRegisters;
static void check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
static void write(UartRegisters& uart, uint64_t address, uint64_t value, unsigned bytes=4) {
  uint8_t data[8];
  for (unsigned byte=0; byte<bytes; ++byte) data[byte] = uint8_t(value >> (byte * 8));
  check(uart.store(address, bytes, data), "UART store refused");
}
static uint64_t read(UartRegisters& uart, uint64_t address, unsigned bytes=4) {
  uint8_t data[8]{};
  check(uart.load(address, bytes, data), "UART load refused");
  uint64_t value=0;
  for (unsigned byte=0; byte<bytes; ++byte) value |= uint64_t(data[byte]) << (byte * 8);
  return value;
}
template<class F> static void unknown(F action) {
  bool refused=false;
  try { action(); } catch (const std::runtime_error&) { refused=true; }
  check(refused, "unknown RX FIFO RAM was silently backed with zero");
}
static UartRegisters uart(unsigned entries=256, uint16_t divisor=135) {
  return UartRegisters({entries, entries, divisor, 8});
}
static void receive(UartRegisters& device, uint8_t value) {
  check(device.begin_rx_frame() && device.complete_rx_frame(value), "RX frame not delivered");
}
int main() {
  unsigned cases=0;
  try {
    {
      auto u=uart();
      check(u.size()==0x1000 && !u.tx_enabled() && !u.rx_enabled() && !u.tx_busy() && u.tx_output(), "UART reset controls");
      check(read(u,0)==0 && read(u,7,1)==0x80 && read(u,0x18)==135 && read(u,0x14)==0, "UART reset registers");
      check(read(u,0x1c)==0 && read(u,0x20)==0 && read(u,0x24)==0 && read(u,0xffc)==0, "optional/undefined register zero");
      unknown([&] { read(u,4); }); unknown([&] { read(u,0,8); });
      uint8_t data[8]{};
      check(!u.load(1,4,data) && !u.load(0xffc,8,data) && !u.store(0,3,data), "UART invalid transaction accepted");
      ++cases;
    }
    {
      auto u=uart();
      write(u,0,0x800000aa); check(u.tx_count()==0, "full-bit quash did not suppress enqueue");
      for (unsigned i=0;i<256;++i) write(u,0,i);
      check(u.tx_count()==256 && read(u,0)==0x80000000, "FireSim FIFO is not 256 entries");
      write(u,0,17); check(u.tx_count()==256, "full nonblocking write must drop");
      u.advance_tx_cycles(1000000); check(u.tx_count()==256 && !u.tx_busy(), "disabled TX drained queued data");
      write(u,8,0x01000001); // txen=1, txwm=256 in its ninth bit.
      write(u,0x10,1);
      check(!u.irq(), "full queue below threshold256 predicate is false");
      u.advance_tx_cycles(1);
      check(u.tx_count()==255 && u.tx_busy() && u.tx_output() && u.irq(), "TX accept/IRQ timing");
      ++cases;
    }
    {
      auto u=uart();
      write(u,0xa,255,1); check(read(u,0xa,2)==0, "partial write to9bit watermark must not commit");
      write(u,0xb,1,1); check(read(u,0xa,2)==0, "ninth-bit-only write must not commit");
      write(u,0xa,511,2); check(read(u,0xa,2)==511, "watermark field width must include9bits");
      write(u,0x18,0xff,1); check(read(u,0x18)==135, "partial16bit divisor write must not commit");
      write(u,0x18,0,2); check(read(u,0x18)==0, "zero runtime divisor is legal");
      auto small=uart(8);
      write(small,0xa,0xf,1); check(read(small,0xa,2)==15, "base8entry watermark is4bits");
      ++cases;
    }
    {
      auto u=uart();
      std::vector<bool> levels;
      u.on_interrupt([&](bool level) { levels.push_back(level); });
      write(u,0xa,1,2); check(read(u,0x14)==1 && !u.irq(), "IP independent of IE");
      write(u,0x10,1); check(u.irq(), "TX IRQ missing");
      write(u,0,0xaa); check(!u.irq(), "TX IRQ predicate must compare actual FIFO count");
      write(u,0xa,511,2); check(u.irq(), "large TX watermark must not truncate to3bits");
      write(u,0x14,0); check(u.irq(), "IP is read-only");
      check(levels==std::vector<bool>({false,true,false,true}), "IRQ callback transitions");
      ++cases;
    }
    {
      auto u=uart();
      check(!u.begin_rx_frame(), "disabled RX began a frame");
      write(u,0xc,1); check(u.begin_rx_frame(), "enabled RX did not begin frame");
      write(u,0xc,0); check(u.complete_rx_frame(0xa5), "disabling RX incorrectly canceled in-flight frame");
      check(read(u,7,1)==0 && u.rx_count()==1, "status-only read consumed data");
      check(read(u,5,1)==0 && u.rx_count()==1, "padding read consumed data");
      check(read(u,4,1)==0xa5 && u.rx_count()==0 && read(u,7,1)==0x80, "RX byte read/dequeue");
      unknown([&] { read(u,4); }); check(u.rx_count()==0, "unknown read changed FIFO");
      ++cases;
    }
    {
      auto u=uart();
      write(u,0xc,1); write(u,0xe,255,2); write(u,0x10,2);
      for (unsigned i=0;i<256;++i) receive(u,uint8_t(i+42));
      check(u.rx_count()==256 && u.irq() && read(u,0x14)==2, "RX full/watermark");
      check(u.begin_rx_frame() && !u.complete_rx_frame(33), "RX full must drop completed frame without overwriting oldest");
      write(u,0xe,256,2); check(!u.irq(), "RX predicate usesstrictly greater");
      for (unsigned i=0;i<256;++i) check(read(u,4)==uint8_t(i+42), "RX order/data corruption");
      check(read(u,4)==0x8000002a, "empty queue must retain known RAM cell data");
      check(u.rx_count()==0, "empty read advanced dequeue pointer");
      ++cases;
    }
    {
      auto u=uart(256,2);
      std::vector<uint8_t> completed;
      u.on_transmitted([&](uint8_t value) { completed.push_back(value); });
      write(u,0,0xa5); write(u,8,1);
      const std::vector<unsigned> edges{2,5,8,11,14,17,20,23,26,29};
      const std::vector<bool> bits{0,1,0,1,0,0,1,0,1,1};
      unsigned cycle=0;
      for (unsigned i=0;i<edges.size();++i) {
        u.advance_tx_cycles(edges[i]-cycle); cycle=edges[i];
        check(u.tx_output()==bits[i], "UARTTx serial waveform or prescaler differs from source");
        check(completed.size()==unsigned(i==edges.size()-1), "TX completed before final stop edge");
      }
      check(!u.tx_busy() && completed==std::vector<uint8_t>{0xa5}, "TX byte completion");
      ++cases;
    }
    {
      auto u=uart(256,2);
      std::vector<uint8_t> completed;
      u.on_transmitted([&](uint8_t value) { completed.push_back(value); });
      write(u,0,1); write(u,0,2); write(u,8,1);
      u.advance_tx_cycles(4); write(u,8,0); u.advance_tx_cycles(25);
      check(completed==std::vector<uint8_t>{1} && !u.tx_busy() && u.tx_count()==1,
            "txen must gate new accepts, not abort current frame");
      u.advance_tx_cycles(1000); check(completed.size()==1 && u.tx_count()==1, "disabled TX accepted another byte");
      write(u,8,1); u.advance_tx_cycles(30); check(u.tx_busy(), "next frame ignored retained prescaler delay");
      u.advance_tx_cycles(1);
      check(completed==std::vector<uint8_t>({1,2}), "next TX frame did not retain prescaler state");
      auto two=uart(256,2); write(two,0,42); write(two,8,3);
      two.advance_tx_cycles(31); check(two.tx_busy(), "two-stop frame ended early");
      two.advance_tx_cycles(1); check(!two.tx_busy(), "two-stop frame duration");
      ++cases;
    }
    {
      auto u=uart(256,2);
      write(u,0,3); write(u,8,1); u.advance_tx_cycles(3);
      write(u,0x18,0,2);
      u.advance_tx_cycles(9); check(u.tx_busy(), "divisor update truncated in-flight prescaler");
      u.advance_tx_cycles(1); check(!u.tx_busy(), "divisor change not used at next pulse");
      ++cases;
    }
    {
      bool invalid=false;
      try { UartRegisters u({0xffffffffu,256,135,8}); } catch(const std::invalid_argument&) { invalid=true; }
      check(invalid,"unbounded FIFO allocation accepted");
      auto u=uart(); unsigned callbacks=0;
      u.on_interrupt([&](bool) { ++callbacks; u.on_interrupt({}); });
      write(u,0xa,1,2); write(u,0x10,1); check(callbacks==1,"self-unregister callback unsafe");
      ++cases;
    }
    std::cout << "{\"uart_helper\":\"pass\",\"cases\":" << cases
      << ",\"firesim_fifo_entries\":256,\"watermark_bits\":9,\"divisor_reset\":135,"
         "\"core_integrated\":false,\"rx_sampling_certified\":false,\"rtl_certified\":false}\n";
  } catch(const std::exception& error) { std::cerr << error.what() << '\n'; return 1; }
}
