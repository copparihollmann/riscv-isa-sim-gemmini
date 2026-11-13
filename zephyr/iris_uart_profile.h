#ifndef IRIS_UART_PROFILE_H
#define IRIS_UART_PROFILE_H
#include <zephyr/kernel.h>
#include <zephyr/devicetree.h>
#include <zephyr/sys/printk.h>
#include <zephyr/sys/sys_io.h>
#include <soc.h>

/* Read the value programmed by the real selected Zephyr driver, before ROI. */
static inline void iris_uart_profile_report(void)
{
    const unsigned clock_hz=SIFIVE_PERIPHERAL_CLOCK_FREQUENCY;
    const unsigned baud=DT_PROP(DT_NODELABEL(uart0),current_speed);
    const unsigned divisor=sys_read32(DT_REG_ADDR(DT_NODELABEL(uart0))+0x18);
    if(divisor!=clock_hz/baud-1u)k_panic();
    printk("IRIS_UART_PROFILE {\"requested_baud\":%u,\"clock_hz\":%u,\"divisor\":%u}\n",baud,clock_hz,divisor);
}
#endif
