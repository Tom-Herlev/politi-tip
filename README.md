# Politi Tip

En installérbar webapp (PWA), der samler offentlige operative meddelelser fra de 12 danske politikredse på et kort og i en liste. Du kan hakke de kredse af, du er interesseret i, og selv tilføje uofficielle tips (fx et link eller en tekst fra en Facebook- eller Instagram-gruppe).

Når appen er lagt på GitHub Pages, opdaterer den sig selv: nye hændelser hentes typisk hvert 5. minut, og den åbne app tjekker efter nyt hvert 2. minut og når du vender tilbage til den.

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

GitHub Actions kører `refresh.py` hvert 5. minut (det er den korteste cron, GitHub tillader). Hvis der ikke er nye meddelelser, stopper scriptet hurtigt og committer ingenting. Er der nyt, opdateres `data.json` og siden udgives igen. På den gratis plan kan GitHub forsinke de planlagte kørsler lidt; derfor tjekker appen også selv.

## Installer appen på tabletten

Åbn appens webadresse i Safari (iPad) eller Chrome (Android):

**iPad / iPhone (Safari)**  
Del → **Føj til hjemmeskærm** → tilføj. Appen åbner bagefter som et selvstændigt ikon med navnet Politi Tip.

**Android (Chrome)**  
Menu (tre prikker) → **Tilføj til startskærm** / **Installer app**.

Når appen er åben, vises tidspunktet for sidste dataopdatering (dansk tid) og hvornår appen sidst tjekkede. Den henter `data.json` igen hvert 2. minut og når du vender tilbage til appen.

## Kør lokalt

```bash
cd politi-tip
python3 refresh.py
python3 -m http.server 8080
```

Åbn [http://127.0.0.1:8080](http://127.0.0.1:8080). Åbn ikke filen som `file://` — så kan `data.json` og service workeren ikke indlæses.

## Sådan opdateres data

`refresh.py` (køres af GitHub Actions hvert 5. minut, eller manuelt):

1. Henter de 12 officielle POLITI UPDATE-RSS-feeds.
2. Stopper med det samme, hvis intet er nyere end sidste `data.json`.
3. Ellers samler det opdateringer af samme sag, henter fuld tekst (genbruger `.cache/`), klassificerer, geokoder og skriver `data.json`.

Geokodning bruger [Adressevælgeren](https://adressevaelger.dk) (Klimadatastyrelsens erstatning for DAWA, som lukkede 1. oktober 2026) med den officielle fælles token `adressevaelger123`, og Nominatim som reserve. Cachen i `.cache/` er lagt i lageret og gemmes også mellem Actions-kørsler, så opdateringerne forbliver korte.

**CORS:** POLITI UPDATE-feedet (`via.ritzau.dk/rss/...`) sender ikke `Access-Control-Allow-Origin`. En ren klientløsning, der læste RSS direkte i tabletten, er derfor ikke mulig med det nuværende API. Data skal stadig hentes af `refresh.py` og udgives som `data.json`.

## Hvorfor POLITI UPDATE og ikke X?

I januar 2026 gik politiet over til [POLITI UPDATE](https://politiupdate.dk). De 12 politikredses X-konti er verificeret og er **ikke længere aktive** – de er sat til beskyttet og henviser selv til POLITI UPDATE.

| Politikreds | Handle |
|---|---|
| Københavns Politi | @KobenhavnPoliti |
| Københavns Vestegns Politi | @VestegnsPoliti |
| Nordsjællands Politi | @NSJPoliti |
| Midt- og Vestsjællands Politi | @MVSJPoliti |
| Sydsjællands og Lolland-Falsters Politi | @SSJ_LFPoliti |
| Fyns Politi | @FynsPoliti |
| Syd- og Sønderjyllands Politi | @SjylPoliti |
| Sydøstjyllands Politi | @SydOjylPoliti |
| Midt- og Vestjyllands Politi | **@MVJPoliti** (ikke det parodiske @MidtVestPoliti) |
| Østjyllands Politi | @OjylPoliti |
| Nordjyllands Politi | @NjylPoliti |
| Bornholms Politi | **@BornholmsPoliti** (ikke @BornholmPoliti, som ikke findes) |

Appen skraber ikke Facebook eller Instagram.

## Begrænsninger

- Geokodning er et bedste bud ud fra fritekst. Nogle meddelelser har intet sted og får ingen nål.
- Dette er ikke en officiel polititjeneste og erstatter ikke 112 eller 114.
- Nogle officielle meddelelser nævner efterlysninger med navn eller alder. Appen viser den offentlige tekst og linker til kilden.
- På iPad kræves Safari for «Føj til hjemmeskærm». Chrome på iOS kan ikke installere PWA’er på samme måde.
