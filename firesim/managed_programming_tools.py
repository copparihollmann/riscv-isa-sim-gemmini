"""Bind the installed Xilinx paths for the existing managed programming helper."""
import functools
import shlex

TOOLS={'vivado_bin':'/tools/xilinx/2026.1/Vivado_Lab/bin/vivado_lab',
       'hw_server_bin':'/tools/xilinx/2026.1/Vivado_Lab/bin/hw_server'}


def install(module=None):
    if module is None:
        import runtools.run_farm_deploy_managers as module
    if getattr(module,'_iris_programming_tools_installed',False):raise RuntimeError('Programming tool binding already installed')
    original=module.run
    @functools.wraps(original)
    def run(*args,**kwargs):
        command=args[0]if args else kwargs.get('command')
        try:words=shlex.split(command)if isinstance(command,str)else[]
        except ValueError:words=[]
        if (len(words)==5 and words[0]=='/usr/local/bin/firesim-fpga-util.py'
                and words[1]=='--bitstream-map' and words[3]=='--fpga-db'):
            command+=' --vivado-bin '+shlex.quote(TOOLS['vivado_bin'])+' --hw-server-bin '+shlex.quote(TOOLS['hw_server_bin'])
            if args:args=(command,*args[1:])
            else:kwargs=dict(kwargs,command=command)
        return original(*args,**kwargs)
    module.run=run;module._iris_programming_tools_installed=True
