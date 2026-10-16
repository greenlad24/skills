"""Tiny client for mod-host's socket protocol (one command, one "resp" reply).

Commands: add <uri> <id> | remove <id> | connect <a> <b> | disconnect <a> <b> |
param_set <id> <symbol> <value> | monitor_output <id> <symbol> | bypass <id> 0|1.
JACK ports of an instance are named effect_<id>:<symbol>.
"""

from __future__ import annotations

import socket
import threading


class ModHostError(RuntimeError):
    pass


class ModHost:
    def __init__(self, host: str = '127.0.0.1', port: int = 5555, feedback_port: int = 5556):
        self.addr = (host, port)
        self.fb_addr = (host, feedback_port)
        self.sock: socket.socket | None = None
        self.lock = threading.Lock()

    def connect(self) -> None:
        self.sock = socket.create_connection(self.addr, timeout=10)

    def cmd(self, text: str) -> str:
        with self.lock:
            if self.sock is None:
                self.connect()
            assert self.sock is not None
            self.sock.sendall(text.encode() + b'\0')
            buf = b''
            while not buf.endswith(b'\0'):
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ModHostError('mod-host closed the connection')
                buf += chunk
            resp = buf.rstrip(b'\0').decode()
        parts = resp.split()
        if len(parts) < 2 or parts[0] != 'resp' or int(parts[1]) < 0:
            raise ModHostError(f'{text!r} -> {resp!r}')
        return resp

    def add(self, uri: str, inst: int) -> None:
        self.cmd(f'add {uri} {inst}')

    def remove(self, inst: int) -> None:
        try:
            self.cmd(f'remove {inst}')
        except ModHostError:
            pass

    def param(self, inst: int, symbol: str, value: float) -> None:
        self.cmd(f'param_set {inst} {symbol} {value:.6g}')

    def connect_ports(self, a: str, b: str) -> None:
        self.cmd(f'connect {a} {b}')

    def monitor(self, inst: int, symbol: str) -> None:
        self.cmd(f'monitor_output {inst} {symbol}')

    def feedback(self, on_message) -> threading.Thread:
        """Read "output_set <id> <symbol> <value>" messages in a background thread."""

        def run():
            s = socket.create_connection(self.fb_addr)
            buf = b''
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    return
                buf += chunk
                *msgs, buf = buf.split(b'\0')
                for m in msgs:
                    on_message(m.decode(errors='replace'))

        t = threading.Thread(target=run, name='modhost-feedback', daemon=True)
        t.start()
        return t
