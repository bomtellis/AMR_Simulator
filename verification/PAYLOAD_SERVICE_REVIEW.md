# Payload service and conservation checkpoint — 2 October 2026

## D008: cause and repair

A seeded waste container is emptied at the waste destination and returned as the
same bin. At a finite exchange store this service bypasses storage occupancy so
the store's stock of empty exchange bins is unaffected. That branch previously
also skipped the arrival log, creating two exits before the next stored entry.

The simulator now records **payload_service_arrival** at the calculated drop-off
completion time. It is a physical journey endpoint, explicitly **not stored in
inventory**, with no inventory bay assigned. Both single-task and multi-stop
completion paths emit it. It is retained in full and playback exports.

Results investigation pairs that event with the preceding exit and exposes a
separate **Payload service arrivals outside storage** metric. New run sidecars
declare the event capability. An older log without that capability shows unknown
coverage instead of claiming zero service arrivals. Old missing events are never
invented or repaired from current project data.

## Review the small reference project

1. Open a copy of `scenarios/payload-service-return.json` in the editor. Save it
   as an `.amrproj` project and run it through **Project runs**.
   The missing charger-equipped-bay warning is intentional for this short
   routing reference with no charging demand; acknowledge it for this example.
2. The project starts with one bin at A and one independent empty bin in B's
   finite bay. One automatic collection is released at 60 s.
3. Expect the collection to finish at 69 s and the return at 78 s: each journey
   takes 2 s pickup + 10 m / 2 m/s travel + 2 s drop-off = **9 s**.
4. In Results investigation, expect **two completed tasks, two physical transfers,
   one service arrival, zero tracking conflicts and zero unpaired exits**.
5. Inspect the bin's history: depart A at 62 s; service arrival at B at 69 s;
   depart B at 71 s; stored entry at A at 78 s. The same physical identifier must
   be used throughout. B's original exchange bin remains unchanged.

The independent tests also cover a one-minute handling delay, ordinary storage
arrivals, two-bin multi-stop delivery and return, exported event identifiers and
unknown versus zero service activity in old/new evidence.

The review also reproduced and fixed **D012**: editor open/save and the task
generation dialog dropped `update_interval_sec`. The example explicitly uses
60 s; reverting to the engine's 900 s default previously generated no work in
its ten-minute window. That setting is now retained, and a test runs the saved
example after editor normalisation as well as through the engine directly.

## LTN comparison

**332 / 332 tests passed**, with zero broken evidence links. This includes ten
payload-service acceptance cases and three generation-setting round-trip cases.
The service metric and its contributing event were also rendered and inspected
in the Results investigation workspace. The user's existing LTN edit was
preserved; no simulation outputs were added to the project archive.

The six-hour LTN demand window still produces **203 completed, zero failed and
zero pending tasks**. Its detailed outcome fingerprint remains:

`593945bef454f5d602c82f0f15180cbc26285d3711d93102d483635da36faab5`

Payload reconciliation changes from **189 observed paired transfers and one
tracking conflict** to **190 paired transfers, zero conflicts and zero unpaired
exits**. This corrects missing movement evidence; it does not change task routes,
timings, storage capacity or create another physical bin.

The original conflicting log remains in `latest/ltn-project-run-ordered/`.
Fresh bound results are in `latest/ltn-payload-service-verified/`. Reproduce with:

```powershell
.venv/Scripts/python.exe -m verification.run --output verification/latest
.venv/Scripts/python.exe -m verification.project_runs --config ltn.json --minutes 360 --output verification/latest/ltn-payload-service-verified
```

## Scope and remaining work

These cases verify service-cycle identity and stored-stock conservation. They do
not establish system-wide conservation for every mixed workflow, mass removal,
inventory exchange or failure path. The existing reference-scope labels remain;
the first release's full verification gate is still open. See `ROADMAP.md` for
the remaining original requirements.
