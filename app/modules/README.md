# Module convention (the plug-in contract)

Business logic lives in **modules**. Core (`app/core/`, `app/main.py`, docker, tooling)
is owned by the foundation and is a stable contract you build against. **A module never
edits `app/core/` or `app/main.py`** — it plugs in through the seams below.

A module is a Python package at `app/modules/<name>/`. The foundation discovers and
wires it automatically:

| File | Purpose | Discovered by |
|---|---|---|
| `router.py` | Exposes `router: APIRouter`. Its routes are mounted on the app at startup. | `app/main.py` → `load_modules()` |
| `tasks.py` | Celery tasks. Registered via Celery autodiscovery. | `app/core/queue.py` |
| `requirements.txt` | *Optional* pip fragment for deps this module needs beyond core. | `Dockerfile` (concatenated + installed) |
| `__init__.py` | Marks the package. | Python |

Nothing else is required. A module may ship only a `router.py`, only a `tasks.py`, or both.

## Rules

1. **Import only from `app.core.*`** (config, db, models, schemas, state_machine,
   adapters, queue). Do not import another module's internals.
2. **Never edit `app/core/` or `app/main.py`.** If you need a new core capability,
   raise it with the foundation owner and update `docs/CONTRACTS.md` — don't fork core.
3. **All external calls go through the adapter registry** (`app.core.adapters.registry`),
   so `DRY_RUN=true` works with zero spend. Never call a vendor SDK directly from a module;
   register a real adapter with `registry.register_real(...)` instead.
4. **Drive job state only through `app.core.state_machine.transition()`** — never assign
   `job.state` directly. Illegal transitions must raise.
5. **Populate the cost ledger** for every billable adapter call (write a `CostLedgerEntry`
   in the same transaction that bumps `VideoJob.cost_accrued_usd`), and respect the budget
   guard before spending.
6. **Give your router a unique `prefix`** (e.g. `/api/research`) and `tags` so the mounted
   API stays collision-free. Register Celery tasks with a namespaced `name=`
   (e.g. `research.run`) matching what the core enqueues.

## Naming: the task names core enqueues

The core jobs router (`app/main.py`) enqueues these task names as the pipeline advances.
Own the matching one in your module's `tasks.py`:

| Stage module | Expected Celery task `name=` |
|---|---|
| research | `research.run` |
| generation | `generation.run` |
| editing | `editing.run` |
| posting | `posting.run` |

(Additional intra-module tasks are free-form; just keep them namespaced.)

## Minimal example

See `app/modules/_example/` for a working stub that:
- exposes `router` at `/api/_example` with a `GET /ping`,
- defines a namespaced Celery task `_example.ping`,
- declares an (empty) `requirements.txt` fragment.

Copy it as the starting point for a real module.
