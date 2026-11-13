#ifndef IRIS_ZEPHYR_POW2_PACKET
#define IRIS_ZEPHYR_POW2_PACKET
#include <stdint.h>
#include <stddef.h>
#define GROUPS 486
#define REGIONS 648
#define STORAGE_BYTES 690048
#define GUARD 0x5ac31e79a64db208ULL
typedef struct {uint32_t kind,sew,lmul,shape,format,n,mask,trial,first;} group_t;
typedef struct {uint32_t group,hart,offset,bytes,elements,width;} descriptor_t;
typedef struct {uint64_t rid,gid,hart,logical,pin,start,issued,end,ir0,ir1,elements,failed,checksum,actual_vl,rows,cols,guard_ok,ack;} record_t;
typedef void (*kernel_fn)(unsigned);
extern void packet_measure(volatile record_t*,kernel_fn,unsigned);
extern void packet_vadd(unsigned),packet_mm_int(unsigned),packet_mm_e4(unsigned),packet_mm_e5(unsigned);
extern uint8_t inputs_a[2][256],inputs_b[2][256];
extern volatile uint8_t output_data[STORAGE_BYTES];
extern volatile record_t records[REGIONS];
extern const group_t *packet_groups;
extern const descriptor_t *packet_descriptors;
unsigned compute_run(unsigned rid);
unsigned long physical_hart(void);
#endif
