# Fields by Scraper

Overview of which product fields are populated by each scraper. ✓ = always set, ~ = sometimes set, ✗ = always null.

## Angebots-Properties

| Field | Billa | Penny | Lidl | Hofer | SPAR | MPreis |
|-------|:-----:|:-----:|:----:|:-----:|:----:|:------:|
| `inPromotion` | ✓ | ✓ (immer) | ✓ (immer) | ✓ | ✓ | ✓ |
| `originalPrice` | ~ | ~ | ~ | ~ | ~ | ~ |
| `promotionText` | ~ | ~ | ~ | ~ | ~ | ~ |
| `offerStart` | ✗ | ✓ | ✓ | ~ | ✗ | ✗ |
| `offerEnd` | ✗ | ✓ | ✓ | ✗ | ✗ | ✗ |

### Anmerkungen

**Billa**
- Scraped alle Produktkategorien (nicht nur Angebote) → `inPromotion` kann `true` oder `false` sein
- `originalPrice` / `promotionText` kommen direkt aus der Billa REST API (`price.crossed`, `price.promotionText`)
- Kein Gültigkeitszeitraum in der API → `offerStart`/`offerEnd` bleiben null

**Penny**
- Scraped **nur** Angebote, über die Sammelkategorie `alle-angebote-99000000` ("Alle Angebote"; enthält aktuelle + kommende Wochen + Themen-Tabs), abgelaufene per `offerEnd < heute` verworfen → alle Produkte haben `inPromotion: true`
- `offerStart`/`offerEnd` kommen als ISO-Strings direkt aus der API (`price.validityStart`, `price.validityEnd`)

**Lidl**
- Scraped **nur** den Aktionsbereich (Essen & Trinken) → alle Produkte haben `inPromotion: true`
- `offerStart`/`offerEnd` kommen als Unix-Timestamps aus der API (`storeStartDate`, `storeEndDate`), werden in `YYYY-MM-DD` umgewandelt
- `promotionText` enthält Rabatttext (z.B. "-50%") und Lidl-Plus-Hinweis wenn vorhanden

**Hofer**
- Scraped reguläres Produktsortiment (Kategorien) + Angebotsflugblätter (nach Datum) + Tiefpreis-Aktionen-Seite → `inPromotion` kann `true` oder `false` sein
- Produkte aus dem regulären Sortiment sind nur bei durchgestrichenem Originalpreis `inPromotion: true`; Flugblatt- und Tiefpreis-Produkte immer
- `offerStart` wird aus dem Datum in der Flugblatt-URL extrahiert (Format `/d.DD-MM-YYYY.html`)
- `offerEnd` bleibt null (kein Enddatum in der Seitenstruktur verfügbar)
- `promotionText` ist bei Tiefpreis-Produkten immer `"Tiefpreis Aktion"`, sonst null
- `productUrl` ist immer null (Hofer hat keine individuellen Produktseiten)

**SPAR**
- Scraped alle Produktkategorien → `inPromotion` kann `true` oder `false` sein
- `originalPrice` wird aus DOM gescraped (`span.product-price__price-old`, enthält "statt X,XX")
- `promotionText` wird aus DOM gescraped (`div.product-price__promo-pill`, z.B. "Aktion!", "Immer billig!", "Mengenvorteil ab 2 Stk.")
- Flugblatt-Seiten sind Cloudflare-geschützt → `offerStart`/`offerEnd` nicht befüllbar

**MPreis**
- Scraped normale Kategorien (`lebensmittel`, `getraenke`) + Aktionsseite (`aktionen`)
- `originalPrice` / `promotionText` aus DOM-Elementen der Produktkachel
- `offerStart`/`offerEnd` bleiben null (kein Zeitraum in der Seitenstruktur verfügbar)

---

## Produkt-Properties

| Field | Billa | Penny | Lidl | Hofer | SPAR | MPreis |
|-------|:-----:|:-----:|:----:|:-----:|:----:|:------:|
| `price` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `unitPrice` | ~ | ~ | ~ | ~ | ~ | ~ |
| `unitLabel` | ~ | ~ | ~ | ~ | ~ | ~ |
| `brand` | ~ | ~ | ~ | ~ | ~ | ~ |
| `amount` | ~ | ~ | ✗ | ✓ | ~ | ~ |
| `sku` | ✓ | ✓ | ✓ | ~ | ~ | ✓ |
| `imageUrl` | ✓ | ✓ | ✓ | ~ | ~ | ~ |
| `productUrl` | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ |

### Quellen der `productUrl`

| Scraper | URL-Quelle | Beispiel |
|---------|-----------|---------|
| Billa | `product.slug` aus API | `https://shop.billa.at/produkte/ja-natuerlich-bio-apfel-00-0-001` |
| Penny | `product.slug` aus API | `https://www.penny.at/produkte/rewe-bio-apfel-00-0-001` |
| Lidl | `canonicalPath` aus API | `https://www.lidl.at/p/favorina-mini-ostersortiment/p10045677` |
| SPAR | `href`-Attribut des Tile-Links | `https://www.spar.at/produktwelt/spar-premium-bio-apfel-2020005521308` |
| MPreis | `href`-Attribut der Produktkachel | `https://www.mpreis.at/shop/p/m-bio-bio-gurken-541601` |
| Hofer | – | immer `null` |
