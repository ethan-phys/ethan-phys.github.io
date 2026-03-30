#!/usr/bin/env python3
"""Sync local Jekyll publications from InspireHEP.

Usage:
  python3 scripts/sync_publications.py
  python3 scripts/sync_publications.py --write

Default behavior is a dry run that reports new InspireHEP records that are not
yet represented in `_publications/`. With `--write`, the script creates new
Markdown files for missing arXiv entries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLICATIONS_DIR = REPO_ROOT / "_publications"
INSPIRE_AUTHOR_ID = "1712090"
DEFAULT_AUTHOR_NAME = "Yu-Cheng Qiu"
INSPIRE_API_URL = "https://inspirehep.net/api/literature"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
PAGE_SIZE = 250


@dataclass
class PublicationRecord:
    title: str
    authors: str
    author_names: list[str]
    arxiv_id: str
    record_date: str
    abstract: str
    primary_categories: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check InspireHEP for new publications and optionally write Jekyll markdown files."
    )
    parser.add_argument(
        "--author-id",
        default=INSPIRE_AUTHOR_ID,
        help=f"InspireHEP author record ID (default: {INSPIRE_AUTHOR_ID})",
    )
    parser.add_argument(
        "--author-name",
        default=DEFAULT_AUTHOR_NAME,
        help=f'Author name fallback query (default: "{DEFAULT_AUTHOR_NAME}")',
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Create markdown files for missing publications.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=PAGE_SIZE,
        help=f"Maximum number of InspireHEP records to fetch (default: {PAGE_SIZE}).",
    )
    return parser.parse_args()


def normalize_arxiv_id(value: str) -> str:
    cleaned = value.strip()
    cleaned = re.sub(r"^arxiv:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"v\d+$", "", cleaned)
    return cleaned


def load_existing_arxiv_ids() -> set[str]:
    arxiv_ids: set[str] = set()
    for path in PUBLICATIONS_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        match = re.search(r"^arXiv:\s*(.+?)\s*$", content, re.MULTILINE)
        if match:
            arxiv_ids.add(normalize_arxiv_id(match.group(1)))
    return arxiv_ids


def fetch_inspire_records(query: str, limit: int) -> list[dict]:
    params = {
        "q": query,
        "sort": "mostrecent",
        "size": str(limit),
        "fields": ",".join(
            [
                "titles.title",
                "abstracts.value",
                "authors.full_name",
                "arxiv_eprints.value",
                "primary_arxiv_category",
                "preprint_date",
                "earliest_date",
            ]
        ),
    }
    url = f"{INSPIRE_API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "qiuyucheng-site-publication-sync/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    return payload.get("hits", {}).get("hits", [])


def fetch_author_arxiv_categories(author_id: str) -> set[str]:
    url = f"https://inspirehep.net/api/authors/{author_id}?fields=arxiv_categories"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "qiuyucheng-site-publication-sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    categories = payload.get("metadata", {}).get("arxiv_categories") or []
    return {str(category).strip() for category in categories if str(category).strip()}


def fetch_author_bai(author_id: str) -> str | None:
    url = f"https://inspirehep.net/api/authors/{author_id}?fields=ids"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "qiuyucheng-site-publication-sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)

    identifiers = payload.get("metadata", {}).get("ids") or []
    for identifier in identifiers:
        if identifier.get("schema") == "INSPIRE BAI":
            value = str(identifier.get("value", "")).strip()
            if value:
                return value
    return None


def fetch_arxiv_ids_by_author(author_name: str, limit: int) -> list[str]:
    params = {
        "search_query": f'au:"{author_name}"',
        "start": "0",
        "max_results": str(limit),
    }
    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "qiuyucheng-site-publication-sync/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        xml_text = response.read()

    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    arxiv_ids: list[str] = []
    for entry in root.findall("atom:entry", ns):
        entry_id = entry.findtext("atom:id", default="", namespaces=ns)
        match = re.search(r"/abs/([^v]+)", entry_id)
        if match:
            arxiv_ids.append(normalize_arxiv_id(match.group(1)))
    return arxiv_ids


def extract_records(raw_records: Iterable[dict]) -> list[PublicationRecord]:
    extracted: list[PublicationRecord] = []
    for item in raw_records:
        metadata = item.get("metadata", {})
        arxiv_entries = metadata.get("arxiv_eprints") or []
        if not arxiv_entries:
            continue

        arxiv_id = normalize_arxiv_id(arxiv_entries[0].get("value", ""))
        if not arxiv_id:
            continue

        title_entries = metadata.get("titles") or []
        title = (title_entries[0].get("title", "") if title_entries else "").strip()
        if not title:
            continue

        author_entries = metadata.get("authors") or []
        authors = ", ".join(
            author.get("full_name", "").strip()
            for author in author_entries
            if author.get("full_name", "").strip()
        )

        abstract_entries = metadata.get("abstracts") or []
        abstract = (
            abstract_entries[0].get("value", "").strip() if abstract_entries else ""
        )

        record_date = metadata.get("preprint_date") or metadata.get("earliest_date") or str(
            date.today()
        )
        primary_categories = metadata.get("primary_arxiv_category") or []

        extracted.append(
            PublicationRecord(
                title=title,
                authors=authors,
                author_names=[
                    author.get("full_name", "").strip()
                    for author in author_entries
                    if author.get("full_name", "").strip()
                ],
                arxiv_id=arxiv_id,
                record_date=record_date,
                abstract=abstract,
                primary_categories=primary_categories,
            )
        )
    return extracted


def author_matches(record: PublicationRecord, author_name: str) -> bool:
    def canonicalize(name: str) -> str:
        cleaned = " ".join(name.lower().split())
        if "," in cleaned:
            family, given = [part.strip() for part in cleaned.split(",", 1)]
            cleaned = f"{given} {family}".strip()
        cleaned = re.sub(r"[^a-z0-9\s-]", "", cleaned)
        return cleaned

    normalized_target = canonicalize(author_name)
    normalized_authors = [
        canonicalize(author) for author in record.author_names if author.strip()
    ]
    return normalized_target in normalized_authors


def categories_match(record: PublicationRecord, allowed_categories: set[str]) -> bool:
    if not allowed_categories:
        return True
    if not record.primary_categories:
        return True
    return any(category in allowed_categories for category in record.primary_categories)


def collect_inspire_records(author_id: str, author_name: str, limit: int) -> list[PublicationRecord]:
    by_bai: list[dict] = []
    allowed_categories = fetch_author_arxiv_categories(author_id)
    author_bai = fetch_author_bai(author_id)
    if author_bai:
        by_bai = fetch_inspire_records(f'author:"{author_bai}"', limit)
        by_name: list[dict] = []
    else:
        by_name = fetch_inspire_records(
            f'exactauthor:"{author_name}" or exactauthor:"Qiu, Yu-Cheng"', limit
        )

    merged: dict[str, PublicationRecord] = {}

    for record in extract_records(by_bai):
        if categories_match(record, allowed_categories):
            merged[record.arxiv_id] = record

    for record in extract_records(by_name):
        if author_matches(record, author_name) and categories_match(
            record, allowed_categories
        ):
            merged.setdefault(record.arxiv_id, record)

    try:
        for arxiv_id in fetch_arxiv_ids_by_author(author_name, limit):
            if arxiv_id in merged:
                continue
            direct_records = extract_records(fetch_inspire_records(f"arxiv:{arxiv_id}", 1))
            for record in direct_records:
                if author_matches(record, author_name) and categories_match(
                    record, allowed_categories
                ):
                    merged.setdefault(record.arxiv_id, record)
    except urllib.error.URLError:
        pass

    return list(merged.values())


def next_publication_number() -> int:
    highest = 0
    for path in PUBLICATIONS_DIR.glob("*.md"):
        match = re.match(r"^(\d+)_", path.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def sanitize_filename(title: str) -> str:
    sanitized = title.replace("&mdash;", "--")
    sanitized = sanitized.replace("/", "-")
    sanitized = sanitized.replace(":", " -")
    sanitized = sanitized.replace("?", "")
    sanitized = sanitized.replace('"', "")
    sanitized = sanitized.replace("'", "")
    sanitized = sanitized.replace("\n", " ")
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def yaml_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_publication_file(record: PublicationRecord) -> str:
    abstract = record.abstract.strip() or "Abstract unavailable."
    return textwrap.dedent(
        f"""\
        ---
        title: {yaml_escape(record.title)}
        authors: {yaml_escape(record.authors)}
        arXiv: {record.arxiv_id}
        date: {record.record_date}
        ---
        {abstract}
        """
    )


def write_new_publications(records: list[PublicationRecord]) -> list[Path]:
    written: list[Path] = []
    next_number = next_publication_number()
    for record in records:
        filename = f"{next_number:02d}_{sanitize_filename(record.title)}.md"
        path = PUBLICATIONS_DIR / filename
        path.write_text(render_publication_file(record), encoding="utf-8")
        written.append(path)
        next_number += 1
    return written


def main() -> int:
    args = parse_args()

    if not PUBLICATIONS_DIR.exists():
        print(f"Missing publications directory: {PUBLICATIONS_DIR}", file=sys.stderr)
        return 1

    existing_arxiv_ids = load_existing_arxiv_ids()

    try:
        inspire_records = collect_inspire_records(
            args.author_id, args.author_name, args.limit
        )
    except urllib.error.URLError as exc:
        print(f"Failed to reach InspireHEP: {exc}", file=sys.stderr)
        return 1

    missing_records = [
        record for record in inspire_records if record.arxiv_id not in existing_arxiv_ids
    ]

    if not missing_records:
        print("No new InspireHEP arXiv publications found.")
        return 0

    print(f"Found {len(missing_records)} new publication(s):")
    for record in missing_records:
        print(f"- {record.arxiv_id} | {record.title}")

    if not args.write:
        print("\nDry run only. Re-run with --write to create markdown files.")
        return 0

    written_paths = write_new_publications(missing_records)
    print("\nCreated files:")
    for path in written_paths:
        print(f"- {path.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
