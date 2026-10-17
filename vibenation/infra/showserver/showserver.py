#!/usr/bin/env python3
"""Create / provision / check / destroy the per-show GPU server on DigitalOcean.

The show server runs the live mix engine, the camera server and the GPU video encodes
(NVENC). It exists only for a show (~$0.76/h for an RTX 4000 Ada in TOR1) and is
destroyed afterwards. The build server pushes the code to it over SSH (no GitHub
credentials ever live on the show server).

usage:
  showserver.py plan                 # print what would be created and the price
  showserver.py create [--dry-run]   # create + wait for SSH + provision + verify NVENC
  showserver.py status               # list running show servers (and their cost so far)
  showserver.py provision <ip>       # (re)push code and services to a running server
  showserver.py destroy              # destroy every show server (tag vibenation-show)

Needs DIGITALOCEAN_TOKEN in vibenation/.env (never committed).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))  # vibenation/
TAG = 'vibenation-show'
REGION = os.environ.get('VN_SHOW_REGION', 'tor1')
SIZE = os.environ.get('VN_SHOW_SIZE', 'gpu-4000adax1-20gb')
IMAGE = os.environ.get('VN_SHOW_IMAGE', 'gpu-h100x1-base')  # DigitalOcean AI/ML-ready image (NVIDIA drivers)
API = 'https://api.digitalocean.com/v2'
SSH_KEY = os.path.expanduser('~/.ssh/vibenation_show')


def load_env() -> None:
    path = os.path.join(ROOT, '.env')
    if os.path.exists(path):
        for line in open(path):
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.rstrip('\n').split('=', 1)
                os.environ.setdefault(k, v)


def api(method: str, path: str, body: dict | None = None) -> dict:
    token = os.environ.get('DIGITALOCEAN_TOKEN')
    if not token:
        sys.exit('DIGITALOCEAN_TOKEN is not set in vibenation/.env')
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f'DigitalOcean API {method} {path}: {e.code} {e.read().decode()[:400]}')


def price() -> float | None:
    sizes = api('GET', '/sizes?per_page=200')['sizes']
    for s in sizes:
        if s['slug'] == SIZE:
            if REGION not in s.get('regions', []):
                print(f'warning: {SIZE} is not offered in {REGION} right now; regions: {s.get("regions")}')
            return float(s['price_hourly'])
    return None


def ensure_ssh_key() -> int:
    if not os.path.exists(SSH_KEY):
        subprocess.run(['ssh-keygen', '-t', 'ed25519', '-N', '', '-C', 'vibenation-build', '-f', SSH_KEY], check=True)
    pub = open(SSH_KEY + '.pub').read().strip()
    for k in api('GET', '/account/keys?per_page=200')['ssh_keys']:
        if k['public_key'].strip() == pub:
            return k['id']
    return api('POST', '/account/keys', {'name': 'vibenation-build', 'public_key': pub})['ssh_key']['id']


def droplets() -> list[dict]:
    return api('GET', f'/droplets?tag_name={TAG}&per_page=50')['droplets']


def public_ip(d: dict) -> str | None:
    for n in d['networks']['v4']:
        if n['type'] == 'public':
            return n['ip_address']
    return None


def ssh(ip: str, cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(['ssh', '-i', SSH_KEY, '-o', 'StrictHostKeyChecking=accept-new', '-o', 'ConnectTimeout=10',
                           f'root@{ip}', cmd], check=check, text=True, capture_output=True)


def cmd_plan() -> None:
    p = price()
    print(f'Would create: 1 × {SIZE} in {REGION}, image {IMAGE}, tag {TAG}.')
    print(f'Price: ${p:.2f}/hour' if p else 'Price: size not found (check VN_SHOW_SIZE)')
    if p:
        print(f'A 4-hour show (incl. setup) ≈ ${p * 4:.2f}.')


def cmd_create(dry: bool) -> None:
    if droplets():
        sys.exit('A show server already exists (run status / destroy).')
    cmd_plan()
    if dry:
        return
    key = ensure_ssh_key()
    user_data = open(os.path.join(HERE, 'cloud-init.yaml')).read()
    d = api('POST', '/droplets', {'name': f'vibenation-show-{time.strftime("%Y%m%d-%H%M")}', 'region': REGION, 'size': SIZE,
                                  'image': IMAGE, 'ssh_keys': [key], 'tags': [TAG], 'user_data': user_data, 'monitoring': True})['droplet']
    print(f'Created droplet {d["id"]}; waiting for it to boot…')
    ip = None
    for _ in range(120):
        d = api('GET', f'/droplets/{d["id"]}')['droplet']
        ip = public_ip(d)
        if d['status'] == 'active' and ip:
            break
        time.sleep(5)
    if not ip:
        sys.exit('Droplet did not become active in 10 minutes — destroy it with: showserver.py destroy')
    for _ in range(60):
        if ssh(ip, 'cloud-init status --wait >/dev/null 2>&1; echo ok', check=False).stdout.strip() == 'ok':
            break
        time.sleep(10)
    print(f'Show server up at {ip}. Provisioning…')
    cmd_provision(ip)


def cmd_provision(ip: str) -> None:
    # Code (no secrets except the runtime .env), our plugins, then the services.
    rsync = ['rsync', '-az', '--delete', '-e', f'ssh -i {SSH_KEY} -o StrictHostKeyChecking=accept-new',
             '--exclude', 'node_modules', '--exclude', '.venv', '--exclude', 'data', '--exclude', 'apps/android',
             '--exclude', 'services/audio/plugins/build', '--exclude', 'services/audio/plugins/.gen']
    subprocess.run([*rsync, ROOT + '/', f'root@{ip}:/opt/vibenation/'], check=True)
    subprocess.run(['rsync', '-az', '-e', f'ssh -i {SSH_KEY}', '/usr/local/lib/lv2/', f'root@{ip}:/usr/local/lib/lv2/'], check=True)
    r = ssh(ip, 'bash /opt/vibenation/infra/showserver/provision.sh', check=False)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        sys.exit('Provisioning failed (server left running for inspection; destroy when done).')
    print('NVENC check:', ssh(ip, 'cat /opt/vibenation/data/nvenc-check.txt', check=False).stdout.strip())


def cmd_status() -> None:
    ds = droplets()
    if not ds:
        print('No show server running.')
        return
    p = price() or 0
    for d in ds:
        age_h = (time.time() - time.mktime(time.strptime(d['created_at'], '%Y-%m-%dT%H:%M:%SZ'))) / 3600
        print(f'{d["name"]}  {public_ip(d)}  {d["status"]}  up {age_h:.1f} h  ≈ ${age_h * p:.2f} so far')


def cmd_destroy() -> None:
    ds = droplets()
    if not ds:
        print('Nothing to destroy.')
        return
    api('DELETE', f'/droplets?tag_name={TAG}')
    print(f'Destroyed {len(ds)} show server(s).')


if __name__ == '__main__':
    load_env()
    args = sys.argv[1:] or ['plan']
    {'plan': cmd_plan, 'status': cmd_status, 'destroy': cmd_destroy}.get(args[0], lambda: None)()
    if args[0] == 'create':
        cmd_create('--dry-run' in args)
    elif args[0] == 'provision':
        cmd_provision(args[1])
    elif args[0] not in ('plan', 'status', 'destroy'):
        sys.exit(__doc__)
