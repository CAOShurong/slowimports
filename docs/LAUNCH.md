# Launch notes

Searchable problem: Python CLIs that take a second to print `--help`.

Show HN title:

```text
Show HN: slowimports – which imports you can actually make lazy
```

Body:

```text
python -X importtime dumps 900 nested lines. slowimports reads that dump
and your source, then tells you which imports are only used inside functions
so you can move them and get the milliseconds back.

  uvx slowimports -m pytest --advice

No dependencies. Not a sampling profiler — import-time only.

https://github.com/CAOShurong/slowimports
```
