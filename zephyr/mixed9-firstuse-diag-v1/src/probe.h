#ifndef IRIS_FIRSTUSE_PROBE_H
#define IRIS_FIRSTUSE_PROBE_H
void iris_probe_init(void);
void iris_probe_arm(void);
unsigned iris_probe_ready(void);
void iris_probe_stamp(unsigned worker,unsigned pin,unsigned stage,unsigned iteration);
void iris_probe_done(unsigned physical_hart);
void iris_probe_observe(unsigned worker,unsigned pin);
#endif
