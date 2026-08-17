"""In-app onboarding: first-run setup wizard backend (/api/setup/*).

Writes provider keys to `.env`, live-tests each provider, and flips the app from
DRY_RUN into the cheap real stack (LTX-2.5 on Modal, Google Thai TTS, TikTok
Content Posting) — so a new operator goes from clone to ready without hand-editing
config files.
"""
