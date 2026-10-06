"""Collect fixed, read-only host measurements; publish no credentials or logs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

SERVICES = ("n8n", "pihole", "navidrome", "val-model", "val-controller",
            "val-whisper", "val-piper", "val-voice", "val-dashboard")
OUTPUT = Path(os.environ.get('VAL_STATUS_OUTPUT', '/srv/val/data/status/server.json'))


def cpu_ticks():
    values = [int(n) for n in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
    return sum(values), values[3] + values[4]


def collect():
    before, idle_before = cpu_ticks()
    time.sleep(0.25)
    after, idle_after = cpu_ticks()
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.split()[0]) * 1024
    disk = shutil.disk_usage('/')
    services = {}
    try:
        output = subprocess.run(
            ['/usr/bin/docker', 'container', 'ls', '--all', '--format', '{{json .}}'],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout
        rows = {row['Names']: row for row in map(json.loads, output.splitlines())}
        for name in SERVICES:
            row = rows.get(name)
            status = row.get('Status', '') if row else ''
            health = 'unhealthy' if '(unhealthy)' in status else 'healthy' if '(healthy)' in status else 'starting' if '(health: starting)' in status else 'not reported'
            services[name] = {'state': row.get('State', 'unknown') if row else 'missing', 'health': health}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        services = {name: {'state': 'unknown', 'health': 'unknown'} for name in SERVICES}
    return {
        'ok': True, 'collected_at': time.time(),
        'cpu_percent': round(100 * (1 - (idle_after - idle_before) / max(1, after - before)), 1),
        'memory_total': memory['MemTotal'], 'memory_available': memory['MemAvailable'],
        'disk_total': disk.total, 'disk_free': disk.free,
        'services': services,
    }


if __name__ == '__main__':
    result = collect()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix('.tmp')
    temporary.write_text(json.dumps(result) + '\n')
    os.chmod(temporary, 0o644)
    os.replace(temporary, OUTPUT)
