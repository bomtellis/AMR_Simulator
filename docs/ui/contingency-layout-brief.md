# Contingency setup correction

Scope: existing PySide6 Windows dialog, project task generator and QProcess study
runner. Retain the workbench styling and non-modal study workflow. Correct the
unbounded validation label and generic outer scrolling wrapper; forms scroll
independently and the status/footer remain outside the form.

Defaults now resolve the existing TaskGenerationManager with prepare_runtime=False;
no task generation or simulation runs during setup. Two payloads per person is
the user's approved initial carrying count. Payload dimensions/weights, locations,
staff speed/handling and shift lengths/days are reused. The envelope, shared base,
load/unload times and break/start rules remain visible, editable planning assumptions.
Completed saved settings retain their values. Old blank profiles are filled in the
dialog only; ordinary Save settings/project Save persist changes through the
existing undo mechanism. Saved study snapshots are not migrated.

Controls, validation, run/resume, cancellation, staleness, CSV and PDF operations
retain the same entry points. The simulation and demand calculation are unchanged.
Tests cover prefill, user edits, old settings, background execution, and long
validation at a 1000×700 logical-pixel window with 14pt text. Visual evidence uses
the current LTN project in an offscreen Qt window at normal and enlarged text.
Live mixed-monitor transitions and assistive technology are not covered.

Rollback: restore the explicitly backed-up application files; no user project
or synced sources are edited during installation.
