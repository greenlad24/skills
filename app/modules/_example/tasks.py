"""Example module Celery tasks — autodiscovered by app.core.queue.

Register tasks with a namespaced `name=` so they don't collide across modules.
"""

from __future__ import annotations

from app.core.queue import celery_app


@celery_app.task(name="_example.ping")
def example_ping() -> str:
    """A no-op task proving module task autodiscovery works."""
    return "example-pong"
