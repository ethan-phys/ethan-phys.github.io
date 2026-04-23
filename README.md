# Yu-Cheng Qiu Personal Site

This repository contains the source for Yu-Cheng Qiu's personal academic website. It is a Jekyll-based site for sharing research information, publications, CV material, presentations, and some blog posts.

## Overview

The site is built as a personal homepage with:

- a landing page and profile information
- a publications archive
- a CV page
- a presentations page
- a small blog section for notes and posts

## Local Development

Install dependencies and run the site locally:

```bash
bundle install
bundle exec jekyll serve
```

Then open:

```text
http://127.0.0.1:4000/
```

If your machine requires a specific Bundler version, install the version pinned in `Gemfile.lock` first.

## Project Structure

- `_posts/` for blog posts
- `_publications/` for publication entries
- `_layouts/` and `_includes/` for page templates
- `_sass/` and `css/` for styling
- `scripts/sync_publications.py` for syncing publication entries from InspireHEP

## Credits

This site is based on the original **Monochrome** Jekyll theme by **Dyuti Barma**.

- Original theme author: [Dyuti Barma](https://github.com/dyutibarma)
- Original theme: [Monochrome](https://dyutibarma.github.io/monochrome/)

This repository was further adapted into a personal academic site by **Yu-Cheng Qiu**, with additional development and editing support from **OpenAI Codex**.

## License

Released under the [MIT License](license.md).
