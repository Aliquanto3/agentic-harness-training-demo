"""The `guardrails` brick (CAP-5, story 4): toxicity and personal-data filters, in and out.

An optional dependency (`guardrails`, like `compression`): WaveStack starts without it, and
each guardrail reports `not_installed` until its libraries are present. Models are loaded on
demand and can be unloaded (`GuardrailsManager.unload_idle`); the whole brick stays at 1.5 GB
of RSS or less, measured in `docs/guardrails-ram.md`.
"""
