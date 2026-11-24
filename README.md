# Porovnávač cen peletek

Sleduje ceny peletek **A1 EN+ Lukapelet SMRK** a **MM Royal dřevěné pelety A1** u českých prodejců,
ukládá historii a zobrazuje ji na https://petrvo.github.io/peletky/.

## Jak to funguje

- `sources.json` – seznam sledovaných nabídek (URL, balení, způsob čtení ceny).
- `scraper/scrape.py` – stáhne stránky, vyčte cenu (JSON-LD, meta tagy, itemprop nebo regex)
  a přepočte ji na Kč/t, Kč/pytel 15 kg a Kč/kg. Jen standardní knihovna Pythonu.
- `data/prices.csv` – historie cen (jeden řádek na nabídku a den), `data/prices.json` – totéž pro web.
- `.github/workflows/scrape.yml` – GitHub Actions spouští sběr denně v 6:15 a změny commitne.
  Pokud se některý zdroj nepodaří načíst, založí/aktualizuje issue; když vše zase funguje, issue zavře.
- `index.html` + `assets/` – statická stránka s grafem vývoje a tabulkou nejlevnějších nabídek.

## Přidání prodejce

Přidej záznam do `sources.json`. Pro většinu e-shopů stačí `"extract": {"method": "auto"}`.
Když cena na stránce není ve strukturovaných datech, použij `regex` s jednou skupinou pro cenu.
`kg` je hmotnost kusu, za který e-shop cenu uvádí (pytel 15, paleta 1050, cena za kg 1).

## Lokálně

```
python scraper/scrape.py            # všechny zdroje
python scraper/scrape.py rvf-paleta # jen vybrané
python -m unittest discover -s scraper
python -m http.server               # web na http://localhost:8000
```
