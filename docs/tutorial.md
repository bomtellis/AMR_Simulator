---
layout: default
title: Tutorial
permalink: /tutorial/
---
<p class="eyebrow">Learn by doing</p>

# Building flow tutorial

Build, test and improve a three-floor example using the **current 12-part guided
tutorial**. You work in the application while a small instruction bubble points
to the next control and checks your progress.

[Open the full illustrated tutorial](building-tutorial/Building-Flow-Tutorial.md){: .button }

## Start in the application

1. [Run from source](development.md), or use the Windows package when it becomes available.
2. Choose **Help → Building flow tutorial…**.
3. Start with **Create the project**. To use prepared drawings, open **More → Start from drawings** and save your own working copy.
4. Follow the bubble. **Next** becomes available after the requested actions pass.
   Use **Details** for instructions/corrections and **Show control** to find the control.

<figure class="tutorial-photo">
  <img src="{{ '/building-tutorial/images/bubble.png' | relative_url }}" alt="Current Building flow tutorial bubble pointing to the next action in the simulator workbench">
  <figcaption>The guided tutorial runs beside the model you are building.</figcaption>
</figure>

## The 12 parts

<ol class="course-list">
  <li>Create the project</li>
  <li>Learn the workbench</li>
  <li>Draw clean and dirty circulation</li>
  <li>Add dispatch, charging and wash facilities</li>
  <li>Configure transport</li>
  <li>Define your flow policy</li>
  <li>Generate deliveries and collections</li>
  <li>Check, save and run Simple</li>
  <li>Investigate and play back</li>
  <li>Stress the design</li>
  <li>Improve lift locations</li>
  <li>Report and hand over</li>
</ol>

## Practice files

Download the three aligned drawings: [floor 0](building-tutorial/floor-0.dxf),
[floor 1](building-tutorial/floor-1.dxf), and [floor 2](building-tutorial/floor-2.dxf).
Each floor is 40 × 20 m with a common origin. The tutorial uses 3.5 m level heights.

For source development, generate the portable starter and chapter checkpoints
from the repository root after installing dependencies:

**Windows (PowerShell)**

```powershell
.\.venv\Scripts\python.exe -m amr_tutorial_assets .cache\building-practice
```

**macOS / Linux**

```bash
./.venv/bin/python -m amr_tutorial_assets .cache/building-practice
```

Open `.cache/building-practice/starter.amrproj` in the application, then save your
own working project. The generated folder also contains chapter 3–7 checkpoints
and dedicated/shared reference projects. These archives are generated locally;
the Windows package can include them when it is built.

## Pause and resume

Use **Pause** to remove the aids. Choose **Help → Building flow tutorial…** to
resume. Progress is stored beside your project in its `.amrproj.tutorial.json`
companion file; keep it with your working copy. **Help → Restart tutorial bubble**
restores the bubble at the current step without resetting your project or progress.

The [full illustrated guide](building-tutorial/Building-Flow-Tutorial.md) contains
the current steps, exact example values, screenshots and explanations.
