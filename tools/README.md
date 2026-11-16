# AMR Simulator source graph and profiling

Run these commands from the checkout using the application's Python environment.

```powershell
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py build
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py find "route planning"
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py find "event recording"
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py find "lift exports"
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py refs "amr_third_party_lift.export_lift_trips_xlsx"
.\.venv\Scripts\python.exe tools/amr_knowledge_graph.py check
```

Use `--json` before `find` or `refs` for structured results. Paths and line numbers
are relative to the indexed checkout. The graph is stored in
`.cache/amr-knowledge-graph/graph.json`. `find` and `refs` compare source and tool
hashes and regenerate a stale graph. `check` reports missing or stale caches,
parse failures, and outdated source annotations. Re-run `build` after changing
the Node runtime or making Acorn available.

The graph covers root application modules and executable sources in
`visualiser`, `report`, `installer`, and `native`. It indexes Python with the
standard AST and JavaScript with Acorn via Node. The JavaScript extractor
can use an installed Acorn package or the parser bundled with Node. The tool
reports incomplete JavaScript coverage if it cannot use either parser.

Calls are inferred from source. Dynamic dispatch, external libraries and
callbacks that cannot be resolved produce counts and source examples. Verify
call sites in source before moving or deleting a function. Add links for
cross-process and storage boundaries in `amr_knowledge_links.json`. Each
link must match one source line within the originating definition.

Run the fixed workloads into a new scratch directory:

```powershell
.\.venv\Scripts\python.exe tools/profile_amr_workflows.py .cache/amr-profile
```

The summary includes per-workflow wall time, process CPU time, call counts,
observed output opens and publications, and event blocks written by the
instrumented Python process. Child and background worker internals are
outside the CPU profile. Normalized fingerprints cover decoded events,
playback, investigation, and exported contents. Repeat runs on the same
machine before drawing timing conclusions.

## Optional C++ corridor timing on Windows x64

Build the extension for the application's Python environment using Zig. The
script checks that the extension loads before installing it in the checkout.

```powershell
.\tools\build_corridor_native.ps1 -Compiler 'C:\Tools\zig\zig.exe'
```

Compact Simple timed routes use the extension when it is available and the route
has no scenario or people timing. Python provides the same timing when the
extension is absent or fails to load. Set `AMR_DISABLE_NATIVE_CORRIDOR=1` before
launching a fresh process to force the Python path for comparisons. Verified runs
that use the extension record its SHA-256 in the run evidence sidecar.
