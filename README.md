# Foodie – ICA Kvittoanalys

Analysera dina matvanor genom att importera digitala kvitton från ICA. Appen visar köpmönster, favoritvaror och utgifter över tid – allt lokalt i din webbläsare utan externa tjänster.

## Funktioner

- Ladda upp PDF-kvitton från ICA-appen eller ICAs webbportal
- Automatisk kategorisering av varor (mejeri, kött, grönsaker, dryck m.m.)
- Utgifter per kategori (cirkeldiagram)
- Mest köpta varor (stapeldiagram)
- Månadsvis utgiftstrend
- Kvittohistorik med datumfilter
- Lokal CSV-lagring – ingen databas, inga externa API-anrop

## Kom igång

### 1. Klona och installera

```bash
git clone <repo-url>
cd foodie
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Starta appen

```bash
streamlit run app.py
```

Öppna [http://localhost:8501](http://localhost:8501) i din webbläsare.

### 3. Hämta dina kvitton

Appen läser digitala ICA-kvitton i PDF-format. Du hittar dem på två ställen:

- **ICA-appen** → Köphistorik → välj ett kvitto → exportera som PDF
- **mina-kvitton.ica.se** → logga in och ladda ner kvitton som PDF

### 4. Ladda upp

Gå till **Ladda upp kvitto** i sidofältet, välj din PDF och klicka **Spara kvitto**. Upprepa för fler kvitton och se sedan dina trender under **Analys & Trender**.

## Projektstruktur

```
foodie/
├── app.py                  # Streamlit-app (UI)
├── core/
│   ├── analyzer.py         # Analys- och aggregeringslogik
│   └── categories.py       # Kategorisering av varor på svenska
├── integrations/
│   ├── pdf_parser.py       # PDF-parser för ICA-kvitton
│   └── storage.py          # CSV-läsning och -skrivning
├── tests/                  # Enhetstester (pytest)
├── data/                   # Skapas automatiskt, innehåller CSV-filer
├── requirements.txt
└── .env.example
```

## Köra tester

```bash
pytest tests/
```

## Teknisk stack

| Komponent | Bibliotek |
|-----------|-----------|
| UI | [Streamlit](https://streamlit.io) |
| PDF-parsing | [pdfplumber](https://github.com/jsvine/pdfplumber) |
| Databehandling | [pandas](https://pandas.pydata.org) |
| Diagram | [Plotly](https://plotly.com/python/) |
| Tester | [pytest](https://pytest.org) |

## Begränsningar (MVP)

- Stöder endast digitala ICA-kvitton i PDF-format (ej skannade papperskvitton)
- Ingen inloggning eller användarhantering – all data lagras lokalt i `data/`
- Kategorisering baseras på nyckelord och kan missa ovanliga produktnamn
