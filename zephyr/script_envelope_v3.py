"""Read-only util-linux script envelope validation for the archived scalar6 job.

This proves the captured command/header/footer correspondence. It does not
identify the remote script executable/version, which was not captured.
"""
import datetime as dt
import re

STAMP=r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\+00:00'
START=re.compile(r'Script started on (?P<stamp>'+STAMP+r') \[COMMAND="(?P<command>[^"\r\n]+)" TERM="screen" TTY="(?P<tty>/dev/pts/[0-9]+)" COLUMNS="(?P<columns>[1-9][0-9]*)" LINES="(?P<lines>[1-9][0-9]*)"\]')
END=re.compile(r'Script done on (?P<stamp>'+STAMP+r') \[COMMAND_EXIT_CODE="0"\]')
WRAPPER=re.compile(r'#!/usr/bin/env bash\nscreen -S fsim0 -d -m bash -c "script -f -c \'(?P<command>[^\'\r\n]*)\' uartlog"; sleep 1\n')

def need(value,message):
 if not value:raise ValueError(message)

def validate_envelope(console,wrapper):
 need(isinstance(console,str)and isinstance(wrapper,str),'Decoded UTF8 console/wrapper required')
 w=WRAPPER.fullmatch(wrapper);need(w is not None,'Exact archived screen/script invocation grammar')
 command=w['command'];need(command.startswith('stty intr ^] && /usr/bin/timeout --foreground --signal=TERM --kill-after=30s 180 ./FireSim-corigine_mimicturbo_gt ')and command.endswith(' && stty intr ^c'),'Archived180s foreground driver wrapper')
 need('+fesvr-step-size=128'in command and '+prog0=iris-batch0-batch.elf'in command and '+max-cycles'not in command,'Exact reviewed loader/program arguments')
 lines=console.splitlines();need(bool(lines),'Nonempty script console')
 while lines and lines[-1]=='':lines.pop()
 need(len(lines)>=2,'Script header and footer required')
 head=START.fullmatch(lines[0]);tail=END.fullmatch(lines[-1])
 need(head is not None,'Exact complete script header on first line')
 need(tail is not None,'Exact complete dated bracketed exit0 script footer on final line')
 need(console.count('Script started')==1 and console.count('Script done')==1 and console.count('COMMAND_EXIT_CODE')==1,'Unique host envelope and exit marker')
 need(head['command']==command,'Header COMMAND must equal actual archived sim-run.sh command byte-for-byte')
 need(0<int(head['columns'])<=65535 and 0<int(head['lines'])<=65535,'Valid captured terminal geometry')
 start=dt.datetime.fromisoformat(head['stamp']);end=dt.datetime.fromisoformat(tail['stamp'])
 need(start<=end and(end-start).total_seconds()<=360,'Valid ordered timestamps within managed phase bound')
 need('*** PASSED ***'in console and '*** FAILED ***'not in console and 'IRIS_FATAL'not in console,'Actual driver PASS without fatal output')
 return dict(schema='iris.archived_script_driver_envelope.v3',normal_driver_exit_zero=True,exact_bracketed_exit_marker=True,header_command_matches_captured_sim_run=True,unique_header_footer_and_exit=True,start_timestamp=start.isoformat(),end_timestamp=end.isoformat(),host_timestamp_duration_seconds=(end-start).total_seconds(),terminal=dict(TERM='screen',TTY=head['tty'],COLUMNS=int(head['columns']),LINES=int(head['lines'])),script_invocation='script -f -c COMMAND uartlog via screen/bash',remote_script_executable_identity=None,remote_script_version=None,scope='Captured host envelope/command consistency and normal exit only; remote tool identity/version was not captured; not a target timing observation')
