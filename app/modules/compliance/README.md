# Compliance & Legal Guardrails module (`app/modules/compliance`)

Implements spec **§06** — the fail-safe compliance engine that stands between script
generation and publishing. It is a *deterministic gate with a probabilistic (LLM) assist*:
the LLM can only ever raise flags, never grant a pass. Any ambiguity, error, timeout, or
missing record → **BLOCK** (fail closed). Every decision is written to an append-only,
hash-chained audit record.

> ## ⚠️ NOT LEGAL ADVICE
> This module and its rule tables translate researched regulatory facts (TikTok Shop
> policy, US FTC Testimonials/Reviews Rule & Endorsement Guides, EU AI Act Art. 50, Thai
> OCPB, Thai FDA, Thai PDPA, ELVIS Act, NO FAKES Act) into software controls for
> engineering. **It is not legal advice and creates no attorney–client relationship.**
> Rules, dollar amounts, and effective dates change and vary by fact pattern. **Qualified
> US/FTC, EU, and Thai counsel MUST review the claim taxonomy, disclosure copy, consent
> template, and jurisdiction table (`ruleset.py` / `data/ruleset_2026_07.yaml`) before
> production launch and on a recurring cadence.** Where counsel and this code disagree,
> counsel wins — encode their determination in the versioned rule tables and bump
> `RULESET_VERSION`.

## Public API (imported by other modules — stable contract)

`app/modules/compliance/service.py`:

```python
classify_claims(script: dict) -> dict
# -> {"allowed": bool, "flags": [{claim, type, action("BLOCK"|"ROUTE"|"ALLOW"), reason, ...}],
#     "script_hash", "ruleset_version", "classifier_prompt_version"}
# Fail-CLOSED: experiential -> ROUTE (operator verification);
# efficacy/health/comparative/guarantee -> BLOCK unless resolved via the merchant
# approved-claims library. NEVER auto-ALLOWs those classes.

run_prepost_checklist(job_id) -> dict
# -> {"passed": bool, "checks": [{id, name, passed, detail}]}
# passed is the AND of CHK-1..11. No human override of a red check.
```

## Layout

| File | §06 area | What it does |
|---|---|---|
| `service.py` | — | The two contract functions above + DB evidence gathering. |
| `classifier.py` | 6B | Hybrid claim classifier: deterministic Thai+English lexicon → LLM judge (`registry.get_llm_provider()`, temp-0 via prompt) → most-restrictive reconciliation. |
| `consent.py` | 6C.1 | `consent_valid()` / `consent_validity()` predicate (PDPA/ELVIS/NO-FAKES). |
| `records.py` | 6C.3 | Immutable, hash-chained `ComplianceRecord` (`ComplianceLedger`) + `ClaimDecision` log; persistence bridge onto the core model. |
| `verifiers.py` | 6A | TikTok Shop form/disclosure/category verifiers; media-analysis checks behind the `MediaAnalyzer` interface with a DRY_RUN passing stub. |
| `checklist.py` | 6D | Pure `evaluate_checklist(evidence)` implementing CHK-1..11. |
| `ruleset.py` + `data/` | 6E, 6.0 | Versioned rule tables: lexicon, category rules, disclosure copy, jurisdiction→control map. |
| `router.py` | — | `/api/compliance` endpoints (classify, checklist, ruleset, consent validity, revoke/takedown). |
| `tasks.py` | — | Celery tasks `compliance.classify`, `compliance.checklist`. |

## Design invariants (§6.0)

1. **Fail safe / fail closed** — no default/allow path to a postable state.
2. **Deterministic gate, probabilistic assist** — the LLM only raises flags/routing.
3. **Everything logged, nothing mutable** — append-only hash-chained events.
4. **Human accountability on experiential/efficacy claims** — only the identity-verified
   operator can affirm a first-person claim; efficacy/health need a merchant
   approved-claims entry + logged substantiation ref.
5. **Config as versioned data** — every decision pins `ruleset_version` +
   `classifier_prompt_version` + `script_hash` for reproducibility.

## Notes / known integration seams

- The core `VideoJob` model has no `category` column; category & cloned-voice usage are
  carried on the ComplianceRecord envelope and passed to `consent_valid()` / verifiers via
  a lightweight job-context object.
- `LLMProvider.complete()` has no temperature parameter, so temperature-0 determinism is
  requested in the classifier system prompt and is the real adapter's contract.
- Media-analysis verifiers (real-env, motion, face+product, ≥3s dynamic, OCR of the baked
  label) require a registered `MediaAnalyzer`; in `DRY_RUN` a deterministic stub passes,
  and in real mode with none registered they fail closed.

## Tests

`tests/` (release-blocking per §6F). Run with `pytest app/modules/compliance/tests`.
Covers: the classifier fails closed on experiential/health claims and never auto-allows
risky classes; the checklist blocks when any check is red; consent validity edge cases;
and hash-chain tamper detection.
