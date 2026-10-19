"""Explicit maintenance tool; never called by the API or game creation.

Downloads the two Worldometer tables and fails closed if their structure changes.
Review the resulting diff before accepting a new snapshot.
"""
import argparse
import hashlib
import json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = "https://www.worldometers.info/world-population/population-by-country/"
ELIGIBILITY = "https://www.worldometers.info/geography/alphabetical-list-of-countries/"


class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": "", "links": []}
        elif tag == "a" and self.cell is not None:
            self.cell["links"].append(dict(attrs).get("href", ""))

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cell["text"] = self.cell["text"].strip()
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None


def download(url):
    with urlopen(Request(url, headers={"User-Agent": "GeopoliticsGame dataset review"}), timeout=30) as response:
        raw = response.read()
    parser = Tables()
    parser.feed(raw.decode("utf-8"))
    return raw, parser.rows


def main():
    arguments = argparse.ArgumentParser(description=__doc__)
    arguments.add_argument("--retrieved-on", required=True, type=date.fromisoformat,
                           help="Actual retrieval date in YYYY-MM-DD format")
    arguments.add_argument("--population-year", required=True, type=int,
                           help="Reference year verified against the source heading")
    options = arguments.parse_args()
    population_html, population_rows = download(SOURCE)
    eligibility_html, eligible_rows = download(ELIGIBILITY)
    # Both tables link to the same country population page, avoiding name aliases.
    def slug(cell):
        for link in cell["links"]:
            if "/world-population/" in link and "-population" in link:
                return link.rstrip("/").split("/")[-1].removesuffix("-population")
        raise ValueError(f"Missing country link: {cell['text']}")

    eligible = {slug(row[2]) for row in eligible_rows if len(row) >= 3 and row[0]["text"].isdigit()}
    if len(eligible) != 195:
        raise ValueError(f"Expected 195 eligible entries, got {len(eligible)}")
    countries, excluded = [], []
    for row in population_rows:
        if len(row) < 3 or not row[0]["text"].isdigit():
            continue
        record = {"id": slug(row[1]), "name": row[1]["text"], "population": int(row[2]["text"].replace(",", ""))}
        (countries if record["id"] in eligible else excluded).append(record)
    if len(countries) != 195 or len({c["id"] for c in countries}) != 195:
        raise ValueError("Population and eligibility tables do not match")
    # HTML may place attributes/tags between words; require a manual year review.
    import re
    plain = re.sub(r"<[^>]*>", " ", population_html.decode("utf-8"))
    if not re.search(rf"Population\s*\(?{options.population_year}", plain):
        raise ValueError("Review population reference year before updating")
    result = {
        "dataset_id": f"worldometer-{options.population_year}-{options.retrieved_on.isoformat()}",
        "source_url": SOURCE,
        "population_year": options.population_year,
        "retrieved_on": options.retrieved_on.isoformat(),
        "eligibility_source_url": ELIGIBILITY,
        "eligibility_policy": "Worldometer 195-country list; dependent territories and other entries excluded.",
        "source_sha256": hashlib.sha256(population_html).hexdigest(),
        "eligibility_sha256": hashlib.sha256(eligibility_html).hexdigest(),
        "countries": sorted(countries, key=lambda c: c["id"]),
        "excluded_entries": sorted(excluded, key=lambda c: c["id"]),
    }
    target = Path(__file__).resolve().parents[1] / "app/data/countries.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Saved {len(countries)} eligible countries; excluded {len(excluded)} entries")


if __name__ == "__main__":
    main()
