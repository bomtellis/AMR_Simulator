# Checkpoint 2C — generation precedence and return import parity

Review date: 3 October 2026. Baseline: `b496a4b`.
Follow-up: [slice 2D](STAFF_CHOICE_REVIEW.md) distinguishes omitted staff choice
from explicit false, preserving omission across import rather than filling false.
It corrects the legacy-fallback limitation recorded in this historical review.

## Fixed import drift

The editor previously filled an imported Stores rule's absent staff settings from
the new-project template. This added `requires_staff=true` and 15 minutes of staff
handling. In the reference below a return that started at 00:02:09 through direct
simulation started at 09:15:00 after editor import because staff/shift handling
was introduced by normalisation.

Imported category rules now retain generated-task defaults for these two missing
fields: `requires_staff=false` and `staff_handling_minutes=0`. Explicit category,
group and department settings remain effective. New projects retain their
explicit staff-enabled Stores template and 15-minute template handling duration.
The existing legacy Stores staff fallback in the simulator remains; this change
does not claim that setting `requires_staff=false` disables all Stores handling.

## Reference calculations

Open [generation-return-import.json](scenarios/generation-return-import.json) as
a separate project. The outbound task is released at 60 seconds. Two 2-second
handling actions and a 10 m Clean route at 2 m/s give a 9-second delivery, arriving
at 69 seconds (00:01:09). A one-minute return delay gives return release/start at
129 seconds (00:02:09), measured from arrival rather than outbound release.

| Return rule field | Effective return path | Duration | Completion time |
| --- | --- | --- | --- |
| Omitted | Inherits the outbound Clean profile: 10 m | 9 s | 00:02:18 |
| Explicit blank | No profile restriction: 1 m shortcut | 4.5 s | 00:02:13.500 |
| `dirty` | Dirty profile: 14 m | 11 s | 00:02:20 |

The saved file uses omission. The tests exercise all three choices both directly
and after editor normalisation. The fixture passes raw Project checks without
blocking findings. Returns remain conditional on delivery and resources; they
are not counted as fixed demand-preview records.

## Expanded contracts and tests

The full evidence build passed **911 tests in 125.440 seconds**, with **zero
broken evidence links** and unchanged source hashes during testing. The LTN
configuration after editor normalisation is identical to the preceding commit;
the source file checksum remains unchanged.

Twenty-two generation fields now have source/default/precedence/validation/limit
and test traceability. Together with the earlier routing audit, 38 option paths
have individual reviewed contracts. The generation entries remain partial because
all modes, input types, staff behaviours and waste/return interactions are not
yet covered independently.
The discovery inventory now contains 530 paths: 38 individually reviewed and
492 still awaiting that level of review. These are option paths, not counts of
missing features, and discovery is not yet an exhaustive configuration schema.

The acceptance cases cover whole-list replacement by an empty group schedule,
group suppression of standalone department/category work, enabled department
overrides of disabled category defaults, override priorities/return settings,
profile omission versus explicit blank, completion-relative delay, missing return
payloads, imported staff defaults, new-project templates and group staff overrides.
Existing weekday/fortnight/horizon/calendar tests remain linked to the audited
schedule contracts.

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_generation_contracts tests.test_generation_reference tests.test_generation_provenance tests.test_verification_evidence -q
.\.venv\Scripts\python.exe -m verification.run --output verification/latest
```

## Remaining work

- Audit other values filled from editor templates on import. This fix addresses
  the two fields proven to change this reference; it does not establish complete
  import parity for all omitted generation settings.
- Resolve and verify the explicit-false versus legacy Stores staff requirement.
  Other generation boolean conversions still need input validation review.
- Continue seeded waste returns, runtime-dependent modes, resource contention and
  complete demand/event/report reconciliation.
- Preserve current waste threshold and department-policy precedence until the
  operating policy is explicitly decided; the earlier provenance review records
  those exceptions.
- Keep geometric traffic, the selected graph-focused UI and tutorial in their
  planned order after core completion.

Local evidence is retained in `latest/generation-contracts-pack-build.txt`, the
main verification pack and `latest/generation-import-ltn.json`.
