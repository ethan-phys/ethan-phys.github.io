## Publication Sync

You can check InspireHEP for new publications with:

```bash
python3 scripts/sync_publications.py
```

This performs a dry run and prints missing arXiv entries that are not yet in `_publications/`.

To create new markdown files automatically:

```bash
python3 scripts/sync_publications.py --write
```

The script:

- fetches publications from the InspireHEP author record `1712090`
- compares them against local `_publications/*.md` files by `arXiv`
- creates new numbered markdown files only for missing entries

Recommended workflow:

1. Run the dry check.
2. If the output looks correct, run with `--write`.
3. Review the new files in `_publications/`.
4. Run your Jekyll build/preview.
5. Commit and push.
