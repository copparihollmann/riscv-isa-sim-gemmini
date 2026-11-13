#define _POSIX_C_SOURCE 200809L
/* Five plain FASED configuration registers, exact archived8f map. No writes. */
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "Source-verified x86 little-endian MMIO contract required"
#endif
_Static_assert(sizeof(uint32_t)==4,"32-bit MMIO required");
enum{NREG=5,PRESENCE_OFFSET=356};
static const char*const names[NREG]={"writeLatency","readLatency","writeMaxReqs","readMaxReqs","relaxFunctionalModel"};
static const unsigned offsets[NREG]={0,4,8,12,72};
static const uint32_t presence_magic=UINT32_C(0x46697265);
typedef struct{int fd;void*map;size_t bytes;} mapping_t;
static int map_readonly(const char*path,int test,mapping_t*out){
  out->fd=open(path,O_RDONLY|O_SYNC);if(out->fd<0){perror("open read-only");return 1;}
  struct stat s;long page=sysconf(_SC_PAGESIZE);
  if(fstat(out->fd,&s)||page<PRESENCE_OFFSET+4||(test?(!S_ISREG(s.st_mode)||s.st_size<PRESENCE_OFFSET+4):!S_ISCHR(s.st_mode))){
    fprintf(stderr,"Wrong type/truncated read-only mapping\n");close(out->fd);return 1;}
  out->bytes=(size_t)page;out->map=mmap(NULL,out->bytes,PROT_READ,MAP_SHARED,out->fd,0);
  if(out->map==MAP_FAILED){perror("mmap read-only");close(out->fd);return 1;}return 0;
}
static int release(mapping_t*m){int a=munmap(m->map,m->bytes),b=close(m->fd);return a||b;}
static uint32_t read32(const mapping_t*m,unsigned offset){return ((volatile const uint32_t*)m->map)[offset/4];}
static int reject(const char*why){
  printf("{\"schema\":\"iris.readonly_fased_config_probe.v2\",\"status\":\"%s\",\"selected_parameters\":null,\"hardware_writes\":false,\"calibration_usable\":false}\n",why);return 1;
}
int main(int argc,char**argv){
  int test=0,pair=0;
  if(argc==3&&!strcmp(argv[1],"--read-idle-device")){
    if(strcmp(argv[2],"/dev/xdma0_user")){fprintf(stderr,"Only verified XDMA user target accepted\n");return 2;}
  }else if(argc==3&&!strcmp(argv[1],"--test-file")){test=1;}
  else if(argc==4&&!strcmp(argv[1],"--test-file-pair")){test=1;pair=1;}
  else{fprintf(stderr,"usage: --read-idle-device /dev/xdma0_user | --test-file FILE | --test-file-pair FIRST SECOND\n");return 2;}
  mapping_t first,second;if(map_readonly(argv[2],test,&first))return 1;
  uint32_t a[NREG],b[NREG];
  if(read32(&first,PRESENCE_OFFSET)!=presence_magic){release(&first);return reject("IRIS_FASED_BAD_PRESENCE_BEFORE");}
  for(unsigned i=0;i<NREG;++i)a[i]=read32(&first,offsets[i]);
  const mapping_t*last=&first;
  if(pair){if(map_readonly(argv[3],1,&second)){release(&first);return 1;}last=&second;}
  for(unsigned i=0;i<NREG;++i)b[i]=read32(last,offsets[i]);
  uint32_t after=read32(last,PRESENCE_OFFSET);
  int failed=release(&first);if(pair)failed|=release(&second);
  if(failed){perror("release read-only mapping");return 1;}
  if(after!=presence_magic)return reject("IRIS_FASED_BAD_PRESENCE_AFTER");
  for(unsigned i=0;i<NREG;++i){
    if(a[i]==UINT32_MAX||b[i]==UINT32_MAX)return reject("IRIS_FASED_ALL_ONES_REGISTER");
    if(a[i]!=b[i])return reject("IRIS_FASED_CHANGED_REGISTER");
  }
  if(a[4]>1)return reject("IRIS_FASED_RELAX_NOT_BOOL_DOMAIN");
  printf("{\"schema\":\"iris.readonly_fased_config_probe.v2\",\"test_file\":%s,\"hardware_writes\":false,\"access\":\"O_RDONLY/PROT_READ\",\"register_width_bits\":32,\"presence_byte_offset\":356,\"presence_verified_before_and_after\":true,\"stable_two_samples\":true",test?"true":"false");
  for(unsigned i=0;i<NREG;++i)printf(",\"%s\":{\"byte_offset\":%u,\"first\":%"PRIu32",\"second\":%"PRIu32"}",names[i],offsets[i],a[i],b[i]);
  printf(",\"configuration_registers_only\":true,\"calibration_usable\":false}\n");return 0;
}
