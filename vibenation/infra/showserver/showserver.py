#!/usr/bin/env python3
"""Create / provision / check / destroy the per-show GPU server on DigitalOcean.

The show server runs the live mix engine, the camera server and the GPU video encodes
(NVENC). It exists only for a show (~$0.76/h for an RTX 4000 Ada; TOR1 first, then the next region with capacity) and is
destroyed afterwards. The build server pushes the code to it over SSH (no GitHub
credentials ever live on the show server).

usage:
  showserver.py plan                 # print what would be created and the price
  showserver.py create [--dry-run] [--retry <min>]  # first free region; create + provision + verify NVENC
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
# Tried in order; a full region (or one without this GPU/image) refuses the create, which costs nothing.
REGIONS = [r.strip() for r in os.environ.get('VN_SHOW_REGIONS', os.environ.get('VN_SHOW_REGION', 'tor1,nyc2,atl1,ric1,sfo3,mkc1,mem1')).split(',') if r.strip()]
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


class ApiError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f'{code} {message}')
        self.code, self.message = code, message


def api(method: str, path: str, body: dict | None = None, fatal: bool = True) -> dict:
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
        raw = e.read().decode()
        try:
            msg = json.loads(raw).get('message', raw)
        except ValueError:
            msg = raw
        if not fatal:
            raise ApiError(e.code, str(msg)[:400]) from None
        sys.exit(f'DigitalOcean API {method} {path}: {e.code} {str(msg)[:400]}')


def price() -> float | None:
    sizes = api('GET', '/sizes?per_page=200')['sizes']
    for s in sizes:
        if s['slug'] == SIZE:
            free = s.get('regions', [])
            print(f'Regions with free capacity right now (API): {", ".join(free) if free else "none listed"}')
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
    print(f'Would create: 1 × {SIZE}, first free region of {", ".join(REGIONS)}, image {IMAGE}, tag {TAG}.')
    print(f'Price: ${p:.2f}/hour' if p else 'Price: size not found (check VN_SHOW_SIZE)')
    if p:
        print(f'A 4-hour show (incl. setup) ≈ ${p * 4:.2f}.')


def try_regions(key: int, user_data: str) -> dict | None:
    """One pass over REGIONS. Returns the new droplet, or None if every region refused."""
    for region in REGIONS:
        try:
            d = api('POST', '/droplets', {'name': f'vibenation-show-{time.strftime("%Y%m%d-%H%M")}', 'region': region, 'size': SIZE,
                                          'image': IMAGE, 'ssh_keys': [key], 'tags': [TAG], 'user_data': user_data,
                                          'monitoring': True}, fatal=False)['droplet']
            print(f'{region}: created.')
            return d
        except ApiError as e:
            if e.code != 422:  # 422 = this region can't take it (capacity, size or image); anything else is real
                sys.exit(f'DigitalOcean API POST /droplets ({region}): {e}')
            print(f'{region}: not available ({e.message})')
    return None


def cmd_create(dry: bool, retry_min: int) -> None:
    if droplets():
        sys.exit('A show server already exists (run status / destroy).')
    cmd_plan()
    if dry:
        return
    key = ensure_ssh_key()
    user_data = open(os.path.join(HERE, 'cloud-init.yaml')).read()
    deadline = time.time() + retry_min * 60
    while (d := try_regions(key, user_data)) is None:
        if time.time() >= deadline:
            sys.exit('No region has capacity right now (nothing was created or charged). Try again later, '
                     'or retry automatically with: showserver.py create --retry <minutes>')
        print('All regions full; trying again in 5 minutes…')
        time.sleep(300)
    print(f'Created droplet {d["id"]} in {d["region"]["slug"]}; waiting for it to boot…')
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
        retry = int(args[args.index('--retry') + 1]) if '--retry' in args else 0
        cmd_create('--dry-run' in args, retry)
    elif args[0] == 'provision':
        cmd_provision(args[1])
    elif args[0] not in ('plan', 'status', 'destroy'):
        sys.exit(__doc__)
