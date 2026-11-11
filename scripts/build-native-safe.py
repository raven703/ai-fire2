"""Single native build with host pressure watchdog; no global Docker cleanup."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time

root = Path(__file__).resolve().parents[1]
lock = open('/tmp/ai-fire2-heavy.lock', 'w')
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit('Another guarded heavy task is running')
artifacts = root / 'artifacts'
artifacts.mkdir(exist_ok=True)


def memory():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        name, value = line.split(':', 1)
        values[name] = int(value.strip().split()[0]) // 1024
    return values['MemAvailable'], values['SwapTotal'] - values['SwapFree']


available, swap = memory()
if available < 4096 or swap > 512:
    raise SystemExit(f'Unsafe starting pressure: available={available} MiB swap_used={swap} MiB')
with (artifacts / 'native-build-3072.log').open('w') as log, (artifacts / 'native-build-memory.csv').open('w') as stats:
    stats.write('seconds,available_mib,swap_used_mib\n')
    process = subprocess.Popen(['docker', 'build', '-f', 'docker/Dockerfile.native',
                                '-t', 'ai-fire2-native:source', '.'], cwd=root,
                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    started = time.monotonic()
    stopped = False
    try:
        while process.poll() is None:
            available, swap = memory()
            stats.write(f'{int(time.monotonic()-started)},{available},{swap}\n')
            stats.flush()
            log.flush()
            if 'FATAL ERROR:' in (artifacts / 'native-build-3072.log').read_text(errors='replace'):
                print('STOP: Node reported fatal heap exhaustion; cancelling own build', flush=True)
                stopped = True
                os.killpg(process.pid, signal.SIGINT)
                break
            if available < 1024 or swap > 768:
                print(f'STOP resource pressure: available={available} MiB swap_used={swap} MiB', flush=True)
                stopped = True
                os.killpg(process.pid, signal.SIGINT)
                break
            time.sleep(2)
        try:
            status = process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            status = process.wait(timeout=15)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
    print(f'Build exit={status}; watchdog_stop={stopped}', flush=True)
    raise SystemExit(75 if stopped else status)