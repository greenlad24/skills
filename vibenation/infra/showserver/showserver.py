#!/usr/bin/env python3
"""Create / provision / check / destroy the per-show GPU server on DigitalOcean.

The show server runs the live mix engine, the camera server and the GPU video encodes
(NVENC). It exists only for a show (~$0.76/h for an RTX 4000 Ada; TOR1 first, then the next region with capacity) and is
destroyed afterwards. The build server pushes the code to it over SSH (no GitHub
credentials ever live on the show server).

usage:
  showserver.py plan                 # print what would be created and the price
  showserver.py create [--dry-run] [--retry <min>] [--ttl <min>] [--size S] [--image I] [--regions a,b]
                                     # first free region; create + provision + verify NVENC;
                                     # auto-destroyed after --ttl minutes (default 120)
  showserver.py status               # list running show servers (and their cost so far)
  showserver.py provision <ip>       # (re)push code and services to a running server
  showserver.py destroy              # destroy every show server (tag vibenation-show)
  showserver.py reap                 # destroy show servers past their time-to-live (run by a timer)
  showserver.py connect <ip>         # point the web app at a show server (SSH tunnel); create does this
  showserver.py disconnect           # back to the build server's own engine; destroy does this

Needs DIGITALOCEAN_TOKEN in vibenation/.env (never committed).
"""

from __future__ import annotations

import calendar
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
# Safety net: every show server carries a time-to-live tag (vn-ttl-<minutes>); the reaper timer on
# the build server destroys it once it is older than that, even if this script or Claude dies.
DEFAULT_TTL_MIN = int(os.environ.get('VN_SHOW_TTL_MIN', '120'))


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


def age_min(d: dict) -> float:
    return (time.time() - calendar.timegm(time.strptime(d['created_at'], '%Y-%m-%dT%H:%M:%SZ'))) / 60


def ttl_min(d: dict) -> int:
    for t in d.get('tags', []):
        if t.startswith('vn-ttl-') and t.endswith('m') and t[7:-1].isdigit():
            return int(t[7:-1])
    return DEFAULT_TTL_MIN  # untagged show server: default limit


def try_regions(key: int, user_data: str, ttl: int) -> dict | None:
    """One pass over REGIONS. Returns the new droplet, or None if every region refused."""
    for region in REGIONS:
        try:
            d = api('POST', '/droplets', {'name': f'vibenation-show-{time.strftime("%Y%m%d-%H%M")}', 'region': region, 'size': SIZE,
                                          'image': IMAGE, 'ssh_keys': [key], 'tags': [TAG, f'vn-ttl-{ttl}m'], 'user_data': user_data,
                                          'monitoring': True}, fatal=False)['droplet']
            print(f'{region}: created.')
            return d
        except ApiError as e:
            if e.code != 422:  # 422 = this region can't take it (capacity, size or image); anything else is real
                sys.exit(f'DigitalOcean API POST /droplets ({region}): {e}')
            print(f'{region}: not available ({e.message})')
    return None


def cmd_create(dry: bool, retry_min: int, ttl: int) -> None:
    if droplets():
        sys.exit('A show server already exists (run status / destroy).')
    cmd_plan()
    print(f'Auto-destroy after {ttl} min (≈ ${(price() or 0) * ttl / 60:.2f} at most).')
    if dry:
        return
    key = ensure_ssh_key()
    user_data = open(os.path.join(HERE, 'cloud-init.yaml')).read()
    deadline = time.time() + retry_min * 60
    while (d := try_regions(key, user_data, ttl)) is None:
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
    cmd_connect(ip)


# Only these settings go to the show server. Everything else in .env (DigitalOcean token,
# platform OAuth secrets, API keys the show server doesn't use) stays on the build server.
SHOW_ENV_KEYS = {'PORT'}
SHOW_ENV_PREFIXES = ('VN_', 'LIVEKIT_', 'GEMINI_')


def _sent(key: str) -> bool:
    return key in SHOW_ENV_KEYS or key.startswith(SHOW_ENV_PREFIXES)


# Tonight's topology: phones keep using LiveKit on the build server (HTTPS, already working);
# the show server's video service subscribes to it over the internet and encodes on the GPU.
SHOW_OVERRIDES = {'LIVEKIT_URL': 'wss://app.jeeznews.com', 'VN_VIDEO_PROFILE': 'gpu'}
# The build server's web app reaches the show server's engines through an SSH tunnel on these ports.
TUNNEL = {'VN_AUDIO_URL': (18091, 8091), 'VN_VIDEO_URL': (18092, 8092)}
TUNNEL_UNIT = '/etc/systemd/system/vibenation-showtunnel.service'
APP_DROPIN = '/etc/systemd/system/vibenation.service.d/show-server.conf'


def show_env() -> str:
    path = os.path.join(ROOT, '.env')
    lines = open(path).read().splitlines() if os.path.exists(path) else []
    keep = [l for l in lines if '=' in l and _sent(l.split('=', 1)[0].strip()) and l.split('=', 1)[0].strip() not in SHOW_OVERRIDES]
    return ''.join(l + '\n' for l in keep) + ''.join(f'{k}={v}\n' for k, v in SHOW_OVERRIDES.items())


def _sudo_write(path: str, text: str) -> None:
    subprocess.run(['sudo', 'mkdir', '-p', os.path.dirname(path)], check=True)
    subprocess.run(['sudo', 'tee', path], input=text, text=True, check=True, stdout=subprocess.DEVNULL)


def cmd_connect(ip: str) -> None:
    """Point the build server's web app at the show server: SSH tunnel + VN_AUDIO_URL/VN_VIDEO_URL."""
    forwards = ' '.join(f'-L 127.0.0.1:{lp}:127.0.0.1:{rp}' for lp, rp in TUNNEL.values())
    _sudo_write(TUNNEL_UNIT, f"""[Unit]
Description=VibeNation: SSH tunnel to the show server ({ip})
After=network-online.target

[Service]
User=vibe
ExecStart=/usr/bin/ssh -i {SSH_KEY} -N -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new {forwards} root@{ip}
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
""")
    _sudo_write(APP_DROPIN, '[Service]\n' + ''.join(f'Environment={k}=http://127.0.0.1:{lp}\n' for k, (lp, _) in TUNNEL.items()))
    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=True)
    subprocess.run(['sudo', 'systemctl', 'enable', '--now', 'vibenation-showtunnel'], check=True)
    subprocess.run(['sudo', 'systemctl', 'restart', 'vibenation'], check=True)
    print(f'Connected: the app now drives the show server at {ip} (audio :{TUNNEL["VN_AUDIO_URL"][0]}, video :{TUNNEL["VN_VIDEO_URL"][0]}).')
    print(f'Venue laptop: set server = {ip} in sender.ini.')


def cmd_disconnect() -> None:
    """Back to the build server's own engine (the stems)."""
    subprocess.run(['sudo', 'systemctl', 'disable', '--now', 'vibenation-showtunnel'], check=False, capture_output=True)
    subprocess.run(['sudo', 'rm', '-f', TUNNEL_UNIT, APP_DROPIN], check=False)
    subprocess.run(['sudo', 'systemctl', 'daemon-reload'], check=False)
    subprocess.run(['sudo', 'systemctl', 'restart', 'vibenation'], check=False)
    print('Disconnected: the app uses the build server\'s own engine again.')


def cmd_provision(ip: str) -> None:
    # Code (never the build server's .env), a filtered .env, our plugins, then the services.
    rsync = ['rsync', '-az', '--delete', '-e', f'ssh -i {SSH_KEY} -o StrictHostKeyChecking=accept-new',
             '--exclude', '/.env', '--exclude', 'node_modules', '--exclude', '.venv', '--exclude', 'data', '--exclude', 'apps/android',
             '--exclude', 'services/audio/plugins/build', '--exclude', 'services/audio/plugins/.gen']
    subprocess.run([*rsync, ROOT + '/', f'root@{ip}:/opt/vibenation/'], check=True)
    subprocess.run(['ssh', '-i', SSH_KEY, '-o', 'StrictHostKeyChecking=accept-new', f'root@{ip}',
                    'umask 077 && cat > /opt/vibenation/.env'], input=show_env(), text=True, check=True)
    # The tuned mix (faders, EQ, compressors) — data/ is otherwise excluded.
    mix = os.path.join(ROOT, 'data', 'mix_state.json')
    if os.path.exists(mix):
        subprocess.run(['ssh', '-i', SSH_KEY, f'root@{ip}', 'mkdir -p /opt/vibenation/data'], check=True)
        subprocess.run(['rsync', '-az', '-e', f'ssh -i {SSH_KEY}', mix, f'root@{ip}:/opt/vibenation/data/mix_state.json'], check=True)
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
        a = age_min(d)
        print(f'{d["name"]}  {d["region"]["slug"]}  {public_ip(d)}  {d["status"]}  up {a / 60:.1f} h  ≈ ${a / 60 * p:.2f} so far'
              f'  auto-destroy in {max(0, ttl_min(d) - a):.0f} min')


def cmd_reap() -> None:
    """Run by the vibenation-showserver-reaper timer: destroy show servers past their time-to-live."""
    ds = droplets()
    if not ds:
        print('No show server running.')
    for d in ds:
        a, ttl = age_min(d), ttl_min(d)
        if a >= ttl:
            api('DELETE', f'/droplets/{d["id"]}')
            print(f'Destroyed {d["name"]} ({d["region"]["slug"]}): up {a:.0f} min, limit {ttl} min.')
        else:
            print(f'{d["name"]}: up {a:.0f} min of {ttl}.')


def cmd_destroy() -> None:
    ds = droplets()
    if not ds:
        print('Nothing to destroy.')
        return
    cmd_disconnect()
    api('DELETE', f'/droplets?tag_name={TAG}')
    print(f'Destroyed {len(ds)} show server(s).')


if __name__ == '__main__':
    load_env()
    args = sys.argv[1:] or ['plan']
    # --size / --image / --regions override the defaults (e.g. a cheap CPU rehearsal server).
    for flag in ('--size', '--image', '--regions'):
        if flag in args:
            i = args.index(flag)
            val = args[i + 1]
            del args[i:i + 2]
            if flag == '--size':
                SIZE = val
            elif flag == '--image':
                IMAGE = val
            else:
                REGIONS = [r.strip() for r in val.split(',') if r.strip()]
    {'plan': cmd_plan, 'status': cmd_status, 'destroy': cmd_destroy, 'reap': cmd_reap}.get(args[0], lambda: None)()
    if args[0] == 'create':
        retry = int(args[args.index('--retry') + 1]) if '--retry' in args else 0
        ttl = int(args[args.index('--ttl') + 1]) if '--ttl' in args else DEFAULT_TTL_MIN
        cmd_create('--dry-run' in args, retry, ttl)
    elif args[0] == 'provision':
        cmd_provision(args[1])
    elif args[0] == 'connect':
        cmd_connect(args[1])
    elif args[0] == 'disconnect':
        cmd_disconnect()
    elif args[0] not in ('plan', 'status', 'destroy', 'reap'):
        sys.exit(__doc__)
