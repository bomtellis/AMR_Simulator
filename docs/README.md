# AMR Simulator website source

This package contains the project website, not the simulator application.

1. Extract this ZIP on the computer you choose to deploy from.
2. Create or choose your GitHub repository. Upload the extracted docs folder
   with its subfolders intact, at the root of the repository's main branch.
3. Edit docs/_config.yml. For bomtellis/AMR_Simulator use:
   url: "https://bomtellis.github.io"
   baseurl: "/AMR_Simulator"
   Adjust both values if you choose another account or repository name.
4. Fill in the project description in docs/index.md. Set future package/source
   links in docs/_data/downloads.yml when they exist; empty links are supported.
5. Open Settings > Pages. Choose Deploy from a branch, main, /docs, and Save.
6. Check the built-in pages build and deployment run, then use Visit site.

GitHub builds the Markdown pages with Jekyll. Upload the contents extracted from
this ZIP, not the ZIP itself or the contents of a generated _build folder.
Include the folders beginning with underscores: Jekyll needs them.
Later changes committed to the selected source are deployed automatically.

Official guidance:
https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site
