#!/usr/bin/env python3
"""Stáhne aktuální ceny peletek podle sources.json a připíše je do data/prices.csv.

Jen standardní knihovna Pythonu (3.9+). Spuštění: python scraper/scrape.py
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources.json"
CSV_PATH = ROOT / "data" / "prices.csv"
JSON_PATH = ROOT / "data" / "prices.json"
RUN_PATH = ROOT / "data" / "last_run.json"

BAG_KG = 15
# Rozumné rozpětí ceny za kg (Kč s DPH). Mimo něj považujeme výsledek za chybu.
MIN_KG_PRICE = 6.0
MAX_KG_PRICE = 30.0

FIELDS = [
    "date", "source_id", "shop", "product", "pack", "unit_kg", "price",
    "price_kg", "price_t", "price_bag", "delivery_included", "url",
]

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ScrapeError(Exception):
    pass


# ---------------------------------------------------------------- parsing

def parse_number(text) -> float | None:
    """Převede '14 980,50 Kč', '14.980', '14980.5', 13990 na float."""
    if isinstance(text, (int, float)):
        return float(text)
    if text is None:
        return None
    s = html.unescape(str(text))
    s = s.replace("\xa0", " ").replace(" ", " ")
    m = re.search(r"\d[\d .,]*", s)
    if not m:
        return None
    s = m.group(0).strip().replace(" ", "")
    s = s.rstrip(".,")
    if "," in s and "." in s:
        # 14.980,50 -> 14980.50 ; 14,980.50 -> 14980.50
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and len(s.split(".")[1]) == 3:
        # 14.980 = tisícový oddělovač
        s = s.replace(".", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


class _MetaCollector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.itemprop_price: list[str] = []
        self.jsonld: list[str] = []
        self.availability: list[str] = []
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a:
                self.meta.setdefault(key, a["content"])
        if a.get("itemprop") == "price":
            val = a.get("content") or a.get("value")
            if val:
                self.itemprop_price.append(val)
        if a.get("itemprop") == "availability":
            val = a.get("href") or a.get("content")
            if val:
                self.availability.append(val)
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._in_jsonld = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_jsonld:
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_jsonld:
            self._buf.append(data)


def _walk_jsonld(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk_jsonld(n)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "offers", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk_jsonld(node[key])


def _jsonld_prices(blocks: list[str]):
    prices, avail = [], []
    for raw in blocks:
        try:
            data = json.loads(raw.strip())
        except (ValueError, TypeError):
            continue
        for node in _walk_jsonld(data):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if "Offer" in types or "AggregateOffer" in types:
                for k in ("price", "lowPrice"):
                    if node.get(k) not in (None, ""):
                        prices.append(node[k])
                        break
                if node.get("availability"):
                    avail.append(str(node["availability"]))
    return prices, avail


def extract_price(page: str, extract: dict) -> tuple[float, bool | None]:
    """Vrátí (cena, skladem?). skladem je None, pokud ho nelze zjistit."""
    method = extract.get("method", "auto")
    if method == "regex":
        text = re.sub(r"<[^>]+>", " ", page)
        text = html.unescape(text).replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text)
        m = re.search(extract["pattern"], text)
        if not m:
            raise ScrapeError("regex nenašel cenu")
        val = parse_number(m.group(1))
        if val is None:
            raise ScrapeError(f"nečitelné číslo: {m.group(1)!r}")
        return val, None

    p = _MetaCollector()
    p.feed(page)
    candidates: list = []
    ld_prices, ld_avail = _jsonld_prices(p.jsonld)
    candidates += ld_prices
    for key in ("product:price:amount", "og:price:amount", "meta-product:price:amount",
                "twitter:data1", "price"):
        if key in p.meta:
            candidates.append(p.meta[key])
    candidates += p.itemprop_price
    for c in candidates:
        val = parse_number(c)
        if val and val > 0:
            avail_raw = (ld_avail or p.availability or [p.meta.get("product:availability", "")])[0].lower()
            in_stock = None
            if avail_raw:
                in_stock = ("instock" in avail_raw or "in stock" in avail_raw
                            or avail_raw in ("instock", "in_stock"))
            return val, in_stock
    raise ScrapeError("cena nenalezena (JSON-LD, meta ani itemprop)")


def choose_unit(price: float, kg) -> float:
    options = kg if isinstance(kg, list) else [kg]
    for unit in options:
        per_kg = price / unit
        if MIN_KG_PRICE <= per_kg <= MAX_KG_PRICE:
            return float(unit)
    raise ScrapeError(
        f"cena {price} nedává rozumnou cenu za kg pro balení {options} kg"
    )


def make_record(src: dict, price: float, today: str) -> dict:
    unit = choose_unit(price, src["kg"])
    per_kg = price / unit
    pack = src.get("pack", "?")
    if pack == "?":
        pack = {15.0: "pytel", 1.0: "kg"}.get(unit, "paleta")
    return {
        "date": today,
        "source_id": src["id"],
        "shop": src["shop"],
        "product": src["product"],
        "pack": pack,
        "unit_kg": f"{unit:g}",
        "price": f"{price:.2f}",
        "price_kg": f"{per_kg:.2f}",
        "price_t": f"{per_kg * 1000:.0f}",
        "price_bag": f"{per_kg * BAG_KG:.0f}",
        "delivery_included": "1" if src.get("delivery_included") else "0",
        "url": src["url"],
    }


# ---------------------------------------------------------------- IO

def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "cs,en;q=0.5",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def load_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_rows(rows: list[dict]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows.sort(key=lambda r: (r["date"], r["product"], r["source_id"]))
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(rows: list[dict], config: dict, run: dict) -> None:
    sources = {s["id"]: {k: s.get(k) for k in ("shop", "product", "pack", "url", "delivery")}
               for s in config["sources"]}
    num = ("unit_kg", "price", "price_kg", "price_t", "price_bag")
    out = []
    for r in rows:
        rec = dict(r)
        for k in num:
            rec[k] = float(rec[k])
        rec["delivery_included"] = rec.get("delivery_included") == "1"
        out.append(rec)
    payload = {
        "updated": run["finished"],
        "products": config["products"],
        "sources": sources,
        "status": run["results"],
        "rows": out,
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: list[str]) -> int:
    config = json.loads(SOURCES.read_text(encoding="utf-8"))
    only = set(argv[1:])
    today = dt.date.today().isoformat()
    rows = load_rows()
    # Jeden záznam na zdroj a den: dnešní běh přepíše dřívější dnešní.
    by_key = {(r["date"], r["source_id"]): r for r in rows}
    results = {}
    for src in config["sources"]:
        if src.get("disabled") or (only and src["id"] not in only):
            continue
        try:
            page = fetch(src["url"])
            price, in_stock = extract_price(page, src.get("extract", {}))
            rec = make_record(src, price, today)
            by_key[(today, src["id"])] = rec
            results[src["id"]] = {"ok": True, "price_t": float(rec["price_t"]),
                                  "in_stock": in_stock}
            print(f"OK   {src['id']:<18} {rec['price']:>10} Kč  -> {rec['price_t']} Kč/t")
        except Exception as e:  # noqa: BLE001 – chceme pokračovat dalšími zdroji
            results[src["id"]] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            print(f"FAIL {src['id']:<18} {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(1)

    rows = list(by_key.values())
    save_rows(rows)
    run = {
        "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "results": results,
    }
    RUN_PATH.write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    write_json(rows, config, run)

    failed = [k for k, v in results.items() if not v["ok"]]
    print(f"\nHotovo: {len(results) - len(failed)} OK, {len(failed)} chyb.")
    return 1 if results and len(failed) == len(results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
