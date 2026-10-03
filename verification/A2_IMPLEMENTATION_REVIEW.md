# A2 visual workbench implementation

The approved graph-focused concept now drives the production PySide6 window.
This follows the earlier CAD interaction checkpoint with the actual visual shell,
map presentation and direct Door placement. The user requested that subagents
stop; final integration and verification were completed by the primary agent.

## Implemented design

- The upper workflow bar opens Project, Layout, Configuration, Check, Simulate,
  Review and Report. Save, Undo, Redo, Help, theme and text size use real actions.
  File/Edit/View/Help menus retain access on smaller screens.
- Illustrated Select, Corridor, Node, Location and Door commands sit over the
  graph, alongside Fit, independent Snap/Grid toggles, More tools and Focus canvas.
- The compact project tree remains beside the drawing. Properties opens from a
  narrow right tab; selection alone does not expand it. Hidden drafts survive.
- A slim checks strip distinguishes unchecked, current and stale inputs. It opens
  the existing findings workspace and never fabricates a passing result.
- Light, Dark and High contrast themes include the graph. The adaptive grid and
  scale use actual metres; the axis marker is explicitly model +Y, not an assumed
  geographic north. Visible room outlines participate in Fit extents.
- Profile labels retain contrast on the selected canvas. Clean defaults to blue
  solid, Dirty to orange dashed; saved custom styles win. Colours never determine
  access. Shared access still means membership in the applicable route profiles.
- Door placement creates a restriction node, reuses a corridor node or atomically
  splits an edge. References and applicable attributes survive; each edit is one
  undo step. The opening width uses existing explicit/default semantics.

Legacy white map text follows the theme through an explicit display migration.
Other legacy custom map text retains its dark background. Stored preferences are
not overwritten until Apply; project and saved simulation inputs are unchanged.

## Actual application preview

Generate screenshots and an editable reference project with:

```powershell
.\.venv\Scripts\python.exe -m verification.cad_preview
```

- [Light workbench](latest/a2-ui/light-workbench.png)
- [Expanded properties](latest/a2-ui/properties.png)
- [Dark workbench](latest/a2-ui/dark-workbench.png)
- [High contrast](latest/a2-ui/high-contrast-workbench.png)
- [Compact 1024 × 768 window](latest/a2-ui/compact-workbench.png)
- [Editable reference project](latest/a2-ui/A2-reference.amrproj)

These images are captures of the application, not mockups. The deliberately small
UI example contains three location outlines and four door restrictions. Its
uncongested graph reference trips are 22 m and 20 m, taking 15 s and 14 s with a
2 m/s robot and four seconds handling. It is not a physical traffic study.

## Verification and limits

The linked [engineering pack](latest/index.html) records automated evidence.
The 3 October 2026 checkpoint passed all 1,829 tests in 634.080 seconds,
with unchanged source during verification and no broken evidence links.
Two LTN smoke runs produced identical outcomes: four completed tasks, zero
failed or pending tasks, and final simulation time 7,928.480894 seconds.
The smoke checks confirmed that both the input and source stayed unchanged.
These checks cover this UI checkpoint; the pack still identifies 267 options
without individually reviewed contracts, so they do not close the wider roadmap.

New acceptance covers working stage/menu actions, stale checks, theme/grid
isolation, old-preference migration, contrast, world grid/scale calculations,
visible-outline framing, large fonts, closed-window signal lifetime and atomic
Door placement. Existing interaction, project save/reopen and run tests remain.

This implements the concept's visual shell, not every future CAD command shown
in illustrative designs. Trim/fillet, full drawing layers and multi-object
transforms remain open and are not presented as working buttons. Doors are graph
width restrictions; no wall geometry or swing orientation is invented. Dense-map
label decluttering, playback theming, full geometry authoring, run editing locks,
human acceptance and the complete illustrated tutorial remain roadmap work.
