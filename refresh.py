#!/usr/bin/env python3
"""Hent officielle POLITI UPDATE-meddelelser, klassificér, geokod og skriv data.json.

Kør fra /workspace/politi-tip:

    python3 refresh.py

Et rutinekald hvert 10–15. minut skal gøre præcis det: køre scriptet i denne
mappe, så data.json overskrives. Appen læser filen ved indlæsning (og via
et diskret 'Opdater'-klik). Facebook og Instagram skrames ikke.

Officielle politikonti på X er lukkede/beskyttede (november 2026) og kan
derfor ikke hentes. Den officielle erstatning er POLITI UPDATE-RSS.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache"
ARTICLE_CACHE = CACHE / "articles"
GEO_CACHE_PATH = CACHE / "geocode.json"
DATA_PATH = ROOT / "data.json"
USER_AGENT = "PolitiTip/1.0 (personligt hændelseskort; +https://politiupdate.dk)"
AV_TOKEN = "adressevaelger123"  # officiel fælles token, jf. KDS
NOMINATIM = "https://nominatim.openstreetmap.org/search"
AV_SOEG = "https://adressevaelger.dk/husnumre/soeg"
AV_HUS = "https://adressevaelger.dk/husnumre/{id}"

DISTRICTS: list[dict[str, Any]] = [
    {
        "id": "koebenhavn",
        "name": "Københavns Politi",
        "short": "Storkøbenhavn",
        "handle": "KobenhavnPoliti",
        "publisher_id": "90685",
        "default_on": True,
        "places": [
            "København", "Frederiksberg", "Tårnby", "Dragør", "Amager",
            "Valby", "Vanløse", "Brønshøj", "Husum", "Østerbro", "Nørrebro",
            "Vesterbro", "Christianshavn", "Sundby", "Kastrup", "København K",
            "København V", "København Ø", "København N", "København S",
            "København NV",
        ],
    },
    {
        "id": "vestegnen",
        "name": "Københavns Vestegns Politi",
        "short": "Vestegnen",
        "handle": "VestegnsPoliti",
        "publisher_id": "90718",
        "default_on": True,
        "places": [
            "Albertslund", "Ballerup", "Brøndby", "Glostrup", "Gladsaxe",
            "Herlev", "Hvidovre", "Høje-Taastrup", "Høje Taastrup", "Taastrup",
            "Ishøj", "Rødovre", "Vallensbæk", "Skovlunde", "Buddinge",
            "Søborg", "Bagsværd",
        ],
    },
    {
        "id": "nordsjaelland",
        "name": "Nordsjællands Politi",
        "short": "Nordsjælland",
        "handle": "NSJPoliti",
        "publisher_id": "90719",
        "default_on": True,
        "places": [
            "Allerød", "Egedal", "Fredensborg", "Frederikssund", "Furesø",
            "Gentofte", "Gribskov", "Halsnæs", "Helsingør", "Hillerød",
            "Hørsholm", "Lyngby-Taarbæk", "Lyngby", "Kongens Lyngby",
            "Taarbæk", "Rudersdal", "Birkerød", "Holte", "Vedbæk",
            "Farum", "Værløse", "Ølstykke", "Stenløse", "Helsinge",
            "Gilleleje", "Hundested", "Frederiksværk", "Hørsholm",
        ],
    },
    {
        "id": "midtvestsjaelland",
        "name": "Midt- og Vestsjællands Politi",
        "short": "Midt- og Vestsjælland",
        "handle": "MVSJPoliti",
        "publisher_id": "13562881",
        "default_on": False,
        "places": [
            "Greve", "Holbæk", "Kalundborg", "Køge", "Lejre", "Odsherred",
            "Ringsted", "Roskilde", "Solrød", "Stevns", "Nykøbing Sj",
            "Nykøbing Sjælland", "Asnæs", "Hvalsø", "Viby Sj", "Tune",
            "Sejerø", "Annebergparken",
        ],
    },
    {
        "id": "sydsjaelland",
        "name": "Sydsjællands og Lolland-Falsters Politi",
        "short": "Sydsjælland og Lolland-Falster",
        "handle": "SSJ_LFPoliti",
        "publisher_id": "90594",
        "default_on": False,
        "places": [
            "Næstved", "Vordingborg", "Faxe", "Haslev", "Lolland", "Falster",
            "Guldborgsund", "Nykøbing F", "Nykøbing Falster", "Nakskov",
            "Maribo", "Sakskøbing", "Rødby", "Nysted", "Stege", "Præstø",
            "Store Heddinge", "Rønnede",
        ],
    },
    {
        "id": "fyn",
        "name": "Fyns Politi",
        "short": "Fyn",
        "handle": "FynsPoliti",
        "publisher_id": "90797",
        "default_on": False,
        "places": [
            "Odense", "Svendborg", "Nyborg", "Middelfart", "Faaborg", "Fåborg",
            "Assens", "Kerteminde", "Ringe", "Nørre Aaby", "Bogense",
            "Langeland", "Ærø", "Rudkøbing", "Marstal", "Fyn",
        ],
    },
    {
        "id": "sydsonderjylland",
        "name": "Syd- og Sønderjyllands Politi",
        "short": "Syd- og Sønderjylland",
        "handle": "SjylPoliti",
        "publisher_id": "90686",
        "default_on": False,
        "places": [
            "Esbjerg", "Haderslev", "Sønderborg", "Tønder", "Varde", "Vejen",
            "Aabenraa", "Åbenrå", "Fanø", "Vojens", "Rødekro", "Padborg",
            "Kruså", "Gråsten", "Nordborg", "Augustenborg", "Skærbæk",
            "Bramming", "Ribe", "Ølgod",
        ],
    },
    {
        "id": "sydostjylland",
        "name": "Sydøstjyllands Politi",
        "short": "Sydøstjylland",
        "handle": "SydOjylPoliti",
        "publisher_id": "90720",
        "default_on": False,
        "places": [
            "Vejle", "Kolding", "Fredericia", "Horsens", "Hedensted",
            "Billund", "Give", "Egtved", "Juelsminde", "Gedved", "Børkop",
        ],
    },
    {
        "id": "midtvestjylland",
        "name": "Midt- og Vestjyllands Politi",
        "short": "Midt- og Vestjylland",
        "handle": "MVJPoliti",
        "publisher_id": "90687",
        "default_on": False,
        "places": [
            "Ikast", "Brande", "Ikast-Brande", "Silkeborg", "Ringkøbing",
            "Skjern", "Ringkøbing-Skjern", "Herning", "Holstebro", "Viborg",
            "Skive", "Lemvig", "Struer", "Thisted", "Morsø", "Nykøbing Mors",
            "Hurup", "Kjellerup", "Karup", "Videbæk",
        ],
    },
    {
        "id": "ostjylland",
        "name": "Østjyllands Politi",
        "short": "Østjylland",
        "handle": "OjylPoliti",
        "publisher_id": "90721",
        "default_on": False,
        "places": [
            "Aarhus", "Århus", "Randers", "Norddjurs", "Syddjurs", "Favrskov",
            "Odder", "Samsø", "Grenaa", "Grenå", "Ebeltoft", "Hadsten",
            "Hinnerup", "Hammel", "Skanderborg", "Viby J", "Risskov",
            "Åbyhøj", "Brabrand", "Tilst", "Lystrup", "Højbjerg",
        ],
    },
    {
        "id": "nordjylland",
        "name": "Nordjyllands Politi",
        "short": "Nordjylland",
        "handle": "NjylPoliti",
        "publisher_id": "13562880",
        "default_on": False,
        "places": [
            "Aalborg", "Ålborg", "Frederikshavn", "Læsø", "Hjørring",
            "Brønderslev", "Jammerbugt", "Vesthimmerland", "Mariagerfjord",
            "Rebild", "Skagen", "Sæby", "Nørresundby", "Støvring",
            "Hobro", "Aars", "Fjerritslev", "Brovst", "Vodskov",
        ],
    },
    {
        "id": "bornholm",
        "name": "Bornholms Politi",
        "short": "Bornholm",
        "handle": "BornholmsPoliti",
        "publisher_id": "90799",
        "default_on": False,
        "places": [
            "Bornholm", "Rønne", "Nexø", "Neksø", "Aakirkeby", "Åkirkeby",
            "Hasle", "Allinge", "Gudhjem", "Svaneke", "Pedersker", "Dueodde",
        ],
    },
]

DISTRICT_BY_ID = {d["id"]: d for d in DISTRICTS}
DISTRICT_BY_PUBLISHER = {d["publisher_id"]: d for d in DISTRICTS}
DISTRICT_BY_NAME = {d["name"]: d for d in DISTRICTS}

# Syd, vest, nord, øst — omtrentlige kredsgrænser til at afvise forkerte nåle
BBOX = {
    "koebenhavn": (55.58, 12.40, 55.78, 12.72),
    "vestegnen": (55.58, 12.10, 55.78, 12.52),
    "nordsjaelland": (55.70, 11.80, 56.16, 12.65),
    "midtvestsjaelland": (55.15, 10.85, 55.98, 12.40),
    "sydsjaelland": (54.50, 10.85, 55.45, 12.55),
    "fyn": (54.70, 9.60, 55.65, 10.95),
    "sydsonderjylland": (54.73, 8.05, 55.80, 9.95),
    "sydostjylland": (55.30, 9.10, 56.00, 10.20),
    "midtvestjylland": (55.65, 8.05, 57.20, 9.85),
    "ostjylland": (55.80, 9.65, 56.65, 10.90),
    "nordjylland": (56.50, 8.05, 57.80, 11.35),
    "bornholm": (54.94, 14.63, 55.32, 15.26),
}

GENERIC_PLACES = {
    "danmark", "jylland", "sjælland", "fyn", "bornholm", "midtjylland",
    "syddanmark", "hovedstaden", "nordjylland", "østjylland", "vestjylland",
    "sønderjylland", "nordsjælland", "region", "landet", "hele landet",
}

PLACE_ALIASES = {
    "ryomård": "Ryomgård",
    "øresundsmotorvej": "Øresundsmotorvejen, Tårnby",
    "djurslandsmotorvejen": "Djurslandsmotorvejen, Aarhus",
    "djurslandsmotorvej": "Djurslandsmotorvejen, Aarhus",
    "aarhus syd motorvejen": "Aarhus Syd Motorvejen",
}


PLACE_STOP = {
    "forbindelse", "perioden", "periode", "dag", "nat", "morges", "eftermiddag",
    "aftes", "formiddag", "gang", "behold", "live", "gang", "øjeblikket",
    "nordlig", "sydlig", "østlig", "vestlig", "retning", "begge", "sider",
    "området", "nærheden", "en", "et", "den", "det", "de", "der", "som",
    "mod", "vedkommende", "sagen", "politiet", "beredskabet", "offentligheden",
    "grundlovsforhør", "retten", "sociale", "medier", "weekenden", "aften",
}

STREET_RE = re.compile(
    r"\b("
    r"[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+(?:\s+[A-ZÆØÅ]?[a-zæøå\-]+)*"
    r"(?:vej|gade|allé|alle|plads|boulevard|stræde|torv|vænget|toften|"
    r"bakken|engen|krogen|ageren|marken|lund|højen|dalen|bro|porten|"
    r"passage|stien|kaj|havn|terrasset|anlæg|parken|have)"
    r"(?:\s+\d+[A-Za-z]?)?"
    r")\b",
    re.UNICODE,
)

MOTORWAY_RE = re.compile(
    r"\b("
    r"E\s?\d{1,3}"
    r"|Øresundsmotorvejen|Øresundsmotorvej"
    r"|Sydmotorvejen|Sydmotorvej"
    r"|Holbækmotorvejen|Holbækmotorvej"
    r"|Hillerødmotorvejen|Hillerødmotorvej"
    r"|Helsingørmotorvejen|Helsingørmotorvej"
    r"|Køge Bugt Motorvejen|Køge Bugt-motorvejen"
    r"|Aarhus Syd Motorvejen|Århus Syd Motorvejen"
    r"|Djurslandsmotorvejen|Djurslandsmotorvej"
    r"|Messemotorvejen|Messemotorvej"
    r"|Motorring\s?[0-9]"
    r"|motorvejen(?:\s+ved\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]+)?"
    r")\b",
    re.IGNORECASE,
)

IN_PLACE_RE = re.compile(
    r"\b(?:i|på|ved|fra|over|under|nær|omkring)\s+"
    r"([A-ZÆØÅ][A-Za-zÆØÅæøå\-]*(?:\s+(?:og|&)\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]*)?"
    r"(?:\s+[A-ZÆØÅ][A-Za-zÆØÅæøå\-]*){0,3})"
    r"(?:\s+kommune)?",
    re.UNICODE,
)

BRAND_KW = ("brand", "ildebrand", "røgudvikling", "røg fra", "eksplosion", "brændt")
REDNING_KW = ("drukne", "redning", "bjærg", "i vandet", "omkommet i", "ambulance")
FAERDSEL_KW = (
    "færdselsuheld", "færdselsuheld", "fuh", "påkørsel", "motorvej", "vognbane",
    "glat føre", "spærret", "afspær", "trafik", "bilist", "personbil",
    "lastbil", "uheld", "hastighed", "indkørselsforbud", "afkørsel",
)
POLITI_KW = (
    "knivstik", "knivstikkeri", "røveri", "anhold", "efterlys", "indbrud",
    "sigtelse", "mistænkel", "hærværk", "vold", "skud", "demonstration",
    "savnet", "bortgået", "fremstilles", "undersøger", "politiet arbejder",
    "narkotika", "bedrageri", "eftersøg", "identificere",
)
ANDET_PRESS_KW = (
    "grundlovsforhør", "idømt", "dømt for", "straksdom", "skyldskendelse",
    "holder lukket", "døgnrapport udkommer", "bevillings", "pressemeddelelse",
)


def log(msg: str) -> None:
    print(msg, flush=True)


def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_get_retries(url: str, retries: int = 3, timeout: int = 30) -> bytes:
    last: Exception | None = None
    for i in range(retries):
        try:
            return http_get(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.6 * (i + 1))
    raise last  # type: ignore[misc]


def strip_html(html: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"[ \t]+", " ", text).strip()



def _has_kw(text: str, kws: tuple[str, ...]) -> bool:
    for k in kws:
        if " " in k or "-" in k:
            if k in text:
                return True
        elif re.search(rf"\b{re.escape(k)}", text):
            return True
    return False


def classify(title: str, body: str) -> str:
    t = f"{title} {body}".lower()
    # Ordsgrænse, så "brandvæsen" ikke bliver til typen brand
    is_brand = bool(re.search(r"\b(brand|branden|brande|ildebrand|røgudvikling|eksplosion|brændt)\b", t) or "røg fra" in t)
    is_faerdsel = _has_kw(t, FAERDSEL_KW)
    is_redning = _has_kw(t, ("drukne", "redning", "i vandet", "omkommet i", "ambulance"))
    if is_brand:
        return "brand"
    if is_redning and not is_faerdsel:
        return "redning"
    if is_faerdsel:
        return "faerdsel"
    if _has_kw(t, ANDET_PRESS_KW) and not _has_kw(t, POLITI_KW):
        return "andet"
    if _has_kw(t, POLITI_KW):
        return "politi"
    if _has_kw(t, ANDET_PRESS_KW):
        return "andet"
    return "andet"


def parse_rss_date(value: str) -> str | None:
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(value.replace("GMT", "+0000"), fmt if "%z" in fmt else "%a, %d %b %Y %H:%M:%S %z")
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    try:
        dt = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def rss_items(district: dict[str, Any]) -> list[dict[str, Any]]:
    url = f"https://via.ritzau.dk/rss/short-messages/latest?publisherId={district['publisher_id']}"
    raw = http_get_retries(url)
    root = ET.fromstring(raw)
    out: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        link = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        pub = parse_rss_date((item.findtext("pubDate") or "").strip())
        m = re.search(r"/pressemeddelelse/(\d+)", link)
        sm = re.search(r"#sm-(\d+)", link)
        if not m:
            continue
        out.append(
            {
                "thread_id": m.group(1),
                "message_id": sm.group(1) if sm else m.group(1),
                "title": title,
                "url": link.split("#")[0],
                "published_at": pub,
                "district": district["id"],
            }
        )
    return out


def decode_initial_state(html: str) -> dict[str, Any] | None:
    m = re.search(r"window\.__INITIAL_STATE__ = '([^']+)'", html)
    if not m:
        return None
    raw = m.group(1)
    try:
        decoded = urllib.parse.unquote(base64.b64decode(raw).decode("utf-8"))
        return json.loads(decoded)
    except Exception:  # noqa: BLE001
        return None


def fetch_thread(thread_id: str, min_published: str | None = None) -> dict[str, Any] | None:
    ARTICLE_CACHE.mkdir(parents=True, exist_ok=True)
    path = ARTICLE_CACHE / f"{thread_id}.json"
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched = cached.get("fetched_at") or ""
            if fetched and (not min_published or fetched >= min_published):
                return cached
        except Exception:  # noqa: BLE001
            pass
    url = f"https://via.ritzau.dk/pressemeddelelse/{thread_id}?lang=da"
    try:
        html = http_get_retries(url, timeout=25).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        log(f"  kunne ikke hente {thread_id}: {exc}")
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None
    state = decode_initial_state(html)
    if not state:
        return None
    release = (state.get("release") or {}).get(thread_id) or {}
    items = release.get("items") or []
    parsed: list[dict[str, Any]] = []
    for it in items:
        meta = it.get("metadata") or {}
        versions = it.get("versions") or []
        ver = next((v for v in versions if v.get("language") == "da"), versions[0] if versions else {})
        body_html = ((ver.get("body") or {}).get("complete")) or ""
        parsed.append(
            {
                "id": str(meta.get("id") or thread_id),
                "title": ver.get("title") or meta.get("title") or "",
                "body_html": body_html,
                "body": strip_html(body_html),
                "published_at": meta.get("publicationDate") or meta.get("lastEdited"),
                "publisher_id": str(meta.get("publisherId") or ""),
                "publisher_name": (meta.get("publisherName") or (meta.get("publisher") or {}).get("name") or ""),
                "url": "https://via.ritzau.dk" + (ver.get("url") or f"/pressemeddelelse/{thread_id}?lang=da"),
            }
        )
    parsed.sort(key=lambda x: x.get("published_at") or "")
    result = {"thread_id": thread_id, "items": parsed, "fetched_at": datetime.now(timezone.utc).isoformat()}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def latest_item(thread: dict[str, Any]) -> dict[str, Any] | None:
    items = thread.get("items") or []
    return items[-1] if items else None


def extract_locations(title: str, body: str, district_id: str) -> list[str]:
    text = f"{title}. {body}".replace("\n", " ")
    found: list[str] = []

    def add(candidate: str) -> None:
        c = re.sub(r"\s+", " ", candidate).strip(" .,;:!?")
        c = re.sub(r"^(den|det|de|en|et)\s+", "", c, flags=re.I)
        if len(c) < 3 or len(c) > 60:
            return
        key = c.casefold()
        if key in PLACE_STOP or any(key == s or key.startswith(s + " ") for s in PLACE_STOP):
            return
        if any(c.casefold() == x.casefold() for x in found):
            return
        found.append(c)

    for m in STREET_RE.finditer(text):
        raw = m.group(1)
        # Undgå at hele overskrifter som "Opfølgning … – Frederiksborggade" bliver ét vejnavn
        if " - " in raw or " – " in raw or len(raw) > 40:
            for part in re.split(r"\s+[-–]\s+", raw):
                if STREET_RE.search(part) and len(part) <= 40:
                    add(part)
        else:
            add(raw)
    for m in MOTORWAY_RE.finditer(text):
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        # try to attach a nearby place (ved X / mellem X)
        tail = text[m.end() : m.end() + 80]
        near = re.search(r"\b(?:ved|mellem afkørsel[^,]*,?|afkørsel[^,]*,)\s*([A-ZÆØÅ][A-Za-zÆØÅæøå\-]+)", tail)
        if near:
            add(f"{raw} {near.group(1)}")
        else:
            add(raw)
    for m in IN_PLACE_RE.finditer(text):
        add(m.group(1))

    district = DISTRICT_BY_ID.get(district_id)
    if district:
        for place in district["places"]:
            if re.search(rf"\b{re.escape(place)}\b", text, re.I):
                add(place)

    for m in re.finditer(r"\b([A-ZÆØÅ][A-Za-zÆØÅæøå]+)(?:afkørslen|afkørsel)\b", text):
        add(m.group(1))

    streets = [x for x in found if STREET_RE.search(x)]
    motorways = [x for x in found if MOTORWAY_RE.search(x)]
    towns = [
        x for x in found
        if x not in streets and x not in motorways and x.casefold() not in GENERIC_PLACES
    ]
    combined: list[str] = []
    if streets and towns:
        combined.append(f"{streets[0]} {towns[0]}")
    if motorways and towns:
        combined.append(f"{motorways[0]} {towns[0]}")
    if district:
        head_place = district["places"][0]
        for item in list(found):
            if re.search(r"skole|storcenter|station|sygehus|hospital|havn", item, re.I):
                if head_place.casefold() not in item.casefold():
                    combined.append(f"{item} {head_place}")
    ordered: list[str] = []
    for q in combined + found:
        alias = PLACE_ALIASES.get(q.casefold())
        if alias:
            ordered.append(alias)
        if q.casefold() in GENERIC_PLACES:
            continue
        ordered.append(q)
    seen: set[str] = set()
    out: list[str] = []
    for q in ordered:
        k = q.casefold()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


def utm32n_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    a = 6378137.0
    f = 1 / 298.257222101
    k0 = 0.9996
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    x = easting - 500000.0
    y = northing
    m = y / k0
    mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
    phi1 = (
        mu
        + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
        + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
        + (151 * e1**3 / 96) * math.sin(6 * mu)
        + (1097 * e1**4 / 512) * math.sin(8 * mu)
    )
    sinp, cosp, tanp = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sinp**2)
    t1 = tanp**2
    c1 = ep2 * cosp**2
    r1 = a * (1 - e2) / (1 - e2 * sinp**2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tanp / r1) * (
        d**2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
    )
    lon = math.radians(9.0) + (
        d
        - (1 + 2 * t1 + c1) * d**3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
    ) / cosp
    return math.degrees(lat), math.degrees(lon)


_geo_cache: dict[str, Any] = {}
_nominatim_last = 0.0


def load_geo_cache() -> None:
    global _geo_cache
    if GEO_CACHE_PATH.exists():
        try:
            _geo_cache = json.loads(GEO_CACHE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            _geo_cache = {}


def save_geo_cache() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    GEO_CACHE_PATH.write_text(json.dumps(_geo_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def cache_key(query: str, district_id: str) -> str:
    return hashlib.sha1(f"v3|{district_id}|{query.casefold()}".encode()).hexdigest()


def in_district(lat: float, lon: float, district_id: str) -> bool:
    box = BBOX.get(district_id)
    if not box:
        return True
    south, west, north, east = box
    pad = 0.08
    return (south - pad) <= lat <= (north + pad) and (west - pad) <= lon <= (east + pad)


def av_search(tekst: str) -> list[dict[str, Any]]:
    qs = urllib.parse.urlencode({"tekst": tekst, "token": AV_TOKEN})
    try:
        data = json.loads(http_get_retries(f"{AV_SOEG}?{qs}", timeout=20).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"  adressevælger-fejl for {tekst!r}: {exc}")
        return []
    return data.get("fund") or []


def av_lookup_husnummer(hid: str) -> dict[str, Any] | None:
    try:
        data = json.loads(http_get_retries(AV_HUS.format(id=hid) + f"?token={AV_TOKEN}", timeout=20).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"  husnummer-opslag-fejl {hid}: {exc}")
        return None
    return data.get("husnummer")


def score_hit(hit: dict[str, Any], query: str, district_id: str) -> int:
    titel = (hit.get("titel") or "").casefold()
    vej = (hit.get("vejnavn") or "").casefold()
    post = (hit.get("postdistrikt") or "").casefold()
    q = query.casefold()
    score = 0
    if vej and vej in q:
        score += 8
    if any(w and w in titel for w in q.split() if len(w) > 3):
        score += 3
    district = DISTRICT_BY_ID.get(district_id)
    if district:
        for p in district["places"]:
            if p.casefold() in titel or p.casefold() in post:
                score += 6
                break
    if hit.get("type") == "husnummer":
        score += 2
    return score


def geocode_adressevaelger(query: str, district_id: str) -> dict[str, Any] | None:
    hits = av_search(query)
    if not hits and " " in query:
        # By-navn i samme streng kan give 0 hits; prøv første led (ofte vejnavn)
        hits = av_search(query.split()[0])
    if not hits:
        return None
    hits = sorted(hits, key=lambda h: score_hit(h, query, district_id), reverse=True)
    best = hits[0]
    typ = (best.get("type") or "").lower()
    hid = None
    label = best.get("titel") or query
    if typ == "husnummer":
        hid = best.get("id")
    elif typ in {"navngivenvejpostnummer", "navngivenvej"}:
        # Slå et husnummer op på vejen, så vi får koordinater
        vej = best.get("vejnavn") or query
        postnr = best.get("postnr") or ""
        more = av_search(f"{vej} {postnr}".strip())
        hus = next((h for h in more if (h.get("type") or "").lower() == "husnummer"), None)
        if hus:
            hid = hus.get("id")
            label = hus.get("titel") or label
    if not hid:
        return None
    hus = av_lookup_husnummer(hid)
    if not hus:
        return None
    coords = ((hus.get("adgangspunkt") or {}).get("koordinater")) or {}
    if "x" not in coords or "y" not in coords:
        return None
    lat, lon = utm32n_to_wgs84(float(coords["x"]), float(coords["y"]))
    betegnelse = hus.get("adgangsadressebetegnelse") or label
    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "label": betegnelse,
        "source": "adressevaelger",
        "query": query,
    }


def geocode_nominatim(query: str, district_id: str | None = None) -> dict[str, Any] | None:
    global _nominatim_last
    wait = 1.05 - (time.time() - _nominatim_last)
    if wait > 0:
        time.sleep(wait)
    params = {
        "q": f"{query}, Danmark",
        "format": "json",
        "limit": "3",
        "countrycodes": "dk",
        "addressdetails": "0",
    }
    box = BBOX.get(district_id or "")
    if box:
        south, west, north, east = box
        # Nominatim viewbox: lon_left,lat_top,lon_right,lat_bottom
        params["viewbox"] = f"{west},{north},{east},{south}"
        params["bounded"] = "0"
    url = NOMINATIM + "?" + urllib.parse.urlencode(params)
    try:
        _nominatim_last = time.time()
        data = json.loads(http_get_retries(url, timeout=20).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log(f"  nominatim-fejl for {query!r}: {exc}")
        return None
    for hit in data or []:
        lat, lon = float(hit["lat"]), float(hit["lon"])
        if district_id and not in_district(lat, lon, district_id):
            continue
        label = hit.get("display_name") or query
        # Afvis lands-/regionspins
        low = label.casefold()
        if low in {"danmark", "denmark"} or low.startswith("region "):
            continue
        return {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "label": label,
            "source": "nominatim",
            "query": query,
        }
    return None


def looks_like_street(query: str) -> bool:
    return bool(STREET_RE.search(query))


def geocode(query: str, district_id: str) -> dict[str, Any] | None:
    key = cache_key(query, district_id)
    if key in _geo_cache:
        cached = _geo_cache[key]
        if cached and not in_district(cached["lat"], cached["lon"], district_id):
            pass  # forkast gammel, forkert nål
        else:
            return cached
    result = None
    if looks_like_street(query) or re.search(r"\d", query):
        result = geocode_adressevaelger(query, district_id)
        if result and not in_district(result["lat"], result["lon"], district_id):
            result = None
        if not result:
            result = geocode_nominatim(query, district_id)
    else:
        result = geocode_nominatim(query, district_id)
        if not result:
            result = geocode_adressevaelger(query, district_id)
            if result and not in_district(result["lat"], result["lon"], district_id):
                result = None
    _geo_cache[key] = result
    return result


def geocode_best(queries: list[str], district_id: str) -> tuple[str | None, dict[str, Any] | None]:
    first_text = queries[0] if queries else None
    for q in queries:
        geo = geocode(q, district_id)
        if geo:
            return q, geo
    return first_text, None


def iso_to_z(value: str | None) -> str | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return value


def build_incident(thread: dict[str, Any], district_id: str, rss_fallback: dict[str, Any]) -> dict[str, Any]:
    latest = latest_item(thread) if thread else None
    title = (latest or {}).get("title") or rss_fallback.get("title") or ""
    body = (latest or {}).get("body") or ""
    url = (latest or {}).get("url") or rss_fallback.get("url")
    published = iso_to_z((latest or {}).get("published_at") or rss_fallback.get("published_at"))
    items = (thread or {}).get("items") or []
    first_pub = iso_to_z(items[0]["published_at"]) if items else published
    typ = classify(title, body)
    queries = extract_locations(title, body, district_id)
    location_text, geo = geocode_best(queries, district_id)
    inc: dict[str, Any] = {
        "id": f"pu-{(thread or {}).get('thread_id') or rss_fallback.get('thread_id')}",
        "source": "politiupdate",
        "source_label": "POLITI UPDATE",
        "district": district_id,
        "district_name": DISTRICT_BY_ID[district_id]["name"],
        "type": typ,
        "title": title,
        "text": body,
        "location_text": location_text,
        "lat": geo["lat"] if geo else None,
        "lon": geo["lon"] if geo else None,
        "geocode_label": geo["label"] if geo else None,
        "geocode_source": geo["source"] if geo else None,
        "published_at": first_pub or published,
        "updated_at": published,
        "url": url,
        "update_count": max(1, len(items) or 1),
        "official": True,
    }
    return inc


def main() -> None:
    started = datetime.now(timezone.utc)
    CACHE.mkdir(parents=True, exist_ok=True)
    ARTICLE_CACHE.mkdir(parents=True, exist_ok=True)
    load_geo_cache()

    log("Henter RSS fra 12 politikredse…")
    all_rss: list[dict[str, Any]] = []
    for d in DISTRICTS:
        try:
            items = rss_items(d)
            log(f"  {d['name']}: {len(items)} poster")
            all_rss.extend(items)
        except Exception as exc:  # noqa: BLE001
            log(f"  FEJL {d['name']}: {exc}")

    # Unikke tråde – vi henter den officielle side og får hele historikken
    by_thread: dict[str, dict[str, Any]] = {}
    for it in all_rss:
        tid = it["thread_id"]
        prev = by_thread.get(tid)
        if not prev or (it.get("published_at") or "") > (prev.get("published_at") or ""):
            by_thread[tid] = it
    log(f"Unikke hændelser: {len(by_thread)} (fra {len(all_rss)} RSS-poster)")

    newest_rss = max((it.get("published_at") or "") for it in all_rss) if all_rss else ""
    feeds_ok = sum(1 for d in DISTRICTS if any(it["district"] == d["id"] for it in all_rss))
    if DATA_PATH.exists() and newest_rss and feeds_ok == len(DISTRICTS):
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            prev = existing.get("newest_rss") or ""
            if not prev:
                inc = existing.get("incidents") or []
                prev = max((i.get("updated_at") or i.get("published_at") or "") for i in inc) if inc else (existing.get("generated_at") or "")
            if prev and newest_rss <= prev:
                elapsed = round((datetime.now(timezone.utc) - started).total_seconds(), 1)
                log(f"Ingen nye meddelelser (nyeste RSS {newest_rss} ≤ {prev}). data.json er uændret. {elapsed}s")
                return
        except Exception as exc:  # noqa: BLE001
            log(f"Kunne ikke sammenligne med eksisterende data.json ({exc}) — kører fuld opdatering.")

    threads: dict[str, dict[str, Any]] = {}
    log("Henter fuld tekst for hver hændelse…")
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {
            pool.submit(fetch_thread, tid, (by_thread[tid].get("published_at") or "")): tid
            for tid in by_thread
        }
        for i, fut in enumerate(as_completed(futs), 1):
            tid = futs[fut]
            try:
                threads[tid] = fut.result() or {"thread_id": tid, "items": []}
            except Exception as exc:  # noqa: BLE001
                log(f"  tråd {tid} fejlede: {exc}")
                threads[tid] = {"thread_id": tid, "items": []}
            if i % 15 == 0 or i == len(futs):
                log(f"  {i}/{len(futs)}")

    log("Klassificerer og geokoder…")
    incidents: list[dict[str, Any]] = []
    for tid, rss in by_thread.items():
        inc = build_incident(threads.get(tid) or {}, rss["district"], rss)
        incidents.append(inc)

    incidents.sort(key=lambda x: x.get("updated_at") or x.get("published_at") or "", reverse=True)
    save_geo_cache()

    pinned = sum(1 for i in incidents if i.get("lat") is not None)
    by_dist: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for i in incidents:
        by_dist[i["district"]] = by_dist.get(i["district"], 0) + 1
        by_type[i["type"]] = by_type.get(i["type"], 0) + 1

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_copenhagen": datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds"),
        "newest_rss": newest_rss,
        "source": "POLITI UPDATE (via.ritzau.dk RSS + artikelsider)",
        "note": (
            "De 12 politikredses officielle X-konti er ikke længere aktive "
            "og er sat til beskyttet. Operative meddelelser hentes derfor "
            "fra POLITI UPDATE, som politiet selv henviser til. "
            "Facebook og Instagram skrames ikke."
        ),
        "handles": [
            {
                "district": d["id"],
                "name": d["name"],
                "handle": d["handle"],
                "status": "inaktiv_og_beskyttet",
            }
            for d in DISTRICTS
        ],
        "districts": [
            {
                "id": d["id"],
                "name": d["name"],
                "short": d["short"],
                "handle": d["handle"],
                "default_on": d["default_on"],
                "count": by_dist.get(d["id"], 0),
            }
            for d in DISTRICTS
        ],
        "stats": {
            "rss_items": len(all_rss),
            "incidents": len(incidents),
            "with_coordinates": pinned,
            "without_coordinates": len(incidents) - pinned,
            "by_type": by_type,
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        },
        "incidents": incidents,
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"Skrev {DATA_PATH} — {len(incidents)} hændelser, {pinned} med kortnål, "
        f"{payload['stats']['elapsed_seconds']}s"
    )
    for d in DISTRICTS:
        log(f"  {d['name']}: {by_dist.get(d['id'], 0)}")
    log(f"Typer: {by_type}")


if __name__ == "__main__":
    main()
