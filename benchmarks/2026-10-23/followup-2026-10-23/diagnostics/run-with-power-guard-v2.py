#!/usr/bin/env python3
"""Abort this owned diagnostic if actual charging is lost; never changes host settings."""
import argparse, datetime, json, os, re, signal, subprocess, sys, time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log',required=True,type=Path)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command: parser.error('command required')
    args.log.parent.mkdir(parents=True,exist_ok=True)
    process=None
    interrupted=False
    with args.log.open('x') as stream:
        def record(kind,**data):
            row=dict(kind=kind,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),monotonic=time.monotonic(),**data)
            stream.write(json.dumps(row)+'\n');stream.flush()
        def check():
            result=subprocess.run(['pmset','-g','batt'],capture_output=True,text=True,timeout=10)
            text=result.stdout
            battery_lines=[line for line in text.splitlines() if 'InternalBattery-' in line]
            parsed=[]
            for line in battery_lines:
                parts=line.split(';')
                percent=re.search(r'(\d+)%',parts[0])
                state=parts[1].strip().lower() if len(parts)>1 else ''
                pct=int(percent.group(1)) if percent else None
                allowed=state in ('charging','charged') or (state=='finishing charge' and pct is not None and pct>=95)
                parsed.append(dict(state=state,percent=pct,allowed=allowed))
            safe=result.returncode==0 and any(line.strip()=="Now drawing from 'AC Power'" for line in text.splitlines()) and bool(parsed) and all(x['allowed'] for x in parsed)
            record('power',safe=safe,battery_states=parsed,returncode=result.returncode,stdout=text,stderr=result.stderr)
            return safe
        if not check():
            record('abort_before_launch',reason='actual charging precondition failed')
            return 2
        process=subprocess.Popen(command,start_new_session=True)
        record('launch',pid=process.pid,command=command)
        try:
            while process.poll() is None:
                time.sleep(10)
                if process.poll() is not None:break
                if not check():
                    interrupted=True
                    record('abort',reason='actual charging lost; SIGINT owned process group')
                    os.killpg(process.pid,signal.SIGINT)
                    try:process.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        record('cleanup_timeout',reason='controller still running; no automatic SIGKILL')
                        process.wait()
                    break
        except BaseException as error:
            record('wrapper_exception',error=repr(error))
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGINT)
                process.wait()
            raise
        record('exit',returncode=process.returncode,interrupted=interrupted)
        return 2 if interrupted else process.returncode
if __name__=='__main__':sys.exit(main())
