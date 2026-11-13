from pathlib import Path
import subprocess,shutil,hashlib,json
R=Path(__file__).resolve().parents[2];Z=R/'third_party/zephyr-flush-frontier-v1';H=Path(__file__).resolve().parent
assert subprocess.check_output(['git','-C',str(Z),'rev-parse','HEAD'],text=True).strip()=='cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0'
shutil.copyfile(H/'iris_flush_frontier.c',Z/'arch/riscv/core/iris_flush_frontier.c');shutil.copyfile(H/'iris_flush_frontier.h',Z/'include/zephyr/arch/riscv/iris_flush_frontier.h')
p=Z/'arch/riscv/core/CMakeLists.txt';p.write_text(p.read_text()+'\nzephyr_sources(iris_flush_frontier.c)\n')
for name in ['arch/riscv/core/fpu.c','arch/riscv/core/ipi_clint.c','drivers/timer/riscv_machine_timer.c']:
 p=Z/name;s=p.read_text();s='#include <zephyr/arch/riscv/iris_flush_frontier.h>\n'+s
 def once(old,new):
  global s
  assert s.count(old)==1,(name,old,s.count(old));s=s.replace(old,new,1)
 if name.endswith('fpu.c'):
  # Calls are scalar compiler barriers, never hardware drain fences.
  stamp=lambda n,peer='0':f'iris_frontier_stamp({n},(uintptr_t)_current_cpu->arch.fpu_owner,(uintptr_t)_current,(uintptr_t)({peer}));'
  once('void z_riscv_vstate_save(struct z_riscv_v_context *save_to)\n{','void z_riscv_vstate_save(struct z_riscv_v_context *save_to)\n{\n\t'+stamp(300,'save_to'))
  once('\tz_riscv_vstate_csr_save(save_to);','\tz_riscv_vstate_csr_save(save_to);\n\t'+stamp(301,'save_to'))
  needle='\t\t       : "memory");\n#ifdef CONFIG_RISCV_IRIS_VME_CONTEXT\n\tif (save_to->iris_vme_initialized)';once(needle,'\t\t       : "memory");\n\t'+stamp(302,'save_to')+'\n#ifdef CONFIG_RISCV_IRIS_VME_CONTEXT\n\tif (save_to->iris_vme_initialized)')
  once('void z_riscv_vstate_restore(struct z_riscv_v_context *restore_from)\n{','void z_riscv_vstate_restore(struct z_riscv_v_context *restore_from)\n{\n\t'+stamp(310,'restore_from'))
  once('\tz_riscv_vstate_csr_restore(restore_from);','\t'+stamp(311,'restore_from')+'\n\tz_riscv_vstate_csr_restore(restore_from);\n\t'+stamp(312,'restore_from'))
  once('\tz_riscv_fpu_restore(&_current->arch.saved_fp_context);','\t'+stamp(120)+'\n\tz_riscv_fpu_restore(&_current->arch.saved_fp_context);\n\t'+stamp(121))
  once('void arch_flush_local_fpu(void)\n{','void arch_flush_local_fpu(void)\n{\n\t'+stamp(100))
  once('\t\t\tz_riscv_fpu_save(&owner->arch.saved_fp_context);','\t\t\t'+stamp(102,'owner')+'\n\t\t\tz_riscv_fpu_save(&owner->arch.saved_fp_context);\n\t\t\t'+stamp(103,'owner'))
  once('\t\tatomic_ptr_clear(&_current_cpu->arch.fpu_owner);','\t\t'+stamp(106,'owner')+'\n\t\tatomic_ptr_clear(&_current_cpu->arch.fpu_owner);\n\t\t'+stamp(107,'owner'))
  once('\t\tarch_flush_fpu_ipi(i);','\t\t'+stamp(201,'i')+'\n\t\tarch_flush_fpu_ipi(i);\n\t\t'+stamp(202,'i'))
  once('\t\t\t} while (owner == thread);','\t\t\t} while (owner == thread);\n\t\t\t'+stamp(203,'i'))
 elif name.endswith('ipi_clint.c'):
  stamp=lambda n,peer='0':f'iris_frontier_stamp({n},(uintptr_t)_current_cpu->arch.fpu_owner,(uintptr_t)_current,(uintptr_t)({peer}));'
  once('void arch_flush_fpu_ipi(unsigned int cpu)\n{','void arch_flush_fpu_ipi(unsigned int cpu)\n{\n\t'+stamp(200,'cpu'))
  once('\tatomic_val_t pending_ipi = atomic_clear(&cpu_pending_ipi[_current_cpu->id]);','\tatomic_val_t pending_ipi = atomic_clear(&cpu_pending_ipi[_current_cpu->id]);\n\t'+stamp(400,'pending_ipi'))
  once('\t\tarch_flush_local_fpu();','\t\t'+stamp(401,'pending_ipi')+'\n\t\tarch_flush_local_fpu();\n\t\t'+stamp(402,'pending_ipi'))
 else:
  once('static void set_mtimecmp(uint64_t time)\n{','static void set_mtimecmp(uint64_t time)\n{\n\tif (iris_frontier_preserve_hart1_cmp()) return;')
  once('static void timer_isr(const void *arg)\n{','static void timer_isr(const void *arg)\n{\n\tiris_frontier_timer_entry(); /* BEFORE lock, accounting, announcement and scheduler. */')
 p.write_text(s)
subprocess.run(['git','-C',str(Z),'add','-N','.'],check=True);patch=subprocess.check_output(['git','-C',str(Z),'diff','--binary','HEAD']);(H/'kernel.patch').write_bytes(patch)
print(json.dumps(dict(source=str(Z),patch_sha256=hashlib.sha256(patch).hexdigest(),original_overlay_preserved=True)))
