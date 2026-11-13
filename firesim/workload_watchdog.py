"""Bound the managed driver while preserving its foreground terminal access."""
import functools
import re

SECONDS=1500


def install(module=None):
    if module is None:
        import runtools.runtime_config as module
    owner=module.RuntimeHWConfig
    if getattr(owner,'_iris_workload_watchdog',False):raise RuntimeError('Workload watchdog already installed')
    original=owner.get_boot_simulation_command
    @functools.wraps(original)
    def command(*args,**kwargs):
        text=original(*args,**kwargs)
        bounds=re.findall(r"\+max-cycles=([^\s'\";&]+)",text)
        if ('+max-cycles' in text and (len(bounds)!=1 or not bounds[0].isdecimal()
                or not 0<int(bounds[0])<=2147483647)):
            raise RuntimeError('Archived driver max-cycles requires one positive signed32 bound; use the wall watchdog for longer runs')
        needle='&&  ./FireSim-corigine_mimicturbo_gt '
        if text.count(needle)!=1:raise RuntimeError('Managed non-AWS driver command changed; watchdog refuses to guess')
        # FireSim opens/configures its terminal. GNU timeout's default private
        # process group receives SIGTTIN/SIGTTOU inside screen/script, stopping
        # the wrapper before its timer can fire. Foreground mode preserves the
        # managed terminal group and bounds this exact driver child. FireSim's
        # owned final kill remains responsible for lifecycle cleanup.
        return text.replace(needle,'&& /usr/bin/timeout --foreground --signal=TERM --kill-after=30s '+str(SECONDS)+' ./FireSim-corigine_mimicturbo_gt ',1)
    owner.get_boot_simulation_command=command;owner._iris_workload_watchdog=True
