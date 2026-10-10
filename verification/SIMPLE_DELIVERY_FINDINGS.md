# Simple delivery findings — 9 October 2026

No unresolved crash, data-loss or core-action blocker was found in the selected
regressions and source/fresh-install small-map checks.

| Finding | Reproduction and effect | Correction and verification |
| --- | --- | --- |
| Practice-map start disagreed with guide | Open the supplied small map: B–C already existed, so the exercise's unreachable-task check could not be demonstrated. | Preserved original input, restored the intentionally missing B–C edge and selected Simple explicitly. Quick-start regression and source/installed connected-map runs passed. |
| Enlarged text reduced compact canvas area | Apply the actual 18-point appearance setting at 1024 × 768. The checks strip reduced canvas fraction to 46.44%. | Collapse that existing strip below 1400 logical pixels when text is at least 16 points. Check stage/tree retain access; summary in stage tooltip. Actual dark/high-contrast captures now show 51.67%; corrected appearance-aware layout regression passed. |
| Guide headings and title decoration | Render updated PDF/Word guide. PDF could leave a heading at page end; inherited Word Title added a blue rule. | Keep headings with following content and remove inherited rule. All five pages of both final guides inspected. |

## Known limitations

- The installer is an unsigned development package. Signing and formal release
  acceptance were not part of the requested delivery.
- Screen evidence uses offscreen Qt at the required logical sizes/scales.
  Another Windows host, physical display/DPI transitions and interactive
  assistive-technology use remain unverified.
- Large-text dialogs may require scrolling and tab-bar overflow navigation;
  Save/Cancel stay reachable. The compact enlarged-text Layout omits its check
  summary strip, with checks available through the existing stage and tree.
- LTN testing, benchmarking, repairs and acceptance are excluded. Existing LTN
  input and guide exercise are retained as historical material; the Simple
  practice map is the verified demonstration.
- Detailed movement and further Detailed development remain deferred. Existing
  imported projects/settings are preserved.
- This run/report contract retains its existing investigation limits and CSV
  evidence interfaces; no project schema or new public API was introduced.

Initial failed evidence is retained under `latest/simple-delivery/qa`; use
`verified-qa` and the `*-smoke-final` folders for the final delivery result.
