"""Tiny background job runner with progress logs (one worker thread per job)."""

from __future__ import annotations

import threading
import time
import traceback
import uuid

_JOBS: dict = {}
_LOCK = threading.Lock()


class Job:
    def __init__(self, kind: str, project_id: str):
        self.id = uuid.uuid4().hex[:10]
        self.kind = kind
        self.project_id = project_id
        self.status = "running"   # running | done | error
        self.progress = 0.0       # 0..1
        self.log: list = []
        self.error = ""
        self.result = None
        self.started = time.time()

    def say(self, msg: str) -> None:
        self.log.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        self.log = self.log[-200:]

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "project_id": self.project_id, "status": self.status,
                "progress": round(self.progress, 3), "log": self.log[-40:], "error": self.error,
                "result": self.result, "elapsed": round(time.time() - self.started)}


def start(kind: str, project_id: str, fn, *args) -> Job:
    job = Job(kind, project_id)
    with _LOCK:
        _JOBS[job.id] = job

    def run():
        try:
            job.result = fn(job, *args)
            job.status = "done"
            job.progress = 1.0
        except Exception as e:  # surfaced to the UI
            job.status = "error"
            job.error = str(e) or e.__class__.__name__
            job.say("ERROR: " + job.error)
            job.say(traceback.format_exc(limit=3).splitlines()[-1])

    threading.Thread(target=run, daemon=True).start()
    return job


def get(job_id: str):
    return _JOBS.get(job_id)


def for_project(project_id: str) -> list:
    return [j.to_dict() for j in _JOBS.values() if j.project_id == project_id]
