"""Context compression behind a port (story 20, AD-22).

The `Compressor` port (`port.py`) is what the session calls at the `transform_context` step;
Headroom (`headroom_adapter.py`) is its adapter, an optional dependency (the `compression`
extra). `env.py`, stdlib only, sets Headroom's offline variables before any third-party import.
This package's `__init__` imports nothing: `cli` imports `env` before the rest.
"""
