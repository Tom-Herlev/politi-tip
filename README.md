# Politi Tip

En installérbar webapp (PWA) til tablet og telefon, der samler offentlige operative hændelser på et kort og i en liste. Du kan hakke de politikredse af, du er interesseret i, filtrere på kategori og tidsrum, se afstand med «Nær mig», og selv tilføje uofficielle tips.

Når appen er lagt på GitHub Pages, opdaterer den sig selv: nye hændelser hentes typisk hvert 5. minut, og den åbne app tjekker efter nyt hvert 2. minut og når du vender tilbage til den. Akutlægehelikoptere forsøges desuden hentet direkte i browseren hvert 20. sekund (hvis adsb.lol tillader det; ellers følger de datafeedet).

## Kilder

- **POLITI UPDATE** – de 12 politikredses officielle meddelelser (RSS fra via.ritzau.dk).
- **ODIN 112-puls** (Beredskabsstyrelsen) – `http://www.odin.dk/RSS/RSS.aspx?beredskabsID=0000`. ODIN angiver kun brandstationen, ikke en adresse. Udrykninger vises derfor som et omtrentligt område omkring stationen. Hver hændelse er kildeangivet med link til [www.odin.dk/112puls](http://www.odin.dk/112puls/), som krævet. Rutineopgaver (eftersyn, forespørgsler, prøver) er skjult som standard.
- **Vejdirektoratet** – offentlige trafikmeldinger fra `https://storage.googleapis.com/trafikkort-data/geojson/big-screen-events.json` (uheld, spærringer, kø, tabt gods, havari), inkl. forventet åbningstid når den findes.
- **Green Power Denmark / Elnet** – aktuelle strømafbrud fra `https://api.elnet.greenpowerdenmark.dk/api/incidents`, vist som et område med antal berørte kunder og elselskab.
- **DMI-varsler** – `https://www.dmi.dk/dmidk_byvejrWS/rest/json/Danmark/DK/WarningAreas` (samme API som dmi.dk). Hvis DMI ikke har aktive varsler, bruges [MeteoAlarm](https://feeds.meteoalarm.org/api/v1/warnings/feeds-denmark) som reserve.
- **Akutlægehelikoptere** – live position og kurs via [adsb.lol](https://api.adsb.lol/v2/lat/56.0/lon/10.0/dist/250), når en af de danske H135/H145 (Norsk Luftambulanse) er i luften over Danmark. Der er fire baser (Skive, Billund, Ringsted, Saltum) og en reservehelikopter.

Appen skraber ikke Facebook eller Instagram.

## Læg appen online (GitHub Pages)

Du skal bruge en **GitHub-konto**. Derefter, på en computer hvor du er logget ind:

1. Opret et nyt, gerne **offentligt** lager (repository), fx `politi-tip`. Offentlige lagre har gratis Actions-minutter. Private lagre har et månedligt loft.
2. Læg indholdet af denne mappe op i lageret. Hvis du har GitHub CLI (`gh`) og er logget ind (`gh auth login`):

   ```bash
   cd politi-tip
   gh repo create politi-tip --public --source=. --remote=origin --push
   ```

   Alternativt: opret lageret på [github.com/new](https://github.com/new), og kør:

   ```bash
   cd politi-tip
   git remote add origin https://github.com/DIT-BRUGERNAVN/politi-tip.git
   git push -u origin main
   ```

3. Åbn lageret på GitHub → **Settings** → **Pages** → **Build and deployment** → **Source:** *GitHub Actions*.
4. Åbn fanen **Actions** og kør workflowet **Opdater data og udgiv** manuelt første gang (*Run workflow*), eller vent på den planlagte kørsel.
5. Når kørslen er færdig, får du en adresse typisk i denne form:

   `https://DIT-BRUGERNAVN.github.io/politi-tip/`

GitHub Actions kører `refresh.py` hvert 5. minut (det er den korteste cron, GitHub tillader). Er der ingen nye politimeddelelser, genbruges de, mens de øvrige kilder stadig opdateres. På den gratis plan kan GitHub forsinke de planlagte kørsler lidt; derfor tjekker appen også selv.

## Installer appen på tabletten

Åbn appens webadresse i Safari (iPad) eller Chrome (Android):

**iPad / iPhone (Safari)**  
Del → **Føj til hjemmeskærm** → tilføj. Appen åbner bagefter som et selvstændigt ikon med navnet Politi Tip.

**Android (Chrome)**  
Menu (tre prikker) → **Tilføj til startskærm** / **Installer app**.

Når appen er åben, vises tidspunktet for sidste dataopdatering (dansk tid) og hvornår appen sidst tjekkede. Den henter `data.json` igen hvert 2. minut og når du vender tilbage til appen. Du kan bruge den offline med de senest hentede hændelser.

Nødnumrene 112, 114, Giftlinjen og lægevagten pr. region ligger øverst og kan trykkes direkte.

## Kør lokalt

```bash
cd politi-tip
python3 refresh.py
python3 -m http.server 8080
```

Åbn [http://127.0.0.1:8080](http://127.0.0.1:8080). Åbn ikke filen som `file://` — så kan `data.json` og service workeren ikke indlæses.

## Begrænsninger

- ODIN giver kun brandstationen. Kortet viser et omtrentligt område, ikke en præcis nål.
- Geokodning af politimeddelelser er et bedste bud ud fra fritekst. Nogle meddelelser har intet sted og får ingen nål.
- adsb.lol sender (november 2026) ikke CORS-headers, så live-opdatering af helikoptere i browseren kan fejle; så vises seneste position fra datafeedet (opdateres typisk hvert 5. minut).
- Dette er ikke en officiel polititjeneste og erstatter ikke 112 eller 114.
- Nogle officielle meddelelser nævner efterlysninger med navn eller alder. Appen viser den offentlige tekst og linker til kilden.
- På iPad kræves Safari for «Føj til hjemmeskærm». Chrome på iOS kan ikke installere PWA’er på samme måde.
