# Personal themes

Put extra looks for Merchant here as `<name>.css`, plus any fonts or images
they use. Git ignores everything in this folder except this note, so these
themes stay on your machine and never reach the repository.

Each file appears in the **Look** menu (bottom of the menu bar) under its file
name, for example `my-theme.css` shows as "My Theme". It is loaded after
`css/app.css`, so it only needs to restyle. With Docker, run
`docker compose up -d --build` after adding or changing a file here.

The markup hooks a theme can use are listed at the top of
`app/static/css/themes/orbit.css`.
