# Excel lift trip export

In a completed run's Report view, choose **Export third-party lifts…**, then
**All lifts and trips — Excel table (.xlsx)**. Choose the Excel filename. The
export runs in the existing background worker. **Open lift Excel table** opens
the finished file. Cancelling the filename dialog starts no work.

The **Lift trips** worksheet contains a native Excel table named `LiftTrips`,
with filters and frozen headers and identifying columns. It contains one row
per recorded lift movement across all configured lifts, including empty lift
repositioning. Rows are ordered by the unrounded third-party start time and
then original event order. No empty trips are invented for unused lifts.
The **Lifts** table lists every configured lift and its trip count, including
zero-trip lifts, plus the saved run location and event checksum.

All 22 existing detailed movement columns are retained: movement ID, lift ID,
movement type, AMR, task IDs, start and finish time, origin and destination
level, duration, origin and destination location, distance, AMR onboard,
direction, endpoint source, payload and AMR weights, service category,
service categories, activity type and FM cohort IDs. Start and finish times
are sortable Excel dates when dated evidence exists, otherwise numeric
simulation seconds. Missing historical duration or weight evidence is blank.

The seven existing third-party fields follow these details, in columns W:AC:
**Start Seconds**, **Origin Number**, **Destination Number**, **Load weight**,
**% loading factor**, **Transfer times**, **Car not in service**. The final
column AD, **concatenated**, is a formula on every trip row, for example:

```excel
=TEXT(W6,"0")&","&TEXT(X6,"0")&","&TEXT(Y6,"0")&","&TEXT(Z6,"0")&","&TEXT(AA6,"0")&","&AB6&","&TEXT(AC6,"0")
```

Changing one of the third-party input fields updates the string. Numeric
fields stay numeric. `Transfer times` is text containing the entry and exit
seconds separated by a comma, preserving decimal points and up to three
decimal places. The concatenation is also stored with its calculated result
for readers that initially show cached Excel values.

The existing import rules are preserved: whole-second entry start rounded
half upward, floor number + 1, fixed load `1500`, loading factor `60`, car not
in service `2`. Empty reposition trips use their movement start and `0,0`
transfer times. Logged physical weights remain separate from these fixed
third-party import values.

The single-lift and separate all-lift CSV options retain their prior schema,
defaults, optional reposition inclusion and command-line interface. The Excel
option always includes reposition trips. Its command-line equivalent is:

```powershell
.\.venv\Scripts\python.exe amr_app.py "path\to\completed-run" --third-party-lift-xlsx "path\to\lift-trips.xlsx"
```

The same option is supported by `amr_third_party_lift.py` and the report CLI.
It cannot be combined with CSV output options or `--lift-id`. It does not
rerun the simulation or generate a PDF. The exporter supports the existing
verified saved-run directory, CSV and compact SQLite input boundaries. It
uses frozen inputs and checks the event and evidence hashes before publishing
the completed workbook. Failures retain the prior completed output.

## Implementation and verification scope

This is a bounded addition to the existing PySide6 report dialog and CLI,
with the existing QProcess job lifecycle and report styling. It changes no
simulation, configuration, persistence, undo or workspace layout behavior.
The detailed movement report and third-party conversion remain authoritative.
Excel generation uses the same Node.js / `@oai/artifact-tool` runtime as
department workbooks, with the same `AMR_REPORT_NODE` and
`AMR_REPORT_NODE_MODULES` overrides. The writer is `amr_lift_trip_workbook.mjs`.
One table supports up to 1,048,570 trips after context and header rows.

Focused tests exercise all three CLIs, the background Excel dialog, opening
and cancelling, source/edit isolation, existing CSV compatibility, saved
table objects, numeric cells, formula text and cached results on every row,
fractional transfer times, negative floors, unused lifts, empty movement
sets, writer failures and evidence changes. A real completed LTN run is
exported and the two sheets rendered for visual review. Changing and restoring
a third-party field during verification exercises recalculation.

Environment: Windows, Python 3.13 and the installed PySide6 environment.
Dialog controls remain native, with an explicit accessible export label.
Automated dialog checks cover format selection and enabled states. Broader
screen-reader, mixed-display and high-contrast certification is not claimed.
Native Excel application recalculation is not automated in this verification.

Installation checks the current file hashes and stages rollback copies before
replacing this bounded set of source files. Restart the source application
after installation. Existing packaged executables require rebuilding, with
the workbook writer and spreadsheet runtime included by the packaging process.
