# Explicit staged-container recovery — review checkpoint

Recovery can now be specified as a direct task in a new run. It requires an exact
container ID, payload type and pickup location. The container must be physically
staged and marked as requiring recovery after a failed task. Planned, stored,
in-transit and unconfirmed objects are not eligible for this option.

The task reserves its source exclusively and uses the normal robot, route-profile,
clearance and destination-capacity checks. Route rejection rolls claims back.
Pickup and arrival are explicit physical events; the original identity and
container state are retained. Failure before pickup leaves the object staged.
Failure in transit records an unconfirmed arrival and does not restore stock.

Results Investigation now distinguishes outstanding staged recovery from confirmed
recovery arrivals. Completing recovery does not erase the original failed task.

## Review in the editor

1. Open [staged-recovery.json](scenarios/staged-recovery.json) and save a disposable
   project. The original delivery and intentionally blocked return remain present.
2. Open **Tasks**, select **RECOVER**, and choose **Edit**. Verify Container ID is
   `Box-Rotation_initial_empty-000002` and the recovery checkbox is selected.
   Pickup is B, dropoff A, payload Box, release **5 January 2026, 00:00:10**.
   Its route profile is blank; the earlier failed return uses `NoReturn`.
3. Save the task and Tasks window. The task list displays Container ID and Recovery.
   Existing project undo/redo applies through the task save command.
4. Run project checks. The blocked original return is deliberate. Recovery's
   eligibility rule is explained as an informational finding; malformed recovery
   input is blocked before simulation.
5. Simulate and open Results Investigation. Inspect the recovery events and metrics.

| Observation | Independent expectation |
| --- | --- |
| Original delivery | Pickup at 2 seconds; 10 m / 2 m/s plus 2-second unload gives arrival at **9 seconds**. |
| Original return | Fails at **9 seconds** because `NoReturn` excludes the B→A path. The empty is staged at B. |
| Recovery | Released at **10 seconds**. The robot is at B; pickup completes at **12 seconds**, then 5-second travel and 2-second unload give arrival at **19 seconds**. |
| Outcomes | **2 completed, 1 failed**. The original return remains failed. |
| Physical state | **2 issued, 2 stored, 0 staged, 0 unconfirmed**. The original empty is stored at A and the full container remains in B's bay. |
| Investigation | **0 outstanding recoveries, 1 confirmed recovery arrival**, with linked evidence; two paired physical transfers. |

To model another recovery, take its exact identity/location from the corresponding
run evidence and add an explicit recovery task to a new run of the matching
project inputs. Changing demand or seed ordering can change generated IDs. An
unmatched ID waits or times out; it is never replaced by another object silently.
An early recovery release waits until a failure makes the container eligible.

## Editor correction and evidence

**D032:** the form emitted `manual_task` and `manual_single_payload_only`, but the
task constructor did not accept them. They are now accepted. `manual_task` activates
the existing single-payload robot policy; `manual_single_payload_only` is retained
editor metadata, not a separate robot-selection switch. Editing also preserves options not shown in the form,
including routing restrictions and return settings. An explicit edited release
date replaces the old relative release value. Recovery and container ID are now
visible and editable; an empty recovery ID is rejected.

Seventeen tests cover exclusive claims, duplicate batches, route/storage rejection,
rollback, estimates, failures before/after pickup, wrong location/state, early release,
raw/editor-normalised projects, malformed inputs, investigation and editor saves.
Baseline evidence: `baseline/staged-recovery-before.txt` and
`baseline/manual-task-flags-before.txt`, against commit `fd6a8dd`.
The task dialog was rendered offscreen with the installed Segoe UI font and checked
for readable labels, values and buttons; `latest/recovery-task-form.png` records it.

The full pack passes **506/506 tests**, with zero broken evidence links. The saved
reference preserves frozen inputs and reconciles its two completions and one
failure against events; see `latest/staged-recovery-reference/summary.json`.
Six-hour LTN remains **203 completed, zero failed and zero pending**, retaining
detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
The final run took 14.521 seconds; see `latest/ltn-staged-recovery-final/summary.json`.

Recovery does not resume or edit a frozen historical run. Physical staging areas,
swept geometry, staging capacity and recovery from an unconfirmed location remain
unsupported. This direct recovery option does not combine with staff handoffs or
further automatic returns. The full [roadmap](ROADMAP.md) remains open. The earlier
unexplained preview interruption remains in `baseline/multi-stop-verification-observation.txt`.
Automated warning acknowledgement does not constitute human acceptance.
