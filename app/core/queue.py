"""Celery app wired to Redis, with autodiscovery that also scans app/modules/*/tasks.py.

Core owns the Celery app; business-logic modules just drop a `tasks.py` into their
package and their tasks are discovered automatically — no edit to this file needed.
"""

from __future__ import annotations

import os
import pkgutil
from pathlib import Path

from celery import Celery

from app.core.config import settings

_broker = settings.CELERY_BROKER_URL or settings.REDIS_URL
_backend = settings.CELERY_RESULT_BACKEND or settings.REDIS_URL

celery_app = Celery("autougc", broker=_broker, backend=_backend)

# Redis-free local mode: a `filesystem://` broker keeps the async worker
# architecture with NO server to install (used by scripts/run-local-mac.sh when
# Redis isn't available). Messages are exchanged through a folder on disk.
if _broker.startswith("filesystem://"):
    _broker_dir = settings.CELERY_BROKER_DIR or ".broker"
    _queue = os.path.join(_broker_dir, "queue")
    _processed = os.path.join(_broker_dir, "processed")
    os.makedirs(_queue, exist_ok=True)
    os.makedirs(_processed, exist_ok=True)
    celery_app.conf.broker_transport_options = {
        "data_folder_in": _queue,
        "data_folder_out": _queue,
        "data_folder_processed": _processed,
    }

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,                 # redeliver on worker crash (idempotent stages)
    worker_prefetch_multiplier=1,        # fair dispatch for long generation tasks
    task_default_queue="default",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def _discover_module_task_packages() -> list[str]:
    """Return dotted module paths for every app/modules/<name>/tasks.py present.

    Skips the modules package's own dunder entries; includes underscore-prefixed
    example/stub modules so their tasks register too.
    """
    packages: list[str] = []
    modules_dir = Path(__file__).resolve().parent.parent / "modules"
    if not modules_dir.is_dir():
        return packages
    for finder in pkgutil.iter_modules([str(modules_dir)]):
        name = finder.name
        if name.startswith("__"):
            continue
        tasks_file = modules_dir / name / "tasks.py"
        if tasks_file.is_file():
            packages.append(f"app.modules.{name}.tasks")
    return packages


# Autodiscover: core task modules + every module's tasks.py.
_task_packages = ["app.core"] + _discover_module_task_packages()
celery_app.autodiscover_tasks(_task_packages, related_name="tasks")


@celery_app.task(name="core.ping")
def ping() -> str:
    """Trivial liveness task (used by /health and smoke checks)."""
    return "pong"
