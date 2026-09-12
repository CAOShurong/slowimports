# Launch notes — slowimports only

Searchable problem: Python CLI takes a second to print `--help`.

Show HN title:

```text
Show HN: slowimports --apply moves the imports that make --help slow
```

Body:

```text
python -X importtime dumps 900 nested lines. slowimports reads that dump
and your source, then rewrites the file: imports that are only used inside
functions get moved there.

  pip install slowimports
  slowimports your_cli.py --apply-dry-run
  slowimports your_cli.py --apply

On this repo's example, 169 ms of startup was only used in functions.
json stayed at module level because it runs at import time. Combined
`import a, b` lines are split; site-packages are refused.

Not a sampling profiler. Import-time only. No dependencies.

https://github.com/CAOShurong/slowimports
```
