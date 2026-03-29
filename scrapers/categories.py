"""Normalize supermarket-specific categories into a unified set.

Each supermarket uses its own category taxonomy – from 3 categories (MPreis) to
392 (Billa).  This module maps every raw category string to one of ~15
**normalized categories** so the Flutter app can offer a single, consistent
category filter across all stores.

Strategy
--------
1. **Exact-match dict** for every known raw category (fast, O(1) lookup).
2. **Keyword fallback** for unknown / future categories – tries substring
   matching against a priority-ordered list of keyword → normalizedCategory
   rules.
3. Falls back to ``"Sonstiges"`` if nothing matches.

The normalized categories are designed to be user-friendly German labels
suitable for direct display in the app UI.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────────────
# Normalized category constants
# ──────────────────────────────────────────────────────────────────────────────

OBST_GEMUESE = "Obst & Gemüse"
BROT_GEBAECK = "Brot & Gebäck"
MILCHPRODUKTE = "Milchprodukte"
FLEISCH_FISCH = "Fleisch & Fisch"
TIEFKUEHL = "Tiefkühl"
GETRAENKE = "Getränke"
SUESSES_SNACKS = "Süßes & Snacks"
KAFFEE_TEE = "Kaffee & Tee"
GRUNDNAHRUNGSMITTEL = "Grundnahrungsmittel"
FERTIGGERICHTE = "Fertiggerichte"
FRUEHSTUECK_AUFSTRICHE = "Frühstück & Aufstriche"
ALKOHOL = "Alkohol"
DROGERIE_HAUSHALT = "Drogerie & Haushalt"
BABY_TIER = "Baby & Tier"
SONSTIGES = "Sonstiges"

# Ordered list for display in the app
NORMALIZED_CATEGORIES: list[str] = [
    OBST_GEMUESE,
    BROT_GEBAECK,
    MILCHPRODUKTE,
    FLEISCH_FISCH,
    TIEFKUEHL,
    GETRAENKE,
    SUESSES_SNACKS,
    KAFFEE_TEE,
    GRUNDNAHRUNGSMITTEL,
    FERTIGGERICHTE,
    FRUEHSTUECK_AUFSTRICHE,
    ALKOHOL,
    DROGERIE_HAUSHALT,
    BABY_TIER,
    SONSTIGES,
]

# ──────────────────────────────────────────────────────────────────────────────
# Exact-match mapping   (raw category → normalized)
#
# Covers Billa (392), Spar (13), Hofer (9), Penny (56), Lidl (17), MPreis (3).
# Keep sorted by supermarket for maintainability.
# ──────────────────────────────────────────────────────────────────────────────

_EXACT: dict[str, str] = {
    # ── Spar (URL slugs) ─────────────────────────────────────────────────
    "obst-gemuese": OBST_GEMUESE,
    "brot-gebaeck": BROT_GEBAECK,
    "milchprodukte-alternativen": MILCHPRODUKTE,
    "wurst-fleisch-eier-fisch": FLEISCH_FISCH,
    "tiefkuehlprodukte": TIEFKUEHL,
    "alkoholfreie-getraenke": GETRAENKE,
    "alkoholische-getraenke": ALKOHOL,
    "suesses-salziges": SUESSES_SNACKS,
    "kaffee-tee-kakao": KAFFEE_TEE,
    "backen-fruehstueck": FRUEHSTUECK_AUFSTRICHE,
    "beilagen-essig-oel-gewuerze": GRUNDNAHRUNGSMITTEL,
    "schnelle-kueche-to-go": FERTIGGERICHTE,
    "babynahrung": BABY_TIER,

    # ── Hofer ─────────────────────────────────────────────────────────────
    "brot-und-backwaren": BROT_GEBAECK,
    "fleisch-und-fisch": FLEISCH_FISCH,
    "getraenke": GETRAENKE,
    "kuehlung": MILCHPRODUKTE,
    "suesses-und-salziges": SUESSES_SNACKS,
    "tiefkuehlung": TIEFKUEHL,
    "tiefpreis-aktionen": SONSTIGES,
    "vorratsschrank": GRUNDNAHRUNGSMITTEL,
    "angebote": SONSTIGES,

    # ── MPreis ────────────────────────────────────────────────────────────
    "lebensmittel": SONSTIGES,
    "aktionen": SONSTIGES,

    # ── Lidl ──────────────────────────────────────────────────────────────
    "Obst & Gemüse": OBST_GEMUESE,
    "Frisches Brot & Gebäck": BROT_GEBAECK,
    "Käse & Molkerei": MILCHPRODUKTE,
    "Fleisch & Wurst": FLEISCH_FISCH,
    "Fisch & Meeresfrüchte": FLEISCH_FISCH,
    "Tiefkühlkost": TIEFKUEHL,
    "Getränke": GETRAENKE,
    "Snacks & Süßigkeiten": SUESSES_SNACKS,
    "Kaffee, Tee & Kakao": KAFFEE_TEE,
    "Eier & Grundnahrungsmittel": GRUNDNAHRUNGSMITTEL,
    "Fette, Öle, Essig & Konserven": GRUNDNAHRUNGSMITTEL,
    "Gewürze, Senf & Saucen": GRUNDNAHRUNGSMITTEL,
    "Marmeladen & Brotaufstriche": FRUEHSTUECK_AUFSTRICHE,
    "Fertiggerichte": FERTIGGERICHTE,
    "Feinkost": FERTIGGERICHTE,
    "Wein & Spirituosen": ALKOHOL,
    "Drogerie": DROGERIE_HAUSHALT,

    # ── Penny ─────────────────────────────────────────────────────────────
    "Obst": OBST_GEMUESE,
    "Gemüse & Kräuter": OBST_GEMUESE,
    "Gemüse & Salate": OBST_GEMUESE,
    "Brot & Gebäck": BROT_GEBAECK,
    "Milchprodukte": MILCHPRODUKTE,
    "Käse, Aufstriche & Salate": MILCHPRODUKTE,
    "Fleisch": FLEISCH_FISCH,
    "Fisch": FLEISCH_FISCH,
    "Fisch & Garnelen": FLEISCH_FISCH,
    "Wurst, Schinken & Speck": FLEISCH_FISCH,
    "Pommes Frites & Co.": TIEFKUEHL,
    "Eis": TIEFKUEHL,
    "Alkoholfreie Getränke": GETRAENKE,
    "Mineralwasser": GETRAENKE,
    "Chips & Co.": SUESSES_SNACKS,
    "Schokolade": SUESSES_SNACKS,
    "Süßwaren": SUESSES_SNACKS,
    "Kuchen & Co.": SUESSES_SNACKS,
    "Kaffee, Tee & Co.": KAFFEE_TEE,
    "Reis, Teigwaren & Sugo": GRUNDNAHRUNGSMITTEL,
    "Basisprodukte": GRUNDNAHRUNGSMITTEL,
    "Konserven & Sauerwaren": GRUNDNAHRUNGSMITTEL,
    "Essig & Öle": GRUNDNAHRUNGSMITTEL,
    "Gewürze & Würzmittel": GRUNDNAHRUNGSMITTEL,
    "Saucen & Dressings": GRUNDNAHRUNGSMITTEL,
    "Zucker & Süßstoffe": GRUNDNAHRUNGSMITTEL,
    "Backen": GRUNDNAHRUNGSMITTEL,
    "Schnelle Küche": FERTIGGERICHTE,
    "Fertiggerichte": FERTIGGERICHTE,
    "Asia Produkte": FERTIGGERICHTE,
    "Blätterteig & Strudelteig": FERTIGGERICHTE,
    "Honig, Marmelade & Co.": FRUEHSTUECK_AUFSTRICHE,
    "Müsli & Cerealien": FRUEHSTUECK_AUFSTRICHE,
    "Bier & Radler": ALKOHOL,
    "Wein": ALKOHOL,
    "Spirituosen": ALKOHOL,
    "Sekt & Champagner": ALKOHOL,
    "Haushalt": DROGERIE_HAUSHALT,
    "Küche": DROGERIE_HAUSHALT,
    "Reinigen & Pflegen": DROGERIE_HAUSHALT,
    "Waschmittel & Weichspüler": DROGERIE_HAUSHALT,
    "Küchenrollen & WC-Papier": DROGERIE_HAUSHALT,
    "Taschentücher & Servietten": DROGERIE_HAUSHALT,
    "Seifen & Duschbäder": DROGERIE_HAUSHALT,
    "Haarpflege & Haarfarben": DROGERIE_HAUSHALT,
    "Haut- & Lippenpflege": DROGERIE_HAUSHALT,
    "Mund- & Zahnhygiene": DROGERIE_HAUSHALT,
    "Sonnen- & Insektenschutzmittel": DROGERIE_HAUSHALT,
    "Hunde": BABY_TIER,
    "Katzen": BABY_TIER,
    "Wochenangebote": SONSTIGES,
    "Non-Food-Artikel": SONSTIGES,
    "Pflanzen & Blumen": SONSTIGES,
    "Bekleidung & Textilien": SONSTIGES,
    "Spiele, Bücher & Co.": SONSTIGES,
    "Strumpfhosen & Socken": SONSTIGES,

    # ── Billa (top-level / unambiguous) ───────────────────────────────────
    # Obst & Gemüse
    "Obst": OBST_GEMUESE,
    "Gemüse": OBST_GEMUESE,
    "Gartengemüse": OBST_GEMUESE,
    "Kartoffeln": OBST_GEMUESE,
    "Salate": OBST_GEMUESE,
    "Salate verpackt": OBST_GEMUESE,
    "Pilze": OBST_GEMUESE,
    "Kräuter": OBST_GEMUESE,
    "Exotisches Obst": OBST_GEMUESE,
    "Steinobst & Beeren": OBST_GEMUESE,
    "Äpfel, Birnen & Trauben": OBST_GEMUESE,
    "Zitrusfrüchte": OBST_GEMUESE,
    "Zwiebeln & Knoblauch": OBST_GEMUESE,

    # Brot & Gebäck
    "Brot & Gebäck": BROT_GEBAECK,
    "Brot & Gebäck verpackt": BROT_GEBAECK,
    "Brot verpackt": BROT_GEBAECK,
    "Brötchen": BROT_GEBAECK,
    "Brezen": BROT_GEBAECK,
    "Semmeln & Salzstangerl": BROT_GEBAECK,
    "Toastbrot": BROT_GEBAECK,
    "Baguette & Co": BROT_GEBAECK,
    "Brioche, Striezel & Plunder": BROT_GEBAECK,
    "Frische Misch-, Vollkorn- & Kornbrote": BROT_GEBAECK,
    "Frische Weißbrote & Baguette": BROT_GEBAECK,
    "Korn- & Vollkorngebäck": BROT_GEBAECK,
    "Ofenfrisches Gebäck": BROT_GEBAECK,
    "Sonstiges Gebäck": BROT_GEBAECK,
    "Aufbackbrötchen & Baguettes": BROT_GEBAECK,
    "Knäckebrot": BROT_GEBAECK,
    "Knäckebrot & Zwieback": BROT_GEBAECK,
    "Zwieback": BROT_GEBAECK,
    "Glutenfreie Backwaren": BROT_GEBAECK,
    "Backwaren": BROT_GEBAECK,

    # Milchprodukte
    "Milch": MILCHPRODUKTE,
    "Haltbar Milch": MILCHPRODUKTE,
    "Milchalternativen": MILCHPRODUKTE,
    "Milch- & Joghurtgetränke": MILCHPRODUKTE,
    "Milchsnacks": MILCHPRODUKTE,
    "Butter": MILCHPRODUKTE,
    "Margarine": MILCHPRODUKTE,
    "Rahm, Obers & Topfen": MILCHPRODUKTE,
    "Rahm & Obers Alternativen": MILCHPRODUKTE,
    "Joghurt-Alternativen": MILCHPRODUKTE,
    "Fruchtjoghurt": MILCHPRODUKTE,
    "Natur": MILCHPRODUKTE,
    "mit Geschmack": MILCHPRODUKTE,
    "Frischkäse & Hüttenkäse": MILCHPRODUKTE,
    "Hartkäse": MILCHPRODUKTE,
    "Weichkäse": MILCHPRODUKTE,
    "Schmelzkäse": MILCHPRODUKTE,
    "Käse Snacks": MILCHPRODUKTE,
    "Käse gerieben": MILCHPRODUKTE,
    "Parmesan": MILCHPRODUKTE,
    "Feta & Mozarella": MILCHPRODUKTE,
    "Schaf- & Ziegenkäse": MILCHPRODUKTE,
    "Grill-, Brat- & Ofenkäse": MILCHPRODUKTE,
    "Eier": MILCHPRODUKTE,
    "Pudding": MILCHPRODUKTE,
    "Desserts": MILCHPRODUKTE,
    "Molkerei Produkte": MILCHPRODUKTE,
    "Aufstriche": MILCHPRODUKTE,
    "Aufstriche & Frischkäse-Alternativen": MILCHPRODUKTE,
    "Aufstriche- & Frischkäsealternative": MILCHPRODUKTE,

    # Fleisch & Fisch
    "Fleisch": FLEISCH_FISCH,
    "Fisch": FLEISCH_FISCH,
    "Rindfleisch": FLEISCH_FISCH,
    "Schweinefleisch": FLEISCH_FISCH,
    "Geflügel": FLEISCH_FISCH,
    "Huhn": FLEISCH_FISCH,
    "Pute": FLEISCH_FISCH,
    "Wild & Saisonales": FLEISCH_FISCH,
    "Diverse Fleischsorten": FLEISCH_FISCH,
    "Faschiertes": FLEISCH_FISCH,
    "Mariniertes": FLEISCH_FISCH,
    "Leberkäse": FLEISCH_FISCH,
    "Frischfisch": FLEISCH_FISCH,
    "Fisch-Spezialitäten": FLEISCH_FISCH,
    "Fisch-Alternativen": FLEISCH_FISCH,
    "Meeresfrüchte": FLEISCH_FISCH,
    "Fisch & Fleisch": FLEISCH_FISCH,
    "Fleisch-Alternativen": FLEISCH_FISCH,
    "Schinken": FLEISCH_FISCH,
    "Speck": FLEISCH_FISCH,
    "Snackwurst": FLEISCH_FISCH,
    "Snackwürste": FLEISCH_FISCH,
    "Würstel": FLEISCH_FISCH,
    "Aufschnitte & Stangenwurst": FLEISCH_FISCH,
    "Salami & co.": FLEISCH_FISCH,
    "Geflügelwurst,- Schinken & -Speck": FLEISCH_FISCH,
    "Streichwurst & Pasteten": FLEISCH_FISCH,
    "Streichwurst-Alternativen": FLEISCH_FISCH,
    "Stangen- & Snackwurst-Alternativen": FLEISCH_FISCH,
    "Wurst & Speck-Alternativen": FLEISCH_FISCH,
    "Wurstspezialitäten": FLEISCH_FISCH,
    "Grammeln & Schmalz": FLEISCH_FISCH,
    "Aus der Feinkost": FLEISCH_FISCH,
    "Antipasti": FLEISCH_FISCH,
    "Fleisch & Fisch Gläschen": BABY_TIER,

    # Tiefkühl
    "Eiscreme": TIEFKUEHL,
    "Eis am Stiel & Stanizl": TIEFKUEHL,
    "Eis-Snacks": TIEFKUEHL,
    "Pizza": TIEFKUEHL,
    "Pommes & Co": TIEFKUEHL,
    "Mehlspeisen, Torten": TIEFKUEHL,
    "Menüschalen": TIEFKUEHL,
    "Pikante & Süße Knödel": TIEFKUEHL,

    # Getränke
    "Alkoholfreie Getränke": GETRAENKE,
    "Limonaden": GETRAENKE,
    "Energydrinks": GETRAENKE,
    "Eistee": GETRAENKE,
    "Eiskaffee": GETRAENKE,
    "Mineralwasser": GETRAENKE,
    "still": GETRAENKE,
    "prickelnd": GETRAENKE,
    "Mineralwasser mit Geschmack": GETRAENKE,
    "Frucht- & Gemüsesäfte": GETRAENKE,
    "Dicksäfte & Sirupe": GETRAENKE,
    "Sirupe": GETRAENKE,
    "Smoothies & Fresh Juice": GETRAENKE,
    "Sportgetränke": GETRAENKE,
    "Kindergetränke": GETRAENKE,
    "Getränke": GETRAENKE,
    "Alkoholfreie Alternativen": GETRAENKE,

    # Süßes & Snacks
    "Chips": SUESSES_SNACKS,
    "Nachos & Dips": SUESSES_SNACKS,
    "Knabberein": SUESSES_SNACKS,
    "Kleine Snacks": SUESSES_SNACKS,
    "Snacks": SUESSES_SNACKS,
    "Kekse": SUESSES_SNACKS,
    "Kekse & Biskotten": SUESSES_SNACKS,
    "Biskotten": SUESSES_SNACKS,
    "Waffeln": SUESSES_SNACKS,
    "Schnitten": SUESSES_SNACKS,
    "Tafel": SUESSES_SNACKS,
    "Tafelschokolade": SUESSES_SNACKS,
    "Schokoriegel": SUESSES_SNACKS,
    "Fruchtgummi": SUESSES_SNACKS,
    "Kaugummi": SUESSES_SNACKS,
    "Zuckerl, Bonbons & Traubenzucker": SUESSES_SNACKS,
    "Süßes": SUESSES_SNACKS,
    "Süßes & Salziges": SUESSES_SNACKS,
    "Süßes & Desserts": SUESSES_SNACKS,
    "Süße Spezialitäten": SUESSES_SNACKS,
    "Konditorei & Süßes": SUESSES_SNACKS,
    "Aus der Konditorei": SUESSES_SNACKS,
    "Feinbackwaren & Süßes": SUESSES_SNACKS,
    "Reiswaffeln": SUESSES_SNACKS,
    "Kuchen, Muffins & Co verpackt": SUESSES_SNACKS,
    "Süsses & Salziges Glutenfrei": SUESSES_SNACKS,
    "Spezialitäten": SUESSES_SNACKS,
    "Platten": SUESSES_SNACKS,

    # Kaffee & Tee
    "Ganze Bohne": KAFFEE_TEE,
    "Gemahlen": KAFFEE_TEE,
    "Tabs & Pads": KAFFEE_TEE,
    "Koffeinfrei": KAFFEE_TEE,
    "Löslich": KAFFEE_TEE,
    "Kakao": KAFFEE_TEE,
    "Kaffee Getränke": KAFFEE_TEE,
    "Kräutertee": KAFFEE_TEE,
    "Früchtetee": KAFFEE_TEE,
    "Schwarztee": KAFFEE_TEE,
    "Grüntee": KAFFEE_TEE,

    # Grundnahrungsmittel (Reis, Pasta, Konserven, Gewürze, Öle, Backen)
    "Spaghetti": GRUNDNAHRUNGSMITTEL,
    "Penne": GRUNDNAHRUNGSMITTEL,
    "Fussili": GRUNDNAHRUNGSMITTEL,
    "Tortellini": GRUNDNAHRUNGSMITTEL,
    "sonstige Pasta": GRUNDNAHRUNGSMITTEL,
    "Glutenfreie Pasta": GRUNDNAHRUNGSMITTEL,
    "Langkorn": GRUNDNAHRUNGSMITTEL,
    "Basmati": GRUNDNAHRUNGSMITTEL,
    "Rundkorn": GRUNDNAHRUNGSMITTEL,
    "Sonst. Reis": GRUNDNAHRUNGSMITTEL,
    "Reis & Pasta": GRUNDNAHRUNGSMITTEL,
    "Reis, Pasta & Beilagen": GRUNDNAHRUNGSMITTEL,
    "Couscous": GRUNDNAHRUNGSMITTEL,
    "Quinoa": GRUNDNAHRUNGSMITTEL,
    "Kichererbsen & Quinoa": GRUNDNAHRUNGSMITTEL,
    "Knödel & Püree": GRUNDNAHRUNGSMITTEL,
    "Semmelwürfel, Brösel & Co": GRUNDNAHRUNGSMITTEL,
    "Bohnen": GRUNDNAHRUNGSMITTEL,
    "Linsen & Erbsen": GRUNDNAHRUNGSMITTEL,
    "getrocknete Hülsenfrüchte": GRUNDNAHRUNGSMITTEL,
    "Tomaten": GRUNDNAHRUNGSMITTEL,
    "Tomatenmark": GRUNDNAHRUNGSMITTEL,
    "Tomatenprodukte & Pesto": GRUNDNAHRUNGSMITTEL,
    "Tomaten & Artischocken": GRUNDNAHRUNGSMITTEL,
    "geschälte Tomaten": GRUNDNAHRUNGSMITTEL,
    "gestückelte Tomaten": GRUNDNAHRUNGSMITTEL,
    "passierte Tomaten": GRUNDNAHRUNGSMITTEL,
    "Sugo": GRUNDNAHRUNGSMITTEL,
    "Pesto": GRUNDNAHRUNGSMITTEL,
    "Mais & Champions": GRUNDNAHRUNGSMITTEL,
    "Gurken": GRUNDNAHRUNGSMITTEL,
    "Sauerkraut": GRUNDNAHRUNGSMITTEL,
    "Oliven & Kapern": GRUNDNAHRUNGSMITTEL,
    "Kompott": GRUNDNAHRUNGSMITTEL,
    "im eigenen Saft": GRUNDNAHRUNGSMITTEL,
    "in Soße": GRUNDNAHRUNGSMITTEL,
    "in Öl": GRUNDNAHRUNGSMITTEL,
    "Dose": GRUNDNAHRUNGSMITTEL,
    "Suppen": GRUNDNAHRUNGSMITTEL,
    "Suppeneinlagen": GRUNDNAHRUNGSMITTEL,
    "Suppengewürze": GRUNDNAHRUNGSMITTEL,
    "Gewürzbriefe & Säcke": GRUNDNAHRUNGSMITTEL,
    "Gewürzgläser, Mühlen & Dosen": GRUNDNAHRUNGSMITTEL,
    "Ketchup": GRUNDNAHRUNGSMITTEL,
    "Senf & Kren": GRUNDNAHRUNGSMITTEL,
    "Mayonaise": GRUNDNAHRUNGSMITTEL,
    "Dressing": GRUNDNAHRUNGSMITTEL,
    "Würzsauce & Pasten": GRUNDNAHRUNGSMITTEL,
    "Sojasauce": GRUNDNAHRUNGSMITTEL,
    "Kochzutaten & Dressings": GRUNDNAHRUNGSMITTEL,
    "Basis- & Fixprodukte": GRUNDNAHRUNGSMITTEL,
    "Olive": GRUNDNAHRUNGSMITTEL,
    "Raps": GRUNDNAHRUNGSMITTEL,
    "Soja": GRUNDNAHRUNGSMITTEL,
    "Mandel": GRUNDNAHRUNGSMITTEL,
    "sonstige Öle": GRUNDNAHRUNGSMITTEL,
    "sonstiger Essig": GRUNDNAHRUNGSMITTEL,
    "Balsamico": GRUNDNAHRUNGSMITTEL,
    "Apfel": GRUNDNAHRUNGSMITTEL,
    "Weizenmehl": GRUNDNAHRUNGSMITTEL,
    "Roggenmehl": GRUNDNAHRUNGSMITTEL,
    "Dinkelmehl": GRUNDNAHRUNGSMITTEL,
    "sonstige Mehlsorten & Stärkemehl": GRUNDNAHRUNGSMITTEL,
    "Glutenfreies Mehl & Backmischungen": GRUNDNAHRUNGSMITTEL,
    "Backmischungen": GRUNDNAHRUNGSMITTEL,
    "Backpulver, Hefe & Natron": GRUNDNAHRUNGSMITTEL,
    "Geliermittel & sonstige Backhilfen": GRUNDNAHRUNGSMITTEL,
    "Backfette": GRUNDNAHRUNGSMITTEL,
    "Backfüllungen": GRUNDNAHRUNGSMITTEL,
    "Backdekoration & Streußel": GRUNDNAHRUNGSMITTEL,
    "Backpapier": GRUNDNAHRUNGSMITTEL,
    "Backfertige Teige": GRUNDNAHRUNGSMITTEL,
    "Aromen & Glasuren": GRUNDNAHRUNGSMITTEL,
    "Rund ums Backen": GRUNDNAHRUNGSMITTEL,
    "Gebäck & Teig": GRUNDNAHRUNGSMITTEL,
    "Weißer Zucker": GRUNDNAHRUNGSMITTEL,
    "Rohrzucker": GRUNDNAHRUNGSMITTEL,
    "Süßungsmittel": GRUNDNAHRUNGSMITTEL,
    "Sonstiger Zucker": GRUNDNAHRUNGSMITTEL,
    "Nüsse": GRUNDNAHRUNGSMITTEL,
    "Nüsse, Kerne & Rosinen": GRUNDNAHRUNGSMITTEL,
    "Trockenfrüchte": GRUNDNAHRUNGSMITTEL,
    "Trockenfrüchte & Nüsse": GRUNDNAHRUNGSMITTEL,
    "Nussmuse": GRUNDNAHRUNGSMITTEL,
    "Kochcremes ungekühlt": GRUNDNAHRUNGSMITTEL,
    "Desserts ungekühlt": GRUNDNAHRUNGSMITTEL,
    "Dessertsaucen & sonstige Pulver": GRUNDNAHRUNGSMITTEL,
    "Puddingpulver": GRUNDNAHRUNGSMITTEL,
    "Eiswürfel": GRUNDNAHRUNGSMITTEL,

    # Fertiggerichte
    "Internationale Küche": FERTIGGERICHTE,
    "Asia": FERTIGGERICHTE,
    "Asien": FERTIGGERICHTE,
    "Balkan": FERTIGGERICHTE,
    "Mediterran & Orientalisch": FERTIGGERICHTE,
    "Frische Pasta & Beilagen": FERTIGGERICHTE,
    "Sandwiches & Co": FERTIGGERICHTE,
    "Fertiggerichte Ungekühlt": FERTIGGERICHTE,
    "Vorgegart": FERTIGGERICHTE,
    "Tofu, Seitan & Co": FERTIGGERICHTE,
    "Tofu. Seitan & Co": FERTIGGERICHTE,

    # Frühstück & Aufstriche
    "Müsli": FRUEHSTUECK_AUFSTRICHE,
    "Cerealien & Frühstücksflocken": FRUEHSTUECK_AUFSTRICHE,
    "Cornflakes & Cerealien": FRUEHSTUECK_AUFSTRICHE,
    "Glutenfreie Cerealien & Müslis": FRUEHSTUECK_AUFSTRICHE,
    "Haferflocken": FRUEHSTUECK_AUFSTRICHE,
    "Hafer": FRUEHSTUECK_AUFSTRICHE,
    "Hirse": FRUEHSTUECK_AUFSTRICHE,
    "sonstiges Getreide": FRUEHSTUECK_AUFSTRICHE,
    "Porridge": FRUEHSTUECK_AUFSTRICHE,
    "Honig": FRUEHSTUECK_AUFSTRICHE,
    "Konfitüren": FRUEHSTUECK_AUFSTRICHE,
    "Süße Aufstriche": FRUEHSTUECK_AUFSTRICHE,
    "Schoko- & Nussaufstriche": FRUEHSTUECK_AUFSTRICHE,
    "Fruchtmus": FRUEHSTUECK_AUFSTRICHE,
    "Frucht & Müsliriegel": FRUEHSTUECK_AUFSTRICHE,
    "Müsliriegel & Fruchtriegel": FRUEHSTUECK_AUFSTRICHE,
    "Proteinriegel": FRUEHSTUECK_AUFSTRICHE,
    "Proteinpulver & Shakes": FRUEHSTUECK_AUFSTRICHE,
    "Sport & Nahrungsergänzung": FRUEHSTUECK_AUFSTRICHE,
    "Nahrungsergänzung": FRUEHSTUECK_AUFSTRICHE,
    "Trinkmahlzeit ungekühlt": FRUEHSTUECK_AUFSTRICHE,

    # Alkohol
    "Flaschenbier": ALKOHOL,
    "Dosenbier": ALKOHOL,
    "Radler": ALKOHOL,
    "Alkoholfreies Bier": ALKOHOL,
    "Alkopops": ALKOHOL,
    "Cider": ALKOHOL,
    "Rotwein": ALKOHOL,
    "Weißwein": ALKOHOL,
    "Rosé": ALKOHOL,
    "Dessertwein & Portwein": ALKOHOL,
    "Champagner": ALKOHOL,
    "Prosecco": ALKOHOL,
    "Schaumwein & Perlwein": ALKOHOL,
    "Sekt": ALKOHOL,
    "Gin": ALKOHOL,
    "Rum": ALKOHOL,
    "Vodka": ALKOHOL,
    "Tequila": ALKOHOL,
    "Schnaps": ALKOHOL,
    "Likör": ALKOHOL,
    "Cognac & Whiskey": ALKOHOL,
    "Aperitif & Digestif": ALKOHOL,
    "Alkoholfreie Spirituosen": ALKOHOL,

    # Drogerie & Haushalt
    "Allzweckreiniger": DROGERIE_HAUSHALT,
    "Alufolie": DROGERIE_HAUSHALT,
    "Beutel": DROGERIE_HAUSHALT,
    "Beutel & Sonstige Folien": DROGERIE_HAUSHALT,
    "Batterien": DROGERIE_HAUSHALT,
    "Kerzen": DROGERIE_HAUSHALT,
    "Grablichter": DROGERIE_HAUSHALT,
    "Spender": DROGERIE_HAUSHALT,
    "Handschuhe": DROGERIE_HAUSHALT,
    "Büro- & Schulartikel": DROGERIE_HAUSHALT,
    "Küchenrolle": DROGERIE_HAUSHALT,
    "Küchenutensilien": DROGERIE_HAUSHALT,
    "Servietten": DROGERIE_HAUSHALT,
    "Taschentücher": DROGERIE_HAUSHALT,
    "Taschentücher & Boxen": DROGERIE_HAUSHALT,
    "WC Papier": DROGERIE_HAUSHALT,
    "WC- und Badreiniger": DROGERIE_HAUSHALT,
    "Sanitär- & Abflussreiniger": DROGERIE_HAUSHALT,
    "Glasreinigung": DROGERIE_HAUSHALT,
    "Kalkentferner": DROGERIE_HAUSHALT,
    "Kleben und Befestigen": DROGERIE_HAUSHALT,
    "Küchenreiniger, Spülmittel & Tabs": DROGERIE_HAUSHALT,
    "Boden- & Möbelpflege": DROGERIE_HAUSHALT,
    "Reinigungsgeräte & Tücher": DROGERIE_HAUSHALT,
    "Lufterfrischer & Raumsprays": DROGERIE_HAUSHALT,
    "Textilerfrischer & Bügelhilfe": DROGERIE_HAUSHALT,
    "Waschmittel & Fleckentferner": DROGERIE_HAUSHALT,
    "Waschmaschinen- & Geschirrspülerpflege": DROGERIE_HAUSHALT,
    "Weichspüler": DROGERIE_HAUSHALT,
    "Müllentsorgung": DROGERIE_HAUSHALT,
    "Shampoo & Spülung": DROGERIE_HAUSHALT,
    "Duschgele": DROGERIE_HAUSHALT,
    "Badezusätze": DROGERIE_HAUSHALT,
    "Baden & Waschen": DROGERIE_HAUSHALT,
    "Desinfektion": DROGERIE_HAUSHALT,
    "Deoderants": DROGERIE_HAUSHALT,
    "Coloration": DROGERIE_HAUSHALT,
    "Styling Produkte & Co": DROGERIE_HAUSHALT,
    "Gesichtspflege und Reinigung": DROGERIE_HAUSHALT,
    "Lippenpflege": DROGERIE_HAUSHALT,
    "Sonnenschutz & -pflege": DROGERIE_HAUSHALT,
    "Insektenschutz": DROGERIE_HAUSHALT,
    "Hand": DROGERIE_HAUSHALT,
    "Ganzkörper": DROGERIE_HAUSHALT,
    "Fuß": DROGERIE_HAUSHALT,
    "Puder, Cremes & Öle": DROGERIE_HAUSHALT,
    "Enthaarungsmittel": DROGERIE_HAUSHALT,
    "Rasierer &-klingen": DROGERIE_HAUSHALT,
    "Rasierschaum & -gel": DROGERIE_HAUSHALT,
    "Zahnbürsten & Aufsteckbürsten": DROGERIE_HAUSHALT,
    "Zahnpasta & -pflege": DROGERIE_HAUSHALT,
    "Zahnseide & Interdental": DROGERIE_HAUSHALT,
    "Mundspülung & -wasser": DROGERIE_HAUSHALT,
    "Gebissreiniger & Haftcreme": DROGERIE_HAUSHALT,
    "Tampons": DROGERIE_HAUSHALT,
    "Einlagen & Binden": DROGERIE_HAUSHALT,
    "Pflaster & Verbandstoffe": DROGERIE_HAUSHALT,
    "Schwangerschaftstest": DROGERIE_HAUSHALT,
    "Verhütung & Gleitmittel": DROGERIE_HAUSHALT,
    "Schuhpflege": DROGERIE_HAUSHALT,
    "Hausschuhe": DROGERIE_HAUSHALT,
    "Blumenerde": DROGERIE_HAUSHALT,
    "Dünger": DROGERIE_HAUSHALT,
    "Party & Geschenke": DROGERIE_HAUSHALT,
    "Lose": DROGERIE_HAUSHALT,

    # Baby & Tier
    "Babynahrung im Glas": BABY_TIER,
    "Babytücher": BABY_TIER,
    "Milchpulver & Folgemilch": BABY_TIER,
    "Obst Gläschen": BABY_TIER,
    "Gemüse Gläschen": BABY_TIER,
    "Getreide Gläschen": BABY_TIER,
    "Quetschies": BABY_TIER,
    "Windeln": BABY_TIER,
    "Nassfutter": BABY_TIER,
    "Trockenfutter": BABY_TIER,
    "Katzepflege": BABY_TIER,
    "Kleintiere": BABY_TIER,
    "Kleintierpflege": BABY_TIER,
    "Vögel": BABY_TIER,

    # Sonstiges
    "Neu im Online Shop": SONSTIGES,
    "rein pflanzlich": SONSTIGES,
    "weitere Alternativen": SONSTIGES,

    # ── misc Billa sub-categories that could go either way ────────────────
    "Dessertwein & Portwein": ALKOHOL,
    "Füller": GRUNDNAHRUNGSMITTEL,
    "fein": FLEISCH_FISCH,
    "grob": FLEISCH_FISCH,
    "mild": GRUNDNAHRUNGSMITTEL,
}


# ──────────────────────────────────────────────────────────────────────────────
# Keyword-based fallback rules (checked in order, first match wins)
#
# Each entry is (keyword_lower, normalized_category).  The keyword is tested
# via ``keyword in raw_category_lower``.  More specific keywords come first
# to avoid false positives (e.g. "milchschok" before "milch").
# ──────────────────────────────────────────────────────────────────────────────

_KEYWORD_RULES: list[tuple[str, str]] = [
    # Baby & Tier (before generic food keywords)
    ("baby", BABY_TIER),
    ("windel", BABY_TIER),
    ("hund", BABY_TIER),
    ("katz", BABY_TIER),
    ("tier", BABY_TIER),
    ("vogel", BABY_TIER),
    ("vögel", BABY_TIER),

    # Drogerie (before food keywords)
    ("reinig", DROGERIE_HAUSHALT),
    ("wasch", DROGERIE_HAUSHALT),
    ("pflege", DROGERIE_HAUSHALT),
    ("shampoo", DROGERIE_HAUSHALT),
    ("dusch", DROGERIE_HAUSHALT),
    ("zahn", DROGERIE_HAUSHALT),
    ("seife", DROGERIE_HAUSHALT),
    ("papier", DROGERIE_HAUSHALT),
    ("drogerie", DROGERIE_HAUSHALT),
    ("haushalt", DROGERIE_HAUSHALT),
    ("küche", DROGERIE_HAUSHALT),

    # Specific food categories
    ("obst", OBST_GEMUESE),
    ("gemüse", OBST_GEMUESE),
    ("salat", OBST_GEMUESE),
    ("frucht", OBST_GEMUESE),

    ("brot", BROT_GEBAECK),
    ("gebäck", BROT_GEBAECK),
    ("semmel", BROT_GEBAECK),

    ("joghurt", MILCHPRODUKTE),
    ("käse", MILCHPRODUKTE),
    ("milch", MILCHPRODUKTE),
    ("molkerei", MILCHPRODUKTE),
    ("butter", MILCHPRODUKTE),
    ("topfen", MILCHPRODUKTE),
    ("rahm", MILCHPRODUKTE),

    ("fleisch", FLEISCH_FISCH),
    ("fisch", FLEISCH_FISCH),
    ("wurst", FLEISCH_FISCH),
    ("schinken", FLEISCH_FISCH),
    ("speck", FLEISCH_FISCH),

    ("tiefkühl", TIEFKUEHL),
    ("tiefkuehl", TIEFKUEHL),
    ("eis", TIEFKUEHL),
    ("pizza", TIEFKUEHL),

    ("bier", ALKOHOL),
    ("wein", ALKOHOL),
    ("spirit", ALKOHOL),
    ("sekt", ALKOHOL),
    ("schnaps", ALKOHOL),
    ("likör", ALKOHOL),
    ("alkohol", ALKOHOL),

    ("kaffee", KAFFEE_TEE),
    ("tee", KAFFEE_TEE),
    ("kakao", KAFFEE_TEE),

    ("getränk", GETRAENKE),
    ("saft", GETRAENKE),
    ("wasser", GETRAENKE),
    ("limonade", GETRAENKE),

    ("süß", SUESSES_SNACKS),
    ("schoko", SUESSES_SNACKS),
    ("chips", SUESSES_SNACKS),
    ("snack", SUESSES_SNACKS),
    ("keks", SUESSES_SNACKS),
    ("bonbon", SUESSES_SNACKS),

    ("müsli", FRUEHSTUECK_AUFSTRICHE),
    ("cereal", FRUEHSTUECK_AUFSTRICHE),
    ("honig", FRUEHSTUECK_AUFSTRICHE),
    ("marmelade", FRUEHSTUECK_AUFSTRICHE),
    ("aufstrich", FRUEHSTUECK_AUFSTRICHE),
    ("konfitür", FRUEHSTUECK_AUFSTRICHE),

    ("fertig", FERTIGGERICHTE),
    ("asia", FERTIGGERICHTE),

    ("pasta", GRUNDNAHRUNGSMITTEL),
    ("reis", GRUNDNAHRUNGSMITTEL),
    ("mehl", GRUNDNAHRUNGSMITTEL),
    ("gewürz", GRUNDNAHRUNGSMITTEL),
    ("konserv", GRUNDNAHRUNGSMITTEL),
    ("sauce", GRUNDNAHRUNGSMITTEL),
    ("essig", GRUNDNAHRUNGSMITTEL),
    ("öl", GRUNDNAHRUNGSMITTEL),
    ("zucker", GRUNDNAHRUNGSMITTEL),
    ("back", GRUNDNAHRUNGSMITTEL),
    ("nüsse", GRUNDNAHRUNGSMITTEL),
    ("suppe", GRUNDNAHRUNGSMITTEL),
]


def normalize_category(raw_category: str | None) -> str:
    """Map a raw supermarket category to a unified normalized category.

    Args:
        raw_category: The original category string from the scraper.

    Returns:
        One of the ``NORMALIZED_CATEGORIES`` strings.
    """
    if not raw_category:
        return SONSTIGES

    # 1. Exact match (fast path)
    result = _EXACT.get(raw_category)
    if result is not None:
        return result

    # 2. Keyword fallback (case-insensitive)
    lower = raw_category.lower()
    for keyword, category in _KEYWORD_RULES:
        if keyword in lower:
            return category

    # 3. Nothing matched
    return SONSTIGES
