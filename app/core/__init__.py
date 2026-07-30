"""Core foundation: config, DB, canonical models/schemas, state machine, adapters, queue.

This package is the CONTRACT every business-logic module builds against.
Modules import from `app.core.*`; they must never edit anything in here.
"""
