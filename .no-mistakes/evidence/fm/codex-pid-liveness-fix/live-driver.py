import os, subprocess as sp, tempfile, pathlib, time, json, shutil, signal
root=pathlib.Path.cwd(); evidence=pathlib.Path('/home/ubuntu/.no-mistakes/evidence/01M5N03K0467EQBHBBTRXETVN1')
lab=pathlib.Path(tempfile.mkdtemp(prefix='.pid-live-',dir=root)); proc=None
log=[]
def record(name, **kw):
    row=dict(name=name,**kw);log.append(row); print(json.dumps(row),flush=True)
def run(args,env,**kw): return sp.run(args,env=env,text=True,stdout=sp.PIPE,stderr=sp.PIPE,timeout=15,**kw)
try:
    sp.run(['bin/fm-lab-home.sh','create',str(lab)],check=True,stdout=sp.DEVNULL)
    # Disposable primary fixture: existing tracked instructions, unchanged.
    shutil.copy(root/'AGENTS.md',lab/'AGENTS.md'); (lab/'bin').symlink_to(root/'bin',target_is_directory=True)
    sp.run(['git','init','-q',str(lab)],check=True)
    (lab/'state/task.meta').touch()
    env=os.environ.copy()
    for key in list(env):
        if key.startswith('FM_'): env.pop(key)
    env.update(FM_HOME=str(lab),FM_SUPERVISION_ACTOR='branch',FM_SUPERVISION_PRIMARY_HARNESS='codex',FM_POLL='1',FM_CHECK_INTERVAL='999999',FM_SIGNAL_GRACE='1')
    output=open(evidence/'checkpoint-live.log','w')
    proc=sp.Popen(['codex','sandbox','-c','sandbox_mode="workspace-write"','--',str(root/'bin/fm-watch-checkpoint.sh'),'--seconds','45'],env=env,stdout=output,stderr=sp.STDOUT,start_new_session=True)
    lock=lab/'state/.watch.lock'; beat=lab/'state/.last-watcher-beat'
    deadline=time.monotonic()+12
    while not (lock/'pid-namespace').exists() or not beat.exists():
        if proc.poll() is not None or time.monotonic()>deadline: raise RuntimeError('checkpoint did not become ready')
        time.sleep(.1)
    fields={p.name:p.read_text().strip() for p in lock.iterdir() if p.is_file()}
    record('real sandbox watcher lock',fields=fields,observer_namespace=os.readlink('/proc/self/ns/pid'))
    def strict():
        return run(['bash','-c','. "$1"; fm_watcher_healthy "$2" "$3" 300 "$4"','_',str(root/'bin/fm-wake-lib.sh'),str(lab/'state'),str(root/'bin/fm-watch.sh'),str(lab)],env)
    result=strict(); record('strict host observer rejects sandbox-local PID',rc=result.returncode); assert result.returncode!=0
    guardenv=env|{'FM_ROOT_OVERRIDE':str(lab)}
    def guard(name,expected,harness='codex'):
        r=run(['bash',str(root/'bin/fm-turnend-guard.sh')],guardenv|{'FM_SUPERVISION_PRIMARY_HARNESS':harness},input='{"stop_hook_active":false}')
        record(name,rc=r.returncode,stdout=r.stdout,stderr=r.stderr)
        assert r.returncode==expected,(name,r.returncode)
        if expected==2: assert 'TURN WOULD END BLIND' in r.stderr+r.stdout
    guard('Codex accepts real cross-namespace watcher',0)
    r=run(['codex','sandbox','-c','sandbox_mode="workspace-write"','--','bash',str(root/'bin/fm-turnend-guard.sh')],guardenv,input='{"stop_hook_active":false}')
    record('inaccessible sibling watcher is safely rejected by sandbox guard',rc=r.returncode,stdout=r.stdout,stderr=r.stderr)
    assert r.returncode==2 and 'TURN WOULD END BLIND' in r.stderr
    r=run(['codex','sandbox','-c','sandbox_mode="workspace-write"','--','bash','-c','readlink /proc/self/ns/pid; for p in /proc/[0-9]*/ns/pid; do readlink "$p"; done'],guardenv)
    record('second sandbox visible PID namespaces',rc=r.returncode,stdout=r.stdout,stderr=r.stderr)
    guard('host recheck still accepts identical live watcher',0)

    for harness in ('claude','cursor','pi'):
        guard(harness+' retains strict rejection',2,harness)
    for field in ('boot-id','pid-identity','fm-home','watcher-path','pid-namespace'):
        p=lock/field; original=p.read_text(); p.write_text('wrong\n')
        guard('reject mismatched '+field,2); p.write_text(original)
    os.chmod(lock,0o777);guard('reject writable lock',2);os.chmod(lock,0o700)
    # Freeze the real watcher so it cannot refresh the beacon during stale checks.
    ns=fields['pid-namespace']; hostpid=None
    for p in pathlib.Path('/proc').glob('[0-9]*'):
        try:
            nspids=next(x.split()[1:] for x in (p/'status').read_text().splitlines() if x.startswith('NSpid:'))
            if os.readlink(p/'ns/pid')==ns and nspids[-1]==fields['pid']:hostpid=int(p.name)
        except (OSError,StopIteration):pass
    assert hostpid
    os.kill(hostpid,signal.SIGSTOP)
    os.utime(beat,(time.time()-400,)*2);guard('reject stale beacon',2)
    os.utime(beat,(time.time()+400,)*2);guard('reject future beacon',2)
    os.utime(beat,None);guard('restored evidence allows stop',0)
    os.kill(hostpid,signal.SIGKILL)
    time.sleep(.2);guard('dead watcher with retained fresh evidence is rejected',2)
    record('live scenarios complete',result='pass')
finally:
    if proc and proc.poll() is None:
        os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=10)
    if 'output' in locals():output.close()
    shutil.rmtree(lab)
    record('cleanup',lab_removed=not lab.exists())
    (evidence/'live-results.json').write_text(json.dumps(log,indent=2)+'\n')
