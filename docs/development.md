---
layout: default
title: Development setup
permalink: /development/
---
<p class="eyebrow">Run from source</p>

# Development setup

Create a separate Python environment, install the repository dependencies, and
launch `amr_app.py`. This is the source development route; it does not need the
future Windows installer. Use **Python 3.13** for this checkout.

<div class="platform-links">
  <a class="button secondary" href="#windows">Windows</a>
  <a class="button secondary" href="#macos">macOS</a>
  <a class="button secondary" href="#linux">Linux</a>
</div>

## Get the source

{% if site.data.downloads.source_url != "" %}
[Open the source repository]({{ site.data.downloads.source_url }})
{% else %}
**The source repository link will be added here.** If you already have a local
copy, use that folder and continue below.
{% endif %}
{% if site.data.downloads.source_archive_url != "" %}
[Download the source archive]({{ site.data.downloads.source_archive_url }})
{% endif %}

Download and extract the source archive, or clone the repository when its link
is available. Replace `https://github.com/bomtellis/AMR_Simulator/` with that actual Git URL before running:

```text
git clone https://github.com/bomtellis/AMR_Simulator/ AMR_Simulator
cd AMR_Simulator
```

Run the platform commands below **inside the source folder** containing
`amr_app.py` and `requirements.txt`. An internet connection is needed for the
first dependency installation.

## Windows

Install [Python 3.13 for Windows](https://www.python.org/downloads/windows/)
with the Python launcher. Open PowerShell in the source folder:

```powershell
py -3.13 --version
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe amr_app.py
```

Wait for installation to finish successfully before launching. Using the
environment's Python directly avoids PowerShell activation-policy changes.
For later launches, run the last command again.

## macOS

Install [Homebrew](https://brew.sh/) if you do not already use it. Install Python
3.13 and the Cairo prerequisites used by the reporting dependencies, then create
the environment in the source folder:

```bash
brew install python@3.13 cairo pkg-config
python3.13 --version
python3.13 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python amr_app.py
```

If a native dependency needs a compiler, install Apple's Command Line Tools with
`xcode-select --install` and retry the dependency installation. Use an interpreter
matching your Mac's architecture. The last command reopens the application later.

## Linux

Use a graphical desktop session. The example below uses
[uv](https://docs.astral.sh/uv/getting-started/installation/) to obtain Python
3.13 and create the environment without depending on your distribution's default
Python version. Install uv using its official instructions first.

For **Debian/Ubuntu**, install the Cairo build prerequisites:

```bash
sudo apt update
sudo apt install build-essential libcairo2-dev pkg-config
```

For another distribution, install its equivalent compiler, Cairo development
library and pkg-config packages. Then, inside the source folder:

```bash
uv python install 3.13
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
./.venv/bin/python amr_app.py
```

If you already have Python 3.13 with venv support and matching development
headers, you can use `python3.13 -m venv .venv` and the macOS pip/launch commands
instead. Reopen the application later with the last command above.

<details markdown="1">
<summary>If installation or launch fails</summary>

- Check the selected interpreter is Python 3.13 and you are in the source folder.
- A **Cairo/pkg-config** build error means a native prerequisite is missing. See
  [Pycairo's platform prerequisites](https://pycairo.readthedocs.io/en/latest/getting_started.html).
- A Linux **xcb** error needs the Qt runtime libraries for your desktop. On
  Debian/Ubuntu, `libxcb-cursor0` and `libxkbcommon-x11-0` are common missing
  packages; inspect the error and [Qt's Linux requirements](https://doc.qt.io/qt-6/linux-requirements.html).
- A **No matching distribution** error can indicate an unsupported Python,
  architecture or OS version for a pinned dependency. Keep `requirements.txt`
  unchanged and use a compatible environment.

</details>

These setup instructions cover all three platforms. This checkout has been run
on Windows; macOS and Linux installation still need testing on those hosts.

## Start learning

When the application opens, choose **Help → Building flow tutorial…**.
The [tutorial page](tutorial.md) explains the current guided course and practice files.
