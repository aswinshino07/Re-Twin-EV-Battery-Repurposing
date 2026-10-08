# output/

All files here are included except `simulated_eis.csv` (the full 50-point-
per-timestamp EIS sweep, ~57MB) — it's left out to keep this package small,
but regenerates in seconds:

    python src/main.py

`realtime_fused_log.csv` is a sample from a real-time run
(`src/realtime_pipeline.py`); it's overwritten fresh every time you run
that script.
