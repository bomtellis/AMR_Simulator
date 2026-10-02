# Individual delivery and charging rollback — review checkpoint

Rejected individual delivery, idle-return and charging-route plans now restore
the resources they touched. The existing multi-stop transaction also preserves
the full robot state and the boundary of appended charging records.

## Defects reproduced

**D020 — individual routes:** an unreachable wash destination after delivery could
leave corridor, location and destination-bay reservations behind. A late exception
could also retain lift wear, battery consumption or an in-place charge record.
Rollback now restores these, including task orientation, wash flag and idle-return
destination settings. Diagnostic pending reasons remain available.

**D021 — charging routes:** both charging schedulers freed the current parking bay
before knowing whether a charging route existed. A rejected route could reserve
the target bay, and a failed lift commit could change lift state. Departure release
is now inside the route transaction. A successful plan keeps its destination claim;
a rejected plan restores the departure occupancy and earlier claims. A charging
estimate no longer changes the robot's target charger.

The original six tests failed in eight cases before the fix. Their output is in
`baseline/single-charge-atomicity-before-fix.txt`.

## Acceptance evidence

Ten tests in `tests/test_single_charge_atomicity.py` cover:

- Unreachable wash routing after a delivery, restoring reservations and task flags.
- Late single-route failure after energy consumption and pre-route charging,
  both on one floor and through a lift.
- Both charging schedulers retaining their occupied departure bay on rejection.
- Target-bay rejection, a lift exception after wear, and stale bay-marker cleanup.
- Charging estimates retaining the original robot target and bay claims.
- Successful single and charging plans retaining their records and reservations.
- Idle-return rejection restoring its original destination and robot bay state.

The independent charging reference starts empty with a 10 kWh battery and a 2 kW
charger: **10 / 2 × 3600 = 18000 seconds** to charge, before travel. It verifies
the retained charge interval and total charging time; it does not validate all
energy or charger-queue behaviour.

The full local pack passes **407/407 tests**, with zero broken feature-to-test
links. Six-hour LTN remains **203 completed, zero failed and zero pending**, and
retains detailed outcome hash
`21cd7e6d1fe83f255ab425307acd0fd1f830f4aa155412eba1767b3996fcf0f6`.
The saved-project run preserves its input and reconciles summary/event outcomes;
it took about 14 seconds on this machine. See
`latest/ltn-single-charge-rollback/summary.json`.

## Review and remaining work

Review the failure evidence alongside `latest/index.html`. The three projects in
[the storage guide](STORAGE_RESERVATIONS_REVIEW.md) remain the practical capacity
examples. No new UI controls or project-format changes are introduced here.

The guarantee covers serial route planning. Exceptions after a plan succeeds,
while assignment events are being published, are outside this transaction. Bay
cleanup during other estimation paths still needs a wider concurrency audit.
The subsequent [charging travel checkpoint](CHARGING_TRAVEL_REVIEW.md) verifies
charger travel reservations and motor/lift energy. The [exchange checkpoint](EXCHANGE_CLAIMS_REVIEW.md)
verifies distinct empty-bin claims; staging/recovery remains open. Geometric traffic,
the wider option audit and the other [roadmap](ROADMAP.md) gates remain open.

The earlier unexplained background-preview process interruption is still recorded
in `baseline/multi-stop-verification-observation.txt`; no repair is claimed here.
Automated regression warning acknowledgement is not human acceptance.
