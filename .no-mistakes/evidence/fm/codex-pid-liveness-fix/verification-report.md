# Linux/Codex PID-view live verification

## Tested revision and scope

- Tested head: `3695d70a9e3990b7875e9001a7d4307219a96e01`.
- Comparison base: `8b1618a49511d67b247f5f8091868b812bfcae2d`.
- Host: Linux; installed runtime: `codex-cli 0.163.0`; real PID namespaces and Python `os.pidfd_open` available.
- No tracked source/test changes, no linter or static-analysis invocation, no full-suite invocation, no pipeline-control or publication commands.
- All labs, isolated Codex homes, copied product code, generated records, and caches were created below the gate worktree's `.test-pid-tmp/` and removed.
- No operator home, login, credentials, shared app-server, default tmux server, Herdr session, or fleet was used.

## Named scenarios and observed results

### 1. A live Codex sandbox watcher no longer causes a false blind-stop alarm

The driver minted marked lab homes with `bin/fm-lab-home.sh create`, extracted the tested tracked tree into each home, initialized only their private Git metadata, and invoked the installed `codex sandbox -c 'sandbox_mode="workspace-write"' -- ...`.
The running product was the actual `fm-watch-checkpoint.sh`, `fm-watch.sh`, `fm-lock.sh`, and `fm-turnend-guard.sh`, not a substituted watcher or harness binary.
The guard's outside-namespace invocation used the production supervision-primary selection pin, not fabricated ancestry.

Direct-path evidence:

- Watcher recorded namespace-local PID `198`; `/proc` independently mapped its `NSpid` to host PID `216196`.
- Observer namespace `pid:[4026531836]` differed from watcher namespace `pid:[4026532917]`.
- The actual watcher environment contained the correct `FM_HOME` even though the sandbox started with it unset.
- Inside the namespace, the guard exited `0` without an alarm.
- Outside the namespace, ordinary `fm_watcher_healthy` exited `1`, while the fixed production guard exited `0` with empty stdout/stderr.
- As a counterfactual, replacing only the disposable lab's guard with the base commit's guard produced exit `2` and `TURN WOULD END BLIND` against the same running watcher and metadata; restoring the candidate guard returned exit `0`.

### 2. Invalid, stale, missing, and dead watcher evidence still blocks

Against the real sandbox watcher, the driver independently changed each persisted proof and invoked the real guard.
Every negative returned exit `2` with the blind-stop diagnostic:

- changed process start-time identity;
- wrong boot ID, home, watcher path, namespace, or PID;
- 400-second-old, future-dated, or absent beacon;
- absent namespace, boot-ID, or identity field;
- group/world-writable resolved lock directory;
- Python unavailable from an isolated PATH containing real host tools but no Python;
- saved real watcher proof replayed with a newly touched beacon after its namespace had exited.

The real watcher was frozen during ownership-record mutation so its own independent self-eviction did not invalidate later cases.
Restoring all evidence while the watcher was live returned exit `0`.
Guard invocations did not alter the live watcher's persisted lock proof.

### 3. Other primary-harness selections retain strict blocking

The same running cross-namespace watcher was evaluated with production primary selections for Claude, Cursor, OpenCode, Pi, pi-signed, Grok, Kimi, Gemini, Muse, Rovo, omp, agy, Devin, Command Code, Polytoken, Cortex, and Hermes.
Every non-Codex selection returned exit `2` rather than using the fallback.
These are live checks of Firstmate's guard selection interface, not claims that all vendor CLIs were launched.
The targeted existing namespace regression additionally exercised the non-Linux branch using a controlled platform shim; this is not native non-Linux evidence.

### 4. Default-home propagation works on direct and supervision-host checkpoint paths

Both real sandbox scenarios started with `FM_HOME` absent, acquired their own session lock through `fm-lock.sh`, and ran the actual checkpoint.
Each running watcher published a matching process-environment `FM_HOME`, PID namespace, current boot ID, full identity, and watcher path.
On the hosted path, the recorded inner/host PID mapping was `367` / `221882`, with namespace `pid:[4026532904]`; the strict predicate rejected it from outside and the Codex guard accepted it.
No model engine or login was necessary: the hosted scenario stayed quiet until its normal park boundary.

### 5. Watcher wake delivery, checkpoint boundaries, and cleanup remain functional

On the direct path, writing a terminal status drove the real watcher, which printed `signal: .../state/scenario.status`, persisted the wake queue, and returned checkpoint exit `0`.
The hosted checkpoint returned exit `124` and `checkpoint: no actionable wake within 30s`; its product ledger recorded `primary=codex` followed by its own `boundary` event.
Both paths removed all `.watch.lock*` artifacts before the dead-proof replay check and lab removal.
Neither ordinary strict liveness nor the guard mistook a fresh beacon after namespace exit for live supervision.

## Commands and supporting regression

```sh
unshare -rpf --mount-proc true
python3 -c 'import os; f=os.pidfd_open(os.getpid()); os.close(f)'
codex --version
codex sandbox --help
TMPDIR="$PWD/.test-pid-tmp" bin/fm-test-run.sh \
  tests/fm-turnend-guard.test.sh \
  tests/fm-watcher-lock.test.sh \
  tests/fm-watch-checkpoint.test.sh
python3 /home/ubuntu/.no-mistakes/evidence/01M6QHJDG177QJ4SB557V6WXWQ/live-pid-driver.py \
  "$PWD" /home/ubuntu/.no-mistakes/evidence/01M6QHJDG177QJ4SB557V6WXWQ/verified
```

The targeted runner completed successfully and its Linux namespace regression actually ran rather than capability-skipping.
Its internal MSYS-only process-identity case was skipped on Linux, as expected and unrelated to this Linux-only fix.
The complete raw log is `targeted-regression.log`.
Product responses, exact persisted proofs, namespace mappings, diagnostics, checkpoint outputs, and cleanup observations are in `verified/live-pid-results.json` and `verified/transcript.log`.
The repeatable driver is `live-pid-driver.py`.

## Setup corrections and evidence limits

The initial CLI probe used the obsolete `codex sandbox linux` spelling, which this version interprets as the command to execute; current `codex sandbox -- ...` succeeded.
The first sandbox probe also required creating its explicitly isolated `CODEX_HOME` directory before invocation.
An early hosted lab retained an extra shell wrapper, pushing harness ancestry beyond the detector's bounded walk and omitting optional namespace metadata; executing the checkpoint in place of that wrapper restored the representative process topology and passed.
A later adversarial attempt changed a live watcher's ownership record while it was still polling; the watcher correctly exited on that mismatch, so a subsequent test signal found no process.
The final driver freezes that real watcher before proof mutation and the complete re-drive passed.
Earlier transcripts are retained as setup history, not presented as product failures or successful runs.

This evidence exercises a real installed Codex workspace-write sandbox, real Linux namespaces/pidfd, and production Firstmate interfaces.
It does **not** establish native model-generated Codex Stop-hook dispatch or native non-Linux execution, and no new native model-driven Stop experiment was run.
Those are explicitly not inferred from a manually supplied guard payload or a platform shim.
There is no rendered UI change; CLI transcripts and persisted product state are the reviewer-visible artifacts, so screenshots are not applicable.
