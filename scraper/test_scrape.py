import unittest

import scrape


class ParseNumber(unittest.TestCase):
    def test_formats(self):
        cases = {
            "14 980 Kč": 14980,
            "14\xa0980,50 Kč": 14980.5,
            "14.980,50": 14980.5,
            "14,980.50": 14980.5,
            "14.980": 14980,
            "13990": 13990,
            "12,89 Kč / kg": 12.89,
            "16099.00": 16099,
            13535: 13535,
        }
        for text, want in cases.items():
            self.assertAlmostEqual(scrape.parse_number(text), want, msg=repr(text))

    def test_none(self):
        self.assertIsNone(scrape.parse_number("bez ceny"))


class Extract(unittest.TestCase):
    def test_jsonld(self):
        page = """<script type="application/ld+json">{"@context":"https://schema.org",
        "@type":"Product","name":"x","offers":{"@type":"Offer","price":"184.00",
        "priceCurrency":"CZK","availability":"https://schema.org/InStock"}}</script>"""
        self.assertEqual(scrape.extract_price(page, {}), (184.0, True))

    def test_jsonld_graph(self):
        page = """<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},
        {"@type":"Product","offers":[{"@type":"Offer","price":13990,
        "availability":"OutOfStock"}]}]}</script>"""
        self.assertEqual(scrape.extract_price(page, {}), (13990.0, False))

    def test_meta(self):
        page = '<meta property="product:price:amount" content="16099">'
        self.assertEqual(scrape.extract_price(page, {})[0], 16099.0)

    def test_itemprop(self):
        page = '<span itemprop="price" content="214,00">214 Kč</span>'
        self.assertEqual(scrape.extract_price(page, {})[0], 214.0)

    def test_regex(self):
        page = "<p>Cena na paletě: <b>12,89&nbsp;Kč</b> / kg</p>"
        got = scrape.extract_price(page, {"method": "regex",
                                          "pattern": r"Cena na paletě:\s*([\d\s.,]+)\s*Kč"})
        self.assertEqual(got[0], 12.89)

    def test_missing(self):
        with self.assertRaises(scrape.ScrapeError):
            scrape.extract_price("<html></html>", {})


class Sources(unittest.TestCase):
    OKPALIVA = ("<div>1 - 2 palety</div><b>13.700&nbsp;Kč</b> <span>13,05 Kč / Kg</span>"
                "<p>cena včetně dopravy a DPH po celé ČR</p><div>11,60 Kč / Kg</div>"
                "<b>12.180 Kč</b><p>cena při osobním odběru včetně DPH</p>")

    def test_okpaliva_patterns(self):
        import json
        cfg = json.loads(scrape.SOURCES.read_text(encoding="utf-8"))
        src = {s["id"]: s for s in cfg["sources"]}
        self.assertEqual(scrape.extract_price(self.OKPALIVA, src["okpaliva-paleta"]["extract"])[0], 13700)
        self.assertEqual(scrape.extract_price(self.OKPALIVA, src["okpaliva-odber"]["extract"])[0], 12180)

    def test_dufa_pattern(self):
        import json
        cfg = json.loads(scrape.SOURCES.read_text(encoding="utf-8"))
        src = {s["id"]: s for s in cfg["sources"]}
        page = "<span>Ušetříte</span> <b>0 Kč s DPH</b><div>Naše cena s DPH</div><strong>12&nbsp;600 Kč</strong> /paleta"
        self.assertEqual(scrape.extract_price(page, src["dufa-paleta"]["extract"])[0], 12600)
        page = "<div>Naše cena s DPH</div>\n<strong>180 Kč</strong> /balík"
        self.assertEqual(scrape.extract_price(page, src["dufa-pytel"]["extract"])[0], 180)

    def test_ids_unique(self):
        import json
        cfg = json.loads(scrape.SOURCES.read_text(encoding="utf-8"))
        ids = [s["id"] for s in cfg["sources"]]
        self.assertEqual(len(ids), len(set(ids)))


class Record(unittest.TestCase):
    src = {"id": "x", "shop": "S", "product": "mm_royal", "url": "u"}

    def test_pallet(self):
        r = scrape.make_record({**self.src, "pack": "paleta", "kg": 1050}, 14980, "2026-11-24")
        self.assertEqual((r["price_t"], r["price_bag"], r["price_kg"]), ("14267", "214", "14.27"))

    def test_unit_candidates(self):
        r = scrape.make_record({**self.src, "pack": "?", "kg": [1050, 15, 1]}, 184, "d")
        self.assertEqual((r["unit_kg"], r["pack"]), ("15", "pytel"))
        r = scrape.make_record({**self.src, "pack": "?", "kg": [1050, 15, 1]}, 13.5, "d")
        self.assertEqual((r["unit_kg"], r["pack"]), ("1", "kg"))

    def test_implausible(self):
        with self.assertRaises(scrape.ScrapeError):
            scrape.make_record({**self.src, "kg": 1050}, 184, "d")


if __name__ == "__main__":
    unittest.main()
