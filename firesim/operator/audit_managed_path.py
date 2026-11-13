#!/usr/bin/env python3
"""Bind local source + prior read-only observation. Never contacts the host."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SOURCE=Path('/scratch/eygao/iris-cy/sims/firesim')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    observed=ROOT/'build/access-privilege-details-20261106/report.json'
    info=json.loads(observed.read_text());remote={Path(row['path']).name:row for row in info['helpers']}
    names=['firesim-remove-xdma-module','firesim-load-xdma-module','firesim-chmod-xdma-perm','firesim-change-pcie-perms','firesim-fpga-util.py']
    helpers=[]
    for name in names:
        path=SOURCE/('platforms/corigine_mimicturbo_gt/scripts' if name.endswith('.py') else 'deploy/sudo-scripts')/name
        value=sha(path)
        if value!=remote[name]['sha256']:raise ValueError('Observed/source helper mismatch: '+name)
        helpers.append({'name':name,'source':str(path),'sha256':value,'remote_observation':remote[name],
            'route':'utility self-execs /usr/bin/sudo absolute protected helper'if name.endswith('.py')else'manager sudo /usr/local/bin/'+name})
    paths=[SOURCE/'deploy/runtools'/name for name in ['run_farm_deploy_managers.py','runtime_config.py','utils.py','firesim_topology_elements.py']]
    paths += [SOURCE/'deploy/config_runtime.yaml',ROOT/'firesim/source-clones.json',ROOT/'firesim/firesim-observed-dirty.patch',observed,Path(__file__).resolve()]
    paths += [Path(row['source']) for row in helpers]
    report={'schema':'iris.local_managed_privilege_audit.v1','hardware_contacted':False,'remote_install_performed':False,
        'observation_time_utc':info['observed_at_utc'],'source_revision':json.loads((ROOT/'firesim/source-clones.json').read_text())['source_revision'],
        'source_scope':'observed dirty manager tree; not a build or loaded-image attestation',
        'input_sha256':{str(path):sha(path)for path in paths},'active_helpers':helpers,
        'infrasetup_order':['copy slot infrastructure','extract matching driver','remove XDMA if loaded','program installed utility','load XDMA','chmod XDMA','change PCIe permissions'],
        'source_locations':{'Corigine inheritance':'run_farm_deploy_managers.py:1393','load/remove/chmod':'run_farm_deploy_managers.py:1077',
            'flash installed utility':'run_farm_deploy_managers.py:1175','PCIe permission helper':'run_farm_deploy_managers.py:1187',
            'infrasetup sequence':'run_farm_deploy_managers.py:1220','helper comparison':'utils.py:200','generic sudo predicate':'utils.py:23',
            'non-AWS driver launch':'runtime_config.py:515','non-AWS kill':'runtime_config.py:594','utility sudo exec':'firesim-fpga-util.py:153'},
        'generic_noninteractive_sudo':info['generic_noninteractive_sudo_read_probe'],
        'unsupported_generic_sudo_branches':['AWS NBD/module/package/rootfs operations','AWS boot/kill and shared-memory removal','privileged network-pipe start/kill'],
        'inactive_in_private_baremetal_no_net_jobs':['AWS instance deploy manager','rootfs mounts (common_rootfs null)','switch/pipe topology'],
        'generic_has_sudo_is_not_helper_capability':True,
        'root_helper_nested_insmod':'firesim-load-xdma-module internally invokes sudo insmod while already root; this does not grant callers generic sudo',
        'remaining_requirements':['operator installs reviewed fixed inspector','complete current all-user inspection','genuine exclusive operator allocation','held shared lock and full lifecycle','root driver/image pairing decision'],
        'managed_setup_tested_under_new_privileges':False,'loaded_image_verified':False,'calibration_usable':False}
    output=Path(__file__).with_name('managed-path-audit.json');output.write_text(json.dumps(report,indent=2)+'\n');print(output)
if __name__=='__main__':main()
