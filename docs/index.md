---
layout: default
title: Project
permalink: /
page_class: project-page
---
<section class="hero">
  <h1>AMR Feasibility Tool</h1>
  <p class="hero-subtitle">A feasibility tool for autonomous mobile robot logistics.</p>
  <div class="actions">
    <a class="button" href="#downloads">Windows download</a>
    <a class="button secondary" href="{{ '/development/' | relative_url }}">Run from source</a>
  </div>
</section>

## About the project

<div class="description-draft" markdown="1">
**Autonomous mobile robot feasibility**

<p>
  The AMR Simulator is a desktop feasibility and planning tool for assessing autonomous mobile robot logistics within buildings. It helps users model operations, compare designs and identify capacity constraints before deployment.
</p>

<p>
  Its capabilties include:
  <ul>
    <li>Creating multi-floor layouts using DXF or PDF plans, with corridors, doors, lifts, storage and charging bays.</li>
    <li>Configuring robot fleets, payloads, delivery demand, departments and staff workflows.</li>
    <li>Simulating routing, traffic interactions, lift usage, battery consumption, charging and payload returns.</li>
    <li>Reviewing operations through animated playback and task, lift and payload monitoring.</li>
    <li>Comparing scenarios and lift arrangements to investigate bottlenecks and service performance.</li>
    <li>Producing PDF reports and CSV exports covering demand, utilisation, delays, energy and operational KPIs.</li>
  </ul>
</p>

</div>

<section id="downloads" class="downloads-section">
  <p class="eyebrow">Get the application</p>
  <h2>Windows download</h2>
  {% include windows-download.html %}
</section>

<section class="next-steps">
  <div>
    <p class="eyebrow">For development</p>
    <h2>Start with the source</h2>
    <p>Set up a Python environment on Windows, macOS or Linux, install the dependencies, and open the application.</p>
    <a class="text-link" href="{{ '/development/' | relative_url }}">Development setup →</a>
  </div>
  <div>
    <p class="eyebrow">Learn by doing</p>
    <h2>Building flow tutorial</h2>
    <p>Follow the current 12-part guided course in the application. Build a three-floor example, run it, and compare an improved design.</p>
    <a class="text-link" href="{{ '/tutorial/' | relative_url }}">Start the tutorial →</a>
  </div>
</section>
