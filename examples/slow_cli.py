"""A small CLI written the way most of them start out.

Every import sits at the top, which is the habit everyone is taught, and most
of the time it costs nothing. Here it costs real milliseconds, because three
of these are only needed on code paths that usually do not run: ``--report``
formats a table, ``--upload`` talks to the network, and the CSV path is only
taken for one of the two input formats.

Run ``slowimports examples/slow_cli.py --advice`` to see which ones can move.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import unittest.mock
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from email.message import EmailMessage

# Used while this module is being imported, so it cannot be deferred.
DEFAULT_FORMAT = json.dumps({"format": "json"})


def read_csv(path: str) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_xml(path: str) -> list[dict[str, str]]:
    tree = ET.parse(path)
    return [dict(element.attrib) for element in tree.getroot()]


def summarise(values: list[float]) -> dict[str, float]:
    return {
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def to_money(value: float) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def notify(address: str, body: str) -> None:
    message = EmailMessage()
    message["To"] = address
    message.set_content(body)


def upload_all(rows: list[dict[str, str]]) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda row: row, rows))


def fake_backend():
    return unittest.mock.MagicMock()


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise a data file.")
    parser.add_argument("path", nargs="?", default="data.csv")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args([])
    del args
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
