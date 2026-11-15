# Copy, paste and delete configured schedules

Open **Task generation → Department actions → Edit configured group…**.

- **Copy** copies the selected group's settings and departments to the local clipboard.
- **Paste…** creates a new group and opens the existing schedule editor. Adjust its times, departments or other settings, then save that editor. Each paste has a fresh identity and independent settings.
- **Edit…** or double-click changes the selected existing group.
- **Delete** removes the selected group from the draft after confirmation.
- **Save** applies the draft to Task generation. **Cancel** discards additions, edits and deletions.

Finish by saving the Task generation dialog and the project. The existing application Undo/Redo handles the completed change. Schedule times are shown in each group row to distinguish runs quickly.

With the group list focused, **Ctrl+C**, **Ctrl+V** and **Delete** perform the same actions. Text fields in the schedule editor retain their normal editing keys. Clipboard groups can be pasted into another dialog for the same category; other clipboard content and groups from a different category are not accepted.

Deleting a group keeps other configured runs and independent department overrides. Compatibility copies of a deleted group are removed, including department-specific location values. Merely saving or changing the selected department/category leaves separate schedules intact. Editing an individual department's settings retains the existing behavior of detaching that department from groups whose settings differ.

The implementation uses deep-copied dialog drafts, the existing schedule editor, project persistence and Undo/Redo. No simulator schema or scheduling algorithm changes are required. Verification covers clipboard actions and keyboard shortcuts, nested copies, cancellation, deletion cleanup, two distinct generated schedules, Save/reopen, scope switching and Undo/Redo. Standard-scale dialog previews are inspected; broader display scaling and assistive-technology checks are outside this bounded change.
