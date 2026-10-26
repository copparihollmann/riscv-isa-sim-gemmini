"""Focused source-service checks only; no functional or physical simulation."""
from pathlib import Path
import argparse
import os
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[5]
SOURCE=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,required=True)
    args=parser.parse_args()
    build=args.build_dir.absolute()
    if build==ROOT or ROOT in build.parents:
        parser.error('build directory must be outside source checkout')
    build.mkdir(parents=True,exist_ok=True)
    for name in ('loop_ws_execute_test','identity_test','queue_test','legacy_operand_test','packet_mapping','row_publication_test','publication_coverage_test','posted_source_test','posted_input_broadcast_test','posted_preload_dependency_test','posted_ws_total_rows_test','posted_zero_writer_test','posted_zero_load_test','posted_acc_dependency_test','posted_accumulator_test','command_ingress_test','posted_history_test','controller_visibility_test','registered_transport_test','reader_path_test','posted_readout_frontend_test','posted_one_beat_writer_test','aligned_i8_readout_test','full_accumulator_load_test','posted_source_d_test','masked_i8_readout_test','posted_full_packet_writer_test','posted_full_raw_readout_test'):
        binary=build/name
        subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror','-I'+str(SOURCE),'-I'+str(ROOT/'timing/core/include'),'-I'+str(ROOT),str(SOURCE/'tests'/(name+'.cpp')),'-o',str(binary)],check=True,timeout=60)
        subprocess.run([str(binary)],check=True,timeout=10)
    binary=build/'loader_bootstrap_test'
    subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror','-I'+str(ROOT),'-I'+str(ROOT/'timing/core/include'),str(SOURCE/'tests/loader_bootstrap_test.cpp'),'-o',str(binary)],check=True,timeout=60)
    subprocess.run([str(binary),str(build/'loader-bootstrap-fixture.elf')],check=True,timeout=10)
    subprocess.run([sys.executable,'-B',str(SOURCE/'tests/test_export.py')],check=True,timeout=20)
if __name__=='__main__': main()
