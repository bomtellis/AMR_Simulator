# AMR Simulator

Before implementing a capability, query the source graph for code you can reuse.
From this checkout, run `.venv\Scripts\python.exe tools/amr_knowledge_graph.py find "capability or name"`.
Use `refs "<qualified ID>"` with the same command to follow callers, callbacks and data dependencies.
`find` and `refs` rebuild a stale cache automatically. Confirm the result in source and use
`rg` for unresolved or dynamic references. See [source graph and profiling](tools/README.md)
for commands and coverage.
