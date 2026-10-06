import json
import os
from pathlib import Path
import time

SERVER_NAME = os.environ.get('VAL_SERVER_NAME', 'Val server')


def read_status(path):
    result = json.loads(Path(path).read_text())
    age = time.time() - result['collected_at']
    if not 0 <= age <= 150:
        raise ValueError('server status snapshot is stale')
    return result


def format_status(result, focus=None):
    gib = 1024 ** 3
    total = result['memory_total'] / gib
    available = result['memory_available'] / gib
    focus = set(focus or ())
    full = not focus
    parts = []
    if full or 'cpu' in focus:
        parts.append(f"{SERVER_NAME}'s latest CPU sample is {result['cpu_percent']:.0f} percent usage.")
    if full or 'memory' in focus:
        parts.append(f"Memory: {total - available:.1f} of {total:.1f} GiB used, {available:.1f} GiB available.")
    if full or 'disk' in focus:
        parts.append(f"Disk: {result['disk_free'] / gib:.0f} of {result['disk_total'] / gib:.0f} GiB free.")
    labels = {'pihole': 'Pi-hole', 'n8n': 'n8n', 'navidrome': 'Navidrome'}
    for name, label in labels.items():
        if not (full or 'services' in focus or name in focus):
            continue
        service = result['services'][name]
        health = service['health']
        suffix = f", health check {health}" if health in ('healthy', 'unhealthy', 'starting') else ''
        parts.append(f"{label}: {service['state']}{suffix}.")
    if full or 'services' in focus or 'val' in focus:
        val = {k: v for k, v in result['services'].items() if k.startswith('val-')}
        problems = [f"{k}: {v['state']}, health {v['health']}" for k, v in val.items()
                    if v['state'] != 'running' or v['health'] in ('unhealthy', 'starting')]
        parts.append('Val services: ' + ('; '.join(problems) if problems else 'all running') + '.')
    return ' '.join(parts)
