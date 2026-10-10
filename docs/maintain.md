---
title: Publish and maintain
nav_order: 10
permalink: /maintain/
---
# Publish and maintain this website

The documentation is a GitHub **project site** in the existing
`bomtellis/AMR_Simulator` repository. Its expected address is
[https://bomtellis.github.io/AMR_Simulator/](https://bomtellis.github.io/AMR_Simulator/).
You do not need a separate `bomtellis.github.io` repository or a custom domain.

## Publish for the first time

You need repository administration access for the Pages settings.

1. Prepare documentation changes on a branch based on fresh remote **main**, then
   review and merge that branch into **main**. The site configuration
   and homepage must exist at `docs/_config.yml` and `docs/index.md` on main.
2. On GitHub open **AMR_Simulator → Settings → Pages**.
3. Under **Build and deployment → Source**, select **Deploy from a branch**.
4. Select **main**, select **/docs**, then **Save**.
5. Open **Actions** and check the built-in **pages build and deployment** run.
6. When it succeeds, return to Pages and choose **Visit site**, or open the URL above.

GitHub runs its built-in Jekyll build for this branch source. This repository
does not require a custom publishing workflow. Subsequent changes merged to
`main/docs` are published automatically; allow time for the deployment to finish.

[GitHub's publishing-source instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
explain access requirements and available source settings.

For later updates, begin from a clean checkout and create a new branch:

```powershell
git fetch origin
git switch -c codex/docs-update origin/main
```

Edit and validate the pages, commit the documentation changes, push the branch
with `git push -u origin codex/docs-update`, then open and merge a pull request
on GitHub. Choose a fresh branch name when that example name is already in use.

## Edit and add pages

Edit Markdown under `docs`, using the page's **Edit this page on GitHub** link
or a local branch and pull request. The same files remain readable in the source
repository. Add front matter to every published page:

```yaml
---
title: New topic
parent: Build a model
nav_order: 5
---
```

Use an existing top-level title as `parent`. For a new top-level group omit
`parent`, choose a distinct `nav_order`, and set `has_children: true` when it has
child pages. Keep one Markdown H1 heading and an understandable reading order.

Link to other source Markdown files using relative paths, for example
`[Checks](check-simulate.md)`. The supported relative-links plugin converts these
to published page addresses and preserves the `/AMR_Simulator` project prefix.
Use relative paths for images and downloads too. Avoid root links such as
`/assets/...`, which would omit the project prefix.

Put screenshots beside the relevant guide in its `images` folder. Give each
image useful alternative text and check it at a narrow width. Download links
must point to tracked, complete inputs. Do not promise generated PDFs, `.amrproj`
archives or installer packages unless they are actually available at a stable URL.

## Check changes before merging

From the repository root:

```powershell
.\.venv\Scripts\python.exe docs\validate_site.py
```

This checks page metadata, parent navigation, local links/images/downloads and
the configured project URL/theme. To audit rendered HTML after a Jekyll build,
pass its output folder:

```powershell
.\.venv\Scripts\python.exe docs\validate_site.py --built-site docs\_build
```

For local Jekyll preview install Ruby and Bundler separately; on Windows use
RubyInstaller **Ruby+Devkit** so native gem dependencies can compile. Application
use does not require Ruby. From `docs`:

```powershell
bundle install
bundle exec jekyll serve --destination _build
```

Open the address printed by Jekyll with the `/AMR_Simulator/` suffix. Dependencies
for this preview are in `docs/Gemfile`. Do not add `.nojekyll`: these pages require
Markdown, Liquid, remote-theme and search generation.

After deployment verify the home page, a direct child-page URL, search for a
known setting, screenshots and practice downloads. Check both desktop and mobile
widths, tab through navigation/search, and check the built-in deployment log.

### Validation of this edition

The initial site was built locally with the GitHub Pages 232 dependency bundle,
Jekyll 3.10 and Just the Docs v0.12.0. The source/rendered link audit passed for
28 pages and 1,345 rendered local links. Browser checks covered desktop and
390-pixel mobile layouts, keyboard search-result selection, mobile navigation,
and loaded/scaled tutorial screenshots.

The application's quick-start tests and packaged-workbench smoke route passed
against the reviewed source: project save/reopen, checks, simulation, frozen
inputs, investigation, Playback and PDF report export. Tutorial asset generation
also produced all eight portable practice archives. These are checks of the
documentation and supplied exercises; they do not validate a real hospital study.
The built-in GitHub Pages deployment must still be checked after publication.

## Keep guidance aligned with the application

When a setting or workflow changes, update the relevant operating page in the
same change. Compare current controls and source contracts with the written
steps; old verification notes describe their own historical checkpoints.

Update `docs/_data/source.yml` only after reviewing the guidance against the
identified application commit. Its `commit`, `short_commit` and `reviewed` date
describe the content review, not necessarily the newest site-only commit.
Keep source evidence and limitations with the explanations they support.

## If publishing fails

- **404:** confirm the branch is main, folder is /docs, and the deployment finished.
  The project URL includes `/AMR_Simulator/` with the repository's exact spelling.
- **Plain Markdown or missing theme:** inspect `_config.yml`, page front matter
  and the Pages build error. Confirm no `.nojekyll` file is disabling Jekyll.
- **Missing images or broken links:** check case-sensitive paths and the project
  base URL; rerun the source and rendered link checks.
- **Search has no results:** confirm search is enabled and `assets/js/search-data.json`
  was built. Pages need front matter and must not be excluded from search.
- **No Pages controls:** ask the repository administrator to configure the source;
  changing Markdown alone cannot grant that permission.

The [Just the Docs documentation](https://just-the-docs.com/) explains theme
navigation and search. The theme is pinned to **v0.12.0** so an upstream main-branch
change does not silently alter this site's presentation.
