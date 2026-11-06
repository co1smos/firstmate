#!/usr/bin/env python3
"""Disposable product-interface verification; no model, credentials or native Stop dispatch.
Run: python3 <this file> <gate worktree> <evidence directory>
"""
import json, os, pathlib, shutil, signal, subprocess, sys, tarfile, tempfile, time

ROOT = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
SCRATCH = ROOT / '.test-pid-tmp'
EVENTS = []
BASE = {k:v for k,v in os.environ.items() if not k.startswith(('FM_', 'HERDR_', 'CODEX_', 'PI_')) and k not in ('CLAUDECODE','CLAUDE_CODE_ENTRYPOINT','TMUX','TMUX_PANE','GIT_DIR','GIT_WORK_TREE','GIT_INDEX_FILE')}
BASE.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')

def emit(name, **kw):
    row = dict(check=name, **kw)
    EVENTS.append(row)
    print(json.dumps(row), flush=True)

def run(cmd, env=None, **kw):
    return subprocess.run(cmd, env=env or BASE, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=kw.pop('timeout',20), **kw)

def require(ok, message):
    if not ok: raise AssertionError(message)

def wait_for(predicate, process, seconds=30):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        if predicate(): return
        require(process.poll() is None, 'sandbox exited before ready')
        time.sleep(.05)
    raise AssertionError('sandbox readiness timeout')

def guard(home, harness='codex'):
    env=BASE | dict(FM_HOME=str(home), FM_ROOT_OVERRIDE=str(home), FM_SUPERVISION_ACTOR='branch', FM_SUPERVISION_PRIMARY_HARNESS=harness, FM_GUARD_GRACE='300', TMPDIR=str(home/'tmp'))
    result=run(['bash',str(home/'bin/fm-turnend-guard.sh')],env,input='{"stop_hook_active":false}')
    return result

def expect_guard(home, name, code, harness='codex'):
    result=guard(home,harness)
    emit(name, harness=harness, exit=result.returncode, stdout=result.stdout, stderr=result.stderr)
    require(result.returncode==code, name+': unexpected exit')
    require((code==0 and not result.stdout and not result.stderr) or (code==2 and 'TURN WOULD END BLIND' in result.stderr),name+': wrong diagnostic')

def strict(home):
    env=BASE | dict(FM_HOME=str(home), TMPDIR=str(home/'tmp'))
    return run(['bash','-c','. "$1/bin/fm-wake-lib.sh"; fm_watcher_healthy "$1/state" "$1/bin/fm-watch.sh" 300 "$1"','_',str(home)],env)

def observer(home):
    env=BASE | dict(FM_HOME=str(home), TMPDIR=str(home/'tmp'))
    return run(['bash','-c','. "$1/bin/fm-wake-lib.sh"; fm_watcher_cross_namespace_healthy "$1/state" "$1/bin/fm-watch.sh" 300 "$1"','_',str(home)],env)

def record(host, state):
    lock=state/'.watch.lock'
    return {p.name:p.read_text().strip() for p in lock.iterdir() if p.is_file()}

INNER = r'''set -u
home=$PWD
printf 'detected_harness=%s\n' "$(bin/fm-harness.sh)"
bin/fm-lock.sh || exit 81
readlink /proc/self/ns/pid > "$home/inner-namespace"
printf 'fm_home_initially=%s\n' "${FM_HOME-unset}"
bin/fm-watch-checkpoint.sh --seconds 120 > "$home/checkpoint.out" 2> "$home/checkpoint.err" &
checkpoint=$!
cleanup() { kill -INT "$checkpoint" 2>/dev/null || true; }
trap cleanup EXIT
for i in $(seq 1 600); do
  if [ -s "$home/state/.watch.lock/boot-id" ] && [ -f "$home/state/.last-watcher-beat" ]; then break; fi
  kill -0 "$checkpoint" 2>/dev/null || { wait "$checkpoint"; exit 82; }
  sleep .05
done
[ -s "$home/state/.watch.lock/pid" ] || exit 83
: > "$home/state/scenario.meta"
printf '{"stop_hook_active":false}' | bin/fm-turnend-guard.sh > "$home/inner-guard.out" 2> "$home/inner-guard.err"
printf '%s\n' "$?" > "$home/inner-guard.exit"
: > "$home/ready"
while [ ! -e "$home/release" ]; do sleep .1; done
wait "$checkpoint"
rc=$?
printf '%s\n' "$rc" > "$home/checkpoint.exit"
trap - EXIT
exit 0
'''

def scenario(mode):
    home=pathlib.Path(tempfile.mkdtemp(prefix='fm-lab-',dir=SCRATCH))
    process=None
    try:
        minted=run(['bash',str(ROOT/'bin/fm-lab-home.sh'),'create',str(home)])
        require(minted.returncode==0,minted.stderr)
        archive=subprocess.Popen(['git','archive','HEAD'],cwd=ROOT,env=BASE,stdout=subprocess.PIPE)
        extract= subprocess.run(['tar','-x','-C',str(home)],stdin=archive.stdout,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        archive.stdout.close()
        require(extract.returncode==0 and archive.wait()==0,'archive failed')
        require(run(['git','init','-q',str(home)]).returncode==0,'git init')
        (home/'tmp').mkdir()
        (home/'codex-home').mkdir()
        if mode=='host': (home/'config/supervision-host').write_text('claude\n')
        # Explicitly do not export FM_HOME: exercise checkpoint default-home propagation.
        env=BASE | dict(CODEX_HOME=str(home/'codex-home'), TMPDIR=str(home/'tmp'), FM_POLL='1', FM_SIGNAL_GRACE='1', FM_CHECK_INTERVAL='999999', FM_HEARTBEAT='999999', FM_SUPERVISION_HOST_POLL='1')
        with (OUT/f'{mode}-sandbox.stdout').open('w') as stdout, (OUT/f'{mode}-sandbox.stderr').open('w') as stderr:
            inner=INNER if mode=='direct' else '''set -u
printf 'detected_harness=%s\\n' "$(bin/fm-harness.sh)"
bin/fm-lock.sh || exit 81
printf 'fm_home_initially=%s\\n' "${FM_HOME-unset}"
exec bin/fm-watch-checkpoint.sh --seconds 30
'''
            process=subprocess.Popen(['codex','sandbox','-c','sandbox_mode="workspace-write"','--','bash','-c',inner],cwd=home,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            wait_for(lambda:(home/'ready').exists() if mode=='direct' else ((home/'state/.watch.lock/boot-id').exists() and (home/'state/.last-watcher-beat').exists()),process)
            if mode=='host': (home/'state/scenario.meta').touch()
            state=home/'state'; lock=state/'.watch.lock'
            values=record(home,state)
            namespace=values['pid-namespace']
            matches=[]
            for entry in pathlib.Path('/proc').glob('[0-9]*'):
                try:
                    if os.readlink(entry/'ns/pid')!=namespace: continue
                    nspids=next(x.split()[1:] for x in (entry/'status').read_text().splitlines() if x.startswith('NSpid:'))
                    if nspids[-1]==values['pid']: matches.append((entry,nspids))
                except (OSError,StopIteration): continue
            require(len(matches)==1,'watcher not uniquely mapped')
            proc,nspids=matches[0]
            host_pid=int(proc.name)
            home_env=('FM_HOME='+str(home)).encode() in (proc/'environ').read_bytes().split(b'\0')
            emit(mode+'-published-watcher', lock=values, host_pid=host_pid, nspids=nspids, observer_namespace=os.readlink('/proc/self/ns/pid'), process_FM_HOME_matches=home_env, same_namespace_guard_exit=(home/'inner-guard.exit').read_text().strip() if mode=='direct' else None, same_namespace_guard_stderr=(home/'inner-guard.err').read_text() if mode=='direct' else None)
            require(home_env and int(values['pid'])!=host_pid and namespace!=os.readlink('/proc/self/ns/pid'),'namespace or home proof missing')
            if mode=='direct': require((home/'inner-guard.exit').read_text().strip()=='0','same namespace strict guard failed')
            s=strict(home)
            emit(mode+'-strict-rejects-inner-pid',exit=s.returncode,stderr=s.stderr)
            require(s.returncode!=0,'strict liveness accepted inner PID')
            expect_guard(home,mode+'-cross-namespace-stop-allowed',0)
            if mode=='direct':
                guard_path=home/'bin/fm-turnend-guard.sh'
                fixed_guard=guard_path.read_bytes()
                baseline=run(['git','show','8b1618a49511d67b247f5f8091868b812bfcae2d:bin/fm-turnend-guard.sh'],cwd=ROOT)
                require(baseline.returncode==0,'baseline guard unavailable')
                try:
                    guard_path.write_text(baseline.stdout)
                    expect_guard(home,'baseline-reproduces-false-blind-stop',2)
                finally: guard_path.write_bytes(fixed_guard)
                expect_guard(home,'fixed-guard-removes-false-blind-stop',0)
                before={p.name:p.read_bytes() for p in lock.iterdir() if p.is_file()}
                for harness in ('claude','cursor','opencode','pi','pi-signed','grok','kimi','gemini','muse','rovo','omp','agy','devin','commandcode','polytoken','cortex','hermes'):
                    expect_guard(home,'non-codex-retains-strict-'+harness,2,harness)
                require(before=={p.name:p.read_bytes() for p in lock.iterdir() if p.is_file()},'guard modified watcher metadata')
                # Hold the subject while corrupting its ownership record: the real watcher
                # otherwise correctly evicts itself when it notices an identity mismatch.
                os.kill(host_pid,signal.SIGSTOP)
                for field,bad in [('pid-identity',values['pid-identity'].replace('linux-starttime=','linux-starttime=9',1)),('boot-id','00000000-0000-0000-0000-000000000000'),('fm-home',str(home/'wrong-home')),('watcher-path',str(home/'bin/not-watch.sh')),('pid-namespace',os.readlink('/proc/self/ns/pid')),('pid','99999999')]:
                    original=(lock/field).read_bytes()
                    (lock/field).write_text(bad+'\n')
                    expect_guard(home,'reject-mismatch-'+field,2)
                    (lock/field).write_bytes(original)
                # The real watcher remains frozen for deliberately stale/future beacons.
                beat=state/'.last-watcher-beat'
                try:
                    for age in (400,-600):
                        timestamp=time.time()-age; os.utime(beat,(timestamp,timestamp))
                        expect_guard(home,'reject-beacon-age-'+str(age),2)
                    beat.unlink()
                    expect_guard(home,'reject-absent-beacon',2)
                    beat.touch()
                    for field in ('pid-namespace','boot-id','pid-identity'):
                        original=(lock/field).read_bytes(); (lock/field).unlink()
                        expect_guard(home,'reject-missing-'+field,2)
                        (lock/field).write_bytes(original)
                    target=lock.resolve(); original_mode=target.stat().st_mode & 0o777
                    target.chmod(0o777)
                    expect_guard(home,'reject-writable-lock',2)
                    target.chmod(original_mode)
                finally: os.kill(host_pid,signal.SIGCONT)
                expect_guard(home,'valid-evidence-restored',0)
                tools=home/'without-python'; tools.mkdir()
                for tool in ('bash','dirname','cat','jq','git','ps','tr','sed','stat','awk','od','readlink','grep','uname','mkdir','basename','sleep','rm','ln','mktemp','date','touch'):
                    resolved=shutil.which(tool)
                    if resolved: (tools/tool).symlink_to(resolved)
                no_python_env=BASE | dict(PATH=str(tools),FM_HOME=str(home),FM_ROOT_OVERRIDE=str(home),FM_SUPERVISION_ACTOR='branch',FM_SUPERVISION_PRIMARY_HARNESS='codex',FM_GUARD_GRACE='300')
                denied=run([str(tools/'bash'),str(home/'bin/fm-turnend-guard.sh')],no_python_env,input='{"stop_hook_active":false}')
                emit('missing-python-blocks',exit=denied.returncode,stdout=denied.stdout,stderr=denied.stderr)
                require(denied.returncode==2 and 'TURN WOULD END BLIND' in denied.stderr,'missing Python did not retain safe block')
            # Drive a real watcher wake, not a fake watcher: a terminal status is queued and surfaced.
            if mode=='direct':
                (home/'release').touch()
                (state/'scenario.status').write_text('done: live PID scenario completed\n')
            process.wait(timeout=40)
            output=(home/'checkpoint.out').read_text() if mode=='direct' else (OUT/f'{mode}-sandbox.stdout').read_text()
            error=(home/'checkpoint.err').read_text() if mode=='direct' else (OUT/f'{mode}-sandbox.stderr').read_text()
            emit(mode+'-checkpoint-close',exit=process.returncode, stdout=output,stderr=error,queue=(state/'.wake-queue').read_text() if (state/'.wake-queue').exists() else '',host_log=(state/'.supervision-host.log').read_text() if (state/'.supervision-host.log').exists() else '')
            if mode=='direct': require(process.returncode==0 and ('signal:' in output or 'check:' in output),'real wake not returned')
            else: require(process.returncode==124 and 'checkpoint: no actionable wake within 30s' in output,'host did not end quietly at boundary')
            # Hosted path intentionally detaches a successor at handback; record it and stop this disposable namespace before checking the stale-proof negative.
            successor=record(home,state) if (lock/'pid').exists() else None
            if successor: emit(mode+'-handback-successor',lock=successor)
            # Container exits kill its own remaining processes. No cross-namespace cleanup/signal authority used by product.
            expect_guard(home,mode+'-after-sandbox-exit-blocks',2)
            residual=[str(p.relative_to(state)) for p in state.glob('.watch.lock*') if p.exists()]
            emit(mode+'-cleanup',remaining_watch_locks=residual)
            require(not residual,'watcher left lock files')
            # Re-present the actual now-dead process's saved proof with a fresh beacon.
            lock.mkdir(mode=0o700)
            for name,value in values.items(): (lock/name).write_text(value+'\n')
            (state/'.last-watcher-beat').touch()
            expect_guard(home,mode+'-dead-holder-with-fresh-saved-proof-blocks',2)
    except Exception as e:
        emit(mode+'-failure',error=str(e),home=str(home))
        for name in ('checkpoint.out','checkpoint.err','inner-guard.exit','inner-guard.err'):
            if (home/name).exists(): shutil.copy2(home/name,OUT/(mode+'-failure-'+name))
        with tarfile.open(OUT/(mode+'-failure-state.tar.gz'),'w:gz') as archive:
            archive.add(home/'state',arcname='state')
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL); process.wait(timeout=10)
        shutil.rmtree(home)
        emit(mode+'-lab-removed',absent=not home.exists())

try:
    emit('identity',head=run(['git','rev-parse','HEAD'],cwd=ROOT).stdout.strip(),codex_version=run(['codex','--version']).stdout.strip(),scope='real Codex workspace-write sandbox and production watcher/checkpoint/guard; NOT native model Stop dispatch')
    for selected_mode in sys.argv[3:] or ('direct','host'):
        scenario(selected_mode)
finally:
    (OUT/'live-pid-results.json').write_text(json.dumps(EVENTS,indent=2)+'\n')
