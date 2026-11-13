#include <vpi_user.h>
#include <svdpi.h>
#include <map>
#include <string>
#include "testchip_tsi.h"
extern "C" void iris_rtl_load_write(uint64_t,size_t,const void*);
extern "C" void iris_rtl_load_read(uint64_t,size_t,void*);


class diag_tsi_t : public testchip_tsi_t {
 public:
  using testchip_tsi_t::testchip_tsi_t;
  uint64_t queued_words=0,write_bytes=0;
  bool direct_loading=false;
  void write_chunk(addr_t address,size_t bytes,const void* data) override {
    if(!direct_loading) queued_words +=5+bytes/4;write_bytes+=bytes;
    if(write_bytes<1100 || address<0x80000000)
      fprintf(stderr,"TSI_DIAG write addr=%lx bytes=%zu total_bytes=%lu queued=%lu\n",address,bytes,write_bytes,queued_words);
    testchip_tsi_t::write_chunk(address,bytes,data);
  }
  void read_chunk(addr_t address,size_t bytes,void* data) override {
    if(!direct_loading) queued_words+=5;
    fprintf(stderr,"TSI_DIAG read begin addr=%lx bytes=%zu queued=%lu\n",address,bytes,queued_words);
    testchip_tsi_t::read_chunk(address,bytes,data);
    fprintf(stderr,"TSI_DIAG read done addr=%lx bytes=%zu\n",address,bytes);
  }
  void load_program() override {
    fprintf(stderr,"TSI_DIAG load begin\n");
    direct_loading=has_loadmem;
    testchip_tsi_t::load_program();
    direct_loading=false;
    fprintf(stderr,"TSI_DIAG load queued bytes=%lu words=%lu\n",write_bytes,queued_words);
  }
  void load_mem_write(addr_t address,size_t bytes,const void* data) override { iris_rtl_load_write(address,bytes,data); }
  void load_mem_read(addr_t address,size_t bytes,void* data) override { iris_rtl_load_read(address,bytes,data); }
  void reset() override {
    fprintf(stderr,"TSI_DIAG reset begin\n");testchip_tsi_t::reset();
    fprintf(stderr,"TSI_DIAG reset queued bytes=%lu words=%lu\n",write_bytes,queued_words);
  }
};

std::map<int, testchip_tsi_t*> tsis;

// Remove VCS simv option from argv if it match pattern -X???=
void remove_vcs_simv_opt(int & argc, char **& argv){
    int idx = 0;
    while(idx < argc){
        std::string str = std::string(argv[idx]);
        if(str.length() > 1 && str[0] == '-' && str[1] != '-' && str.find('=') != std::string::npos){
            // Found -????=???? as VCS simv option
            for(int i = idx; i < argc - 1; i++){
                // Remove the current option
                argv[i] = argv[i + 1];
            }
            argc--;
        }else{
            idx++;
        }
    }
}

extern "C" int tsi_tick(
                        int chip_id,
                        unsigned char out_valid,
                        unsigned char *out_ready,
                        int out_bits,

                        unsigned char *in_valid,
                        unsigned char in_ready,
                        int *in_bits)
{
    bool out_fire = *out_ready && out_valid;
    bool in_fire = *in_valid && in_ready;
    bool in_free = !(*in_valid);

    auto it = tsis.find(chip_id);

    if (it == tsis.end()) {
        s_vpi_vlog_info info;
        if (!vpi_get_vlog_info(&info))
          abort();

        // Prevent simv option enter htif
        remove_vcs_simv_opt(info.argc, info.argv);

        // TODO: We should somehow inspect whether or not our backing memory supports loadmem, instead of unconditionally setting it to true
        tsis[chip_id] = new diag_tsi_t(info.argc, info.argv, true, chip_id);
    }

    testchip_tsi_t* tsi = tsis[chip_id];
    static uint64_t calls=0,sent=0,received=0;
    ++calls;if(tsi->in_valid()&&in_ready)++sent;if(out_valid&&tsi->out_ready())++received;
    if(calls<5 || calls%10000==0)fprintf(stderr,"TSI_DIAG tick=%lu sent=%lu recv=%lu inv=%d inready=%d outv=%d front=%08x\n",calls,sent,received,tsi->in_valid(),in_ready,out_valid,tsi->in_valid()?tsi->in_bits():0);
    tsi->tick(out_valid, out_bits, in_ready);
    tsi->switch_to_host();

    *in_valid = tsi->in_valid();
    *in_bits = tsi->in_bits();
    *out_ready = tsi->out_ready();

    return tsi->done() ? (tsi->exit_code() << 1 | 1) : 0;
}