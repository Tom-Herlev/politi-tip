#!/usr/bin/env python3
"""Hent offentlige hændelser og skriv data.json til Politi Tip.

Kør fra mappen:

    python3 refresh.py

Kilder: POLITI UPDATE, ODIN 112-puls, Vejdirektoratet, Green Power Denmark
(strømafbrud), DMI-varsler (plus MeteoAlarm som reserve) og adsb.lol for
de danske akutlægehelikoptere. Facebook og Instagram skrames ikke.
"""

from __future__ import annotations

import base64
import hashlib
import html
import http.client
import json
import math
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
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


def http_get(url: str, timeout: int = 30, force_ip: str | None = None) -> bytes:
    if not force_ip:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    if parsed.scheme == "https":
        raw = socket.create_connection((force_ip, port), timeout=timeout)
        ctx = ssl.create_default_context()
        sock = ctx.wrap_socket(raw, server_hostname=host)
        conn = http.client.HTTPSConnection(host, port=port, timeout=timeout)
        conn.sock = sock
    else:
        conn = http.client.HTTPConnection(force_ip, port=port, timeout=timeout)
    try:
        conn.request("GET", path, headers={
            "Host": host,
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        })
        resp = conn.getresponse()
        data = resp.read()
        if resp.status >= 400:
            raise OSError(f"HTTP {resp.status} {resp.reason} for {url}")
        return data
    finally:
        conn.close()


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


def district_for_point(lat: float, lon: float) -> str | None:
    hits = []
    for did, box in BBOX.items():
        south, west, north, east = box
        if south <= lat <= north and west <= lon <= east:
            hits.append(did)
    if not hits:
        # lidt slæk, hvis punktet ligger lige uden for boksen
        hits = [did for did in BBOX if in_district(lat, lon, did)]
    if not hits:
        return None

    def area(did: str) -> float:
        south, west, north, east = BBOX[did]
        return (north - south) * (east - west)

    return min(hits, key=area)


def as_cph_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Europe/Copenhagen"))
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_dk_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = html.unescape(value).strip()
    m = re.match(
        r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})(?:\s*(?:kl\.?)?\s*(\d{1,2})[:.](\d{2})(?::(\d{2}))?)?",
        text,
        re.IGNORECASE,
    )
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hour = int(m.group(4) or 0)
        minute = int(m.group(5) or 0)
        second = int(m.group(6) or 0)
        try:
            return datetime(year, month, day, hour, minute, second, tzinfo=ZoneInfo("Europe/Copenhagen"))
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Europe/Copenhagen"))
        return dt
    except ValueError:
        return None


def geocode_anywhere(query: str) -> dict[str, Any] | None:
    """Geokod et sted i Danmark uden at kræve en politikreds."""
    key = hashlib.sha1(f"v4|dk|{query.casefold()}".encode()).hexdigest()
    if key in _geo_cache:
        return _geo_cache[key]
    result = None
    try:
        result = geocode_nominatim(query, None)
    except Exception as exc:  # noqa: BLE001
        log(f"  geocode_anywhere nominatim {query!r}: {exc}")
    if not result:
        try:
            result = geocode_adressevaelger(query, "")
        except Exception as exc:  # noqa: BLE001
            log(f"  geocode_anywhere adressevælger {query!r}: {exc}")
    _geo_cache[key] = result
    return result


def _base_incident(
    *,
    ident: str,
    category: str,
    typ: str,
    title: str,
    text: str,
    source: str,
    source_label: str,
    source_url: str,
    published_at: str | None,
    updated_at: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    location_text: str | None = None,
    radius_m: float | None = None,
    approximate: bool = False,
    district: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if district is None and lat is not None and lon is not None:
        district = district_for_point(lat, lon)
    district_name = DISTRICT_BY_ID[district]["name"] if district and district in DISTRICT_BY_ID else None
    inc: dict[str, Any] = {
        "id": ident,
        "category": category,
        "type": typ,
        "title": title,
        "text": text,
        "source": source,
        "source_label": source_label,
        "source_url": source_url,
        "url": source_url,
        "published_at": published_at,
        "updated_at": updated_at or published_at,
        "lat": lat,
        "lon": lon,
        "location_text": location_text,
        "geometry": "circle" if radius_m else "point",
        "radius_m": radius_m,
        "approximate": approximate,
        "district": district,
        "district_name": district_name,
        "official": True,
        "nationwide": district is None,
    }
    if extra:
        inc.update(extra)
    return inc


# --- ODIN 112-puls (Beredskabsstyrelsen) ---

ODIN_RSS = "http://www.odin.dk/RSS/RSS.aspx?beredskabsID=0000"
ODIN_PAGE = "http://www.odin.dk/112puls/"
ODIN_IP = "5.56.147.39"
ODIN_ROUTINE = re.compile(
    r"\b(isl-forespørgsel|forespørgsel|eftersyn|isl-eftersyn|springtæppe|"
    r"prøve|øvelse|ovelse|rutin|kontrol|afprøvning|service)\b",
    re.IGNORECASE,
)


def http_get_odin(url: str, timeout: int = 30) -> bytes:
    try:
        return http_get(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        log(f"  ODIN via DNS fejlede ({exc}); prøver {ODIN_IP}")
        return http_get(url, timeout=timeout, force_ip=ODIN_IP)


def is_odin_routine(melding: str) -> bool:
    return bool(ODIN_ROUTINE.search(melding or ""))


def fetch_odin() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {
        "ok": False,
        "count": 0,
        "endpoint": ODIN_RSS,
        "error": None,
    }
    try:
        raw = http_get_odin(ODIN_RSS, timeout=25)
        root = ET.fromstring(raw)
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)
        log(f"  ODIN fejlede: {exc}")
        return [], status

    items: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        beredskab = html.unescape((item.findtext("title") or "").strip())
        desc = html.unescape((item.findtext("description") or "").strip())
        pub = (item.findtext("pubDate") or "").strip()
        comments = (item.findtext("comments") or "").strip()
        melding, station = "", ""
        m = re.search(r"Førstemelding:\s*(.*?)\s+Station:\s*(.*)$", desc, re.IGNORECASE | re.DOTALL)
        if m:
            melding = re.sub(r"\s+", " ", m.group(1)).strip()
            station = re.sub(r"\s+", " ", m.group(2)).strip()
        else:
            melding = desc
        published = None
        try:
            published = as_cph_iso(parsedate_to_datetime(pub))
        except Exception:
            published = as_cph_iso(parse_dk_datetime(comments)) or iso_to_z(pub)
        routine = is_odin_routine(melding)
        geo = None
        queries = []
        if station:
            queries = [
                f"{station} brandstation",
                f"brandstation {station}",
                f"{station} beredskab",
                station,
            ]
            if beredskab:
                queries.insert(2, f"{station}, {beredskab}")
        for q in queries:
            geo = geocode_anywhere(q)
            if geo:
                break
        title = melding or "Udrykning"
        if station:
            title = f"{melding} – {station}" if melding else station
        ident = "odin-" + hashlib.sha1(
            f"{beredskab}|{station}|{melding}|{published or pub}".encode()
        ).hexdigest()[:16]
        text_parts = []
        if beredskab:
            text_parts.append(f"Beredskab: {beredskab}.")
        if station:
            text_parts.append(
                f"Station: {station}. ODIN angiver kun brandstationen, ikke en præcis adresse."
            )
        if melding:
            text_parts.append(f"Første melding: {melding}.")
        inc = _base_incident(
            ident=ident,
            category="brand",
            typ="redning" if re.search(r"redning|assistance|fuh|trafik", melding, re.I) and not re.search(r"brand", melding, re.I) else "brand",
            title=title,
            text=" ".join(text_parts),
            source="odin",
            source_label="ODIN 112-puls",
            source_url=ODIN_PAGE,
            published_at=published,
            lat=geo["lat"] if geo else None,
            lon=geo["lon"] if geo else None,
            location_text=(f"{station} (omtrentligt område omkring stationen)" if station else beredskab),
            radius_m=2000 if geo else None,
            approximate=True,
            extra={
                "routine": routine,
                "station": station,
                "beredskab": beredskab,
                "first_message": melding,
                "attribution": "Kilde: www.odin.dk/112puls",
            },
        )
        items.append(inc)
    status["ok"] = True
    status["count"] = len(items)
    log(f"  ODIN: {len(items)} alarmer")
    return items, status


# --- Vejdirektoratet ---

VD_EVENTS = "https://storage.googleapis.com/trafikkort-data/geojson/big-screen-events.json"
VD_CRITICAL = "https://storage.googleapis.com/trafikkort-data/geojson/critical-announcements.json"
VD_PAGE = "https://trafikkort.vejdirektoratet.dk/"

VD_INCLUDE_LAYERS = {
    "current-queue.point",
    "current-roadblocks.point",
    "current-blocking-events.point",
}
VD_INCLUDE_TYPES = {
    "org.vd.trafficmap.datexii.v32.datamodel.Accident",
    "org.vd.trafficmap.datexii.v32.datamodel.AbnormalTraffic",
    "org.vd.trafficmap.datexii.v32.datamodel.RoadOrCarriagewayOrLaneManagement",
    "org.vd.trafficmap.datexii.v32.datamodel.VehicleObstruction",
}
VD_KEYWORDS = (
    "uheld", "spærret", "spærring", "tabt gods", "havari", "havareret",
    "kø,", "kø ", "kø.", "køen", "ulykke", "påkørsel", "blokering",
)


def vd_subtype(layer: str, typ: str, text: str) -> str:
    low = text.lower()
    if "tabt gods" in low:
        return "tabt gods"
    if "queue" in layer or "kø" in low or typ.endswith("AbnormalTraffic"):
        return "kø"
    if "roadblock" in layer or "blocking" in layer or "spær" in low:
        return "spærring"
    if typ.endswith("Accident") or "uheld" in low or "ulykke" in low:
        return "uheld"
    if "havari" in low:
        return "havari"
    return "trafik"


def _iter_vd_features(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if isinstance(payload, list):
        for coll in payload:
            if not isinstance(coll, dict):
                continue
            layer = coll.get("layerName") or ""
            for feat in coll.get("features") or []:
                out.append((layer, feat))
    elif isinstance(payload, dict):
        layer = payload.get("layerName") or ""
        for feat in payload.get("features") or []:
            out.append((layer, feat))
    return out


def fetch_vejdirektoratet() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {"ok": False, "count": 0, "endpoint": VD_EVENTS, "error": None}
    try:
        raw = http_get_retries(VD_EVENTS, timeout=25)
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)
        log(f"  Vejdirektoratet fejlede: {exc}")
        return [], status

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for layer, feat in _iter_vd_features(payload):
        props = feat.get("properties") or {}
        if str(props.get("suspended", "false")).lower() == "true":
            continue
        typ = props.get("TrafficMan2_Type") or ""
        header = html.unescape(strip_html(props.get("header") or props.get("title") or "Trafikmelding"))
        desc = html.unescape(strip_html(props.get("description") or ""))
        blob = f"{header} {desc} {layer} {typ}".lower()
        include = layer in VD_INCLUDE_LAYERS or typ in VD_INCLUDE_TYPES or any(k in blob for k in VD_KEYWORDS)
        if not include:
            continue
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        lon = lat = None
        if geom.get("type") == "Point" and len(coords) >= 2:
            lon, lat = float(coords[0]), float(coords[1])
        fid = str(props.get("featureId") or header)
        if fid in seen:
            continue
        seen.add(fid)
        begin = parse_dk_datetime(props.get("beginPeriod"))
        end = parse_dk_datetime(props.get("endPeriod"))
        inserted = props.get("lastModifiedString") or props.get("dateInsertedInListString")
        updated = as_cph_iso(parse_dk_datetime(inserted) if inserted and "T" not in str(inserted) else None)
        if not updated and inserted:
            updated = iso_to_z(str(inserted))
        published = as_cph_iso(begin) or updated
        subtype = vd_subtype(layer, typ, f"{header} {desc}")
        title = header
        reopening = None
        if props.get("endPeriod"):
            reopening = html.unescape(str(props["endPeriod"]))
        inc = _base_incident(
            ident="vd-" + hashlib.sha1(fid.encode()).hexdigest()[:16],
            category="trafik",
            typ="faerdsel",
            title=title,
            text=desc,
            source="vejdirektoratet",
            source_label="Vejdirektoratet",
            source_url=VD_PAGE,
            published_at=published,
            updated_at=updated or published,
            lat=round(lat, 6) if lat is not None else None,
            lon=round(lon, 6) if lon is not None else None,
            location_text=header,
            extra={
                "subtype": subtype,
                "reopening": reopening,
                "reopening_at": as_cph_iso(end),
                "ongoing": True,
                "layer": layer,
            },
        )
        items.append(inc)
    status["ok"] = True
    status["count"] = len(items)
    log(f"  Vejdirektoratet: {len(items)} hændelser")
    return items, status


# --- Strømafbrud, Green Power Denmark ---

GPD_INCIDENTS = "https://api.elnet.greenpowerdenmark.dk/api/incidents"
GPD_PAGE = "https://elnet.dk/"


def fetch_outages() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {"ok": False, "count": 0, "endpoint": GPD_INCIDENTS, "error": None}
    try:
        raw = http_get_retries(GPD_INCIDENTS, timeout=30)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("uventet svarformat")
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)
        log(f"  Strømafbrud fejlede: {exc}")
        return [], status

    now = datetime.now(ZoneInfo("Europe/Copenhagen"))
    items: list[dict[str, Any]] = []
    for rec in payload:
        start = parse_dk_datetime(rec.get("startDate"))
        end = parse_dk_datetime(rec.get("endDate"))
        exp = parse_dk_datetime(rec.get("expectedDowntime"))
        typ = rec.get("incidentType") or ""
        lat, lon = rec.get("centerLat"), rec.get("centerLng")
        if lat is None or lon is None:
            continue
        if end and end < now:
            continue
        if start and start > now:
            # planlagte fremtidige arbejder vises ikke som aktuelle afbrud
            continue
        if start:
            age_h = (now - start.astimezone(now.tzinfo)).total_seconds() / 3600
        else:
            created = parse_dk_datetime(rec.get("created"))
            age_h = (now - created.astimezone(now.tzinfo)).total_seconds() / 3600 if created else 9999
        # expectedDowntime opdateres ofte ikke, når strømmen er tilbage;
        # vis derfor kun nylige uvarslede, og varslede/planlagte der stadig er i vinduet.
        typ_l = typ
        still_expected = exp is not None and exp >= now
        if typ_l == "Uvarslet":
            if age_h > 18:
                continue
        elif typ_l in {"Varslet", "Planlagt"}:
            if not still_expected and age_h > 4:
                continue
            if age_h > 48:
                continue
        else:
            if age_h > 12 and not still_expected:
                continue
        customers = rec.get("effectedCustomers") or rec.get("poweroutagesCount") or 0
        radius = rec.get("radius") or 100
        try:
            radius = float(radius)
        except (TypeError, ValueError):
            radius = 100
        radius = max(100, min(radius, 25000))
        title = rec.get("title") or "Strømafbrud"
        utility = rec.get("supplierName") or "Netselskab"
        comment = (rec.get("comment") or rec.get("cause") or "").strip()
        text = f"{customers} kunder berørt. Elselskab: {utility}."
        if typ:
            text += f" Type: {typ}."
        if comment:
            short = re.sub(r"\s+", " ", comment)
            text += " " + short[:400]
        expected = rec.get("expectedDowntime")
        inc = _base_incident(
            ident=f"gpd-{rec.get('id')}",
            category="strom",
            typ="andet",
            title=title,
            text=text,
            source="elnet",
            source_label="Green Power Denmark / Elnet",
            source_url=GPD_PAGE,
            published_at=as_cph_iso(start) or as_cph_iso(parse_dk_datetime(rec.get("created"))),
            updated_at=as_cph_iso(parse_dk_datetime(rec.get("created"))) or as_cph_iso(start),
            lat=round(float(lat), 6),
            lon=round(float(lon), 6),
            location_text=title.replace("Afbrud i ", "").replace("Afbrud ", ""),
            radius_m=radius,
            approximate=True,
            extra={
                "customers": int(customers) if customers is not None else None,
                "utility": utility,
                "utility_phone": rec.get("supplierPhone"),
                "utility_web": rec.get("supplierWeb"),
                "outage_type": typ,
                "expected_back": expected,
                "ongoing": True,
            },
        )
        items.append(inc)
    status["ok"] = True
    status["count"] = len(items)
    log(f"  Strømafbrud: {len(items)} aktuelle")
    return items, status


# --- DMI-varsler (+ MeteoAlarm som reserve) ---

DMI_OVERVIEW = "https://www.dmi.dk/dmidk_byvejrWS/rest/json/Danmark/DK/WarningOverview"
DMI_AREAS = "https://www.dmi.dk/dmidk_byvejrWS/rest/json/Danmark/DK/WarningAreas"
DMI_VARSEL = "https://www.dmi.dk/dmidk_byvejrWS/rest/json/Danmark/DK/varsel"
DMI_PAGE = "https://www.dmi.dk/varsler"
METEOALARM = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-denmark"

# Omtrentlige midterpunkter for MeteoAlarm EMMA-områder i Danmark
EMMA_CENTROIDS = {
    "DK001": (55.67, 12.48),  # København / hovedstaden
    "DK002": (55.12, 14.92),  # Bornholm
    "DK003": (55.70, 11.90),  # Nordsjælland
    "DK004": (55.40, 11.70),  # Sjælland
    "DK005": (54.85, 11.50),  # Lolland-Falster
    "DK006": (55.35, 10.40),  # Fyn
    "DK007": (55.40, 9.30),   # Sydjylland
    "DK008": (56.20, 9.50),   # Midtjylland
    "DK801": (57.05, 9.90),   # Nordjylland / Vendsyssel
    "DK802": (56.80, 8.70),
    "DK803": (56.40, 8.60),
    "DK804": (56.15, 8.20),
    "DK805": (55.70, 8.50),
    "DK806": (55.50, 8.80),
    "DK807": (55.25, 9.40),
    "DK808": (55.90, 9.80),
    "DK809": (56.15, 10.20),
    "DK810": (56.45, 10.00),
    "DK811": (56.70, 10.00),
    "DK812": (55.55, 10.00),
    "DK813": (54.95, 10.60),
    "DK814": (55.20, 11.20),
    "DK815": (55.00, 12.00),
    "DK816": (55.60, 12.10),
    "DK817": (55.75, 12.30),
    "DK818": (55.95, 12.40),
    "DK819": (56.00, 12.00),
    "DK820": (54.70, 11.70),
}


def _walk_warnings(node: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            out.extend(_walk_warnings(item))
        return out
    if not isinstance(node, dict):
        return out
    keys = {k.lower() for k in node}
    interesting = keys & {
        "text", "title", "headline", "category", "type", "areaname", "area",
        "validfrom", "validto", "from", "to", "warningtype", "description",
    }
    if interesting and ("text" in keys or "title" in keys or "headline" in keys or "description" in keys):
        out.append(node)
    for k, v in node.items():
        if k.lower() in {"warningactual", "warnings", "warning5days", "sections", "areas", "items"}:
            out.extend(_walk_warnings(v))
        elif isinstance(v, (list, dict)) and k.lower() not in {"icons", "widget"}:
            # nested, but avoid double-adding the current node children if already added
            if not interesting:
                out.extend(_walk_warnings(v))
    return out


def _warning_coords(rec: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    for key in ("lat", "latitude", "centerLat", "center_lat"):
        if rec.get(key) is not None and rec.get("lon") or rec.get("lng") or rec.get("longitude") or rec.get("centerLng"):
            lat = rec.get(key)
            lon = rec.get("lon") or rec.get("lng") or rec.get("longitude") or rec.get("centerLng")
            try:
                return float(lat), float(lon), None
            except (TypeError, ValueError):
                pass
    # polygons?
    for key in ("polygon", "polygons", "geometry", "coordinates", "area"):
        val = rec.get(key)
        pts = []
        if isinstance(val, list):
            def collect(a):
                if isinstance(a, (list, tuple)) and len(a) >= 2 and isinstance(a[0], (int, float)):
                    # lon,lat or lat,lon – DMI often lat,lon. Heuristic: DK lon is 8-15, lat 54-58
                    x, y = float(a[0]), float(a[1])
                    if 54 <= x <= 58 and 7 <= y <= 16:
                        pts.append((x, y))
                    elif 54 <= y <= 58 and 7 <= x <= 16:
                        pts.append((y, x))
                elif isinstance(a, (list, tuple)):
                    for b in a:
                        collect(b)
            collect(val)
        if pts:
            lat = sum(p[0] for p in pts) / len(pts)
            lon = sum(p[1] for p in pts) / len(pts)
            return lat, lon, 40000
    return None, None, None


def fetch_dmi_warnings() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {
        "ok": False,
        "count": 0,
        "endpoint": DMI_AREAS,
        "error": None,
        "fallback": None,
    }
    items: list[dict[str, Any]] = []
    overview = areas = varsel = None
    try:
        overview = json.loads(http_get_retries(DMI_OVERVIEW, timeout=20).decode("utf-8"))
        areas = json.loads(http_get_retries(DMI_AREAS, timeout=20).decode("utf-8"))
        varsel = json.loads(http_get_retries(DMI_VARSEL, timeout=20).decode("utf-8"))
        status["ok"] = True
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)
        log(f"  DMI-varsler fejlede: {exc}")

    recs: list[dict[str, Any]] = []
    if isinstance(overview, dict) and overview.get("warnings"):
        recs.extend(_walk_warnings(overview["warnings"]))
        max_cat = overview.get("maxCategory")
        if overview.get("text") and max_cat not in (None, 0, "0"):
            recs.append({"text": overview.get("text"), "category": max_cat, "title": "DMI-varsel"})
    if isinstance(areas, dict):
        recs.extend(_walk_warnings(areas.get("warningActual") or []))
    if isinstance(varsel, dict):
        if varsel.get("headline") or (varsel.get("sections")):
            recs.extend(_walk_warnings(varsel))

    seen_txt: set[str] = set()
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        title = rec.get("title") or rec.get("headline") or rec.get("type") or rec.get("warningType") or "DMI-varsel"
        text = rec.get("text") or rec.get("description") or rec.get("comment") or ""
        if isinstance(text, list):
            text = " ".join(str(x) for x in text)
        title = str(title).strip()
        text = str(text).strip()
        if not title and not text:
            continue
        key = f"{title}|{text[:120]}"
        if key in seen_txt:
            continue
        seen_txt.add(key)
        cat = rec.get("category") or rec.get("maxCategory")
        area_name = rec.get("areaName") or rec.get("area") or rec.get("name")
        if isinstance(area_name, dict):
            area_name = area_name.get("name") or area_name.get("areaDesc")
        lat, lon, rad = _warning_coords(rec)
        if lat is None:
            # landsdækkende eller uden geometri
            lat, lon, rad = 56.0, 10.4, 180000
            nationwide = True
        else:
            nationwide = False
        start = parse_dk_datetime(str(rec.get("validFrom") or rec.get("from") or rec.get("onset") or ""))
        end = parse_dk_datetime(str(rec.get("validTo") or rec.get("to") or rec.get("expires") or ""))
        loc = str(area_name) if area_name else "Danmark"
        inc = _base_incident(
            ident="dmi-" + hashlib.sha1(key.encode()).hexdigest()[:16],
            category="vejr",
            typ="andet",
            title=str(title),
            text=text or str(title),
            source="dmi",
            source_label="DMI",
            source_url=DMI_PAGE,
            published_at=as_cph_iso(start),
            updated_at=as_cph_iso(end) or as_cph_iso(start),
            lat=round(lat, 6),
            lon=round(lon, 6),
            location_text=loc,
            radius_m=rad or 50000,
            approximate=True,
            extra={
                "warning_category": cat,
                "valid_to": as_cph_iso(end),
                "ongoing": True,
                "nationwide": nationwide,
            },
        )
        inc["nationwide"] = nationwide
        if nationwide:
            inc["district"] = None
            inc["district_name"] = None
        items.append(inc)

    # MeteoAlarm som reserve, når DMI ikke har aktive varsler
    if not items:
        try:
            malarm = json.loads(http_get_retries(METEOALARM, timeout=20).decode("utf-8"))
            warnings = malarm.get("warnings") or malarm.get("data") or []
            real = 0
            for wrap in warnings:
                alert = wrap.get("alert") if isinstance(wrap, dict) else None
                if not alert:
                    continue
                ident = str(alert.get("identifier") or "")
                if "NOWARNING" in ident.upper():
                    continue
                infos = alert.get("info") or []
                info = None
                for cand in infos:
                    lang = (cand.get("language") or "").lower()
                    if lang.startswith("da"):
                        info = cand
                        break
                info = info or (infos[0] if infos else {})
                level = ""
                for p in info.get("parameter") or []:
                    if p.get("valueName") == "awareness_level":
                        level = p.get("value") or ""
                desc = (info.get("description") or "")
                if "ingen aktive" in desc.lower():
                    continue
                if "green" in level.lower() and "minor" in level.lower() and "ingen" in desc.lower():
                    continue
                event = info.get("event") or "DMI-varsel"
                areaspec = []
                emma = []
                for area in info.get("area") or []:
                    areaspec.append(area.get("areaDesc") or "")
                    for g in area.get("geocode") or []:
                        if g.get("valueName") == "EMMA_ID":
                            emma.append(g.get("value"))
                loc = ", ".join(a for a in areaspec if a and a.lower() != "all areas") or "Danmark"
                if emma and emma[0] in EMMA_CENTROIDS and loc != "Danmark":
                    lat, lon = EMMA_CENTROIDS[emma[0]]
                    rad = 40000
                    nationwide = False
                elif len(emma) >= 8 or loc == "Danmark":
                    lat, lon, rad = 56.0, 10.4, 180000
                    nationwide = True
                else:
                    pts = [EMMA_CENTROIDS[e] for e in emma if e in EMMA_CENTROIDS]
                    if pts:
                        lat = sum(p[0] for p in pts) / len(pts)
                        lon = sum(p[1] for p in pts) / len(pts)
                        rad = 50000
                        nationwide = False
                    else:
                        lat, lon, rad = 56.0, 10.4, 180000
                        nationwide = True
                onset = parse_dk_datetime(info.get("onset")) or parse_dk_datetime(alert.get("sent"))
                expires = parse_dk_datetime(info.get("expires"))
                inc = _base_incident(
                    ident="meteo-" + hashlib.sha1((ident or event + desc[:80]).encode()).hexdigest()[:16],
                    category="vejr",
                    typ="andet",
                    title=event,
                    text=desc,
                    source="dmi",
                    source_label="DMI / MeteoAlarm",
                    source_url=info.get("web") or DMI_PAGE,
                    published_at=as_cph_iso(onset),
                    updated_at=as_cph_iso(expires) or as_cph_iso(onset),
                    lat=round(lat, 6),
                    lon=round(lon, 6),
                    location_text=loc,
                    radius_m=rad,
                    approximate=True,
                    extra={
                        "warning_category": level,
                        "valid_to": as_cph_iso(expires),
                        "ongoing": True,
                        "nationwide": nationwide,
                    },
                )
                inc["nationwide"] = nationwide
                if nationwide:
                    inc["district"] = None
                    inc["district_name"] = None
                items.append(inc)
                real += 1
            status["fallback"] = METEOALARM
            status["ok"] = True
            log(f"  MeteoAlarm: {real} aktive varsler (DMI havde ingen)")
        except Exception as exc:  # noqa: BLE001
            log(f"  MeteoAlarm fejlede: {exc}")
            if not status["ok"]:
                status["error"] = (status.get("error") or "") + f"; MeteoAlarm: {exc}"

    status["count"] = len(items)
    if status["ok"]:
        log(f"  DMI-varsler: {len(items)}")
    return items, status


# --- Akutlægehelikoptere via adsb.lol ---

ADSB_POINT = "https://api.adsb.lol/v2/lat/56.0/lon/10.0/dist/250"
ADSB_REG = "https://api.adsb.lol/v2/reg/{reg}"
ADSB_PAGE = "https://adsb.lol/"

# Fire baser + en reservehelikopter (H135/H145, Norsk Luftambulanse).
# Registreringer roterer; vi slår op på kendte LN-OU*/LN-OT* og viser dem,
# der er i dansk luftrum.
HEMS_REGS = [
    "LN-OUD", "LN-OUE", "LN-OUF", "LN-OUG", "LN-OUH",
    "LN-OUI", "LN-OUJ", "LN-OUK", "LN-OUL", "LN-OUM",
    "LN-OTQ", "LN-OTP", "LN-OTO", "LN-OTR",
]
HEMS_TYPES = {"EC35", "EC45", "H135", "H145", "E135", "E145"}
HEMS_BASES = [
    {"name": "Skive", "lat": 56.5503, "lon": 9.1728},
    {"name": "Billund", "lat": 55.7403, "lon": 9.1518},
    {"name": "Ringsted", "lat": 55.4258, "lon": 11.8067},
    {"name": "Saltum", "lat": 57.2725, "lon": 9.6958},
]
DK_BOX = (54.45, 7.7, 57.9, 15.4)  # south, west, north, east


def _in_denmark(lat: float, lon: float) -> bool:
    s, w, n, e = DK_BOX
    return s <= lat <= n and w <= lon <= e


def _is_hems_ac(ac: dict[str, Any]) -> bool:
    reg = (ac.get("r") or "").replace(" ", "").upper()
    typ = (ac.get("t") or "").upper()
    flight = (ac.get("flight") or "").strip().upper()
    if typ in HEMS_TYPES and (reg.startswith("LN-OU") or reg.startswith("LN-OT") or flight.startswith("DOC") or flight.startswith("NLA")):
        return True
    if reg in {r.replace(" ", "").upper() for r in HEMS_REGS} or reg in HEMS_REGS:
        return True
    return False


def fetch_hems() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    status: dict[str, Any] = {"ok": False, "count": 0, "endpoint": ADSB_POINT, "error": None, "cors": False}
    aircraft: list[dict[str, Any]] = []
    try:
        raw = http_get_retries(ADSB_POINT, timeout=20)
        payload = json.loads(raw.decode("utf-8"))
        aircraft = payload.get("ac") or []
        status["ok"] = True
    except Exception as exc:  # noqa: BLE001
        status["error"] = str(exc)
        log(f"  adsb.lol fejlede: {exc}")
        return [], [], status

    items: list[dict[str, Any]] = []
    fleet: list[dict[str, Any]] = []
    seen_regs: set[str] = set()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ac in aircraft:
        if not _is_hems_ac(ac):
            continue
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue
        if not _in_denmark(float(lat), float(lon)):
            continue
        reg = (ac.get("r") or "").strip() or (ac.get("hex") or "ukendt")
        if reg in seen_regs:
            continue
        seen_regs.add(reg)
        typ = ac.get("t") or ""
        flight = (ac.get("flight") or "").strip()
        alt = ac.get("alt_baro") or ac.get("alt_geom")
        airborne = alt not in (None, "ground", 0, "0")
        track = ac.get("track") or ac.get("true_heading") or ac.get("mag_heading")
        speed = ac.get("gs")
        title = f"Akutlægehelikopter {reg}"
        if flight:
            title += f" ({flight})"
        bits = []
        if airborne:
            bits.append("I luften.")
        else:
            bits.append("På jorden / lav højde.")
        if typ:
            bits.append(f"Type: {typ}.")
        if alt not in (None, "ground"):
            bits.append(f"Højde: {alt} ft.")
        if speed:
            bits.append(f"Fart: {speed} kt.")
        if track is not None:
            bits.append(f"Kurs: {track}°.")
        inc = _base_incident(
            ident=f"hems-{reg}",
            category="helikopter",
            typ="redning",
            title=title,
            text=" ".join(bits),
            source="adsb",
            source_label="adsb.lol",
            source_url=ADSB_PAGE,
            published_at=now,
            updated_at=now,
            lat=round(float(lat), 6),
            lon=round(float(lon), 6),
            location_text="Live position" if airborne else "Seneste position",
            extra={
                "registration": reg,
                "callsign": flight or None,
                "aircraft_type": typ,
                "track": track,
                "altitude_ft": alt if alt != "ground" else 0,
                "speed_kt": speed,
                "airborne": bool(airborne),
                "hex": ac.get("hex"),
                "ongoing": True,
            },
        )
        items.append(inc)
        fleet.append({
            "registration": reg,
            "callsign": flight or None,
            "lat": inc["lat"],
            "lon": inc["lon"],
            "track": track,
            "altitude_ft": inc["altitude_ft"],
            "speed_kt": speed,
            "airborne": bool(airborne),
            "type": typ,
            "updated_at": now,
        })
    status["count"] = len(items)
    log(f"  Akutlægehelikoptere i luften over DK: {len(items)}")
    return items, fleet, status


def annotate_police(incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for inc in incidents:
        inc.setdefault("category", "politi")
        inc.setdefault("source_url", inc.get("url") or "https://politiupdate.dk")
        inc.setdefault("geometry", "point")
        inc.setdefault("approximate", False)
        inc.setdefault("routine", False)
        inc.setdefault("nationwide", False)
        if not inc.get("source_label"):
            inc["source_label"] = "POLITI UPDATE"
    return incidents



def main() -> None:
    started = datetime.now(timezone.utc)
    CACHE.mkdir(parents=True, exist_ok=True)
    ARTICLE_CACHE.mkdir(parents=True, exist_ok=True)
    load_geo_cache()

    existing: dict[str, Any] = {}
    if DATA_PATH.exists():
        try:
            existing = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log(f"Kunne ikke læse eksisterende data.json ({exc})")

    log("Henter RSS fra 12 politikredse…")
    all_rss: list[dict[str, Any]] = []
    for d in DISTRICTS:
        try:
            items = rss_items(d)
            log(f"  {d['name']}: {len(items)} poster")
            all_rss.extend(items)
        except Exception as exc:  # noqa: BLE001
            log(f"  FEJL {d['name']}: {exc}")

    by_thread: dict[str, dict[str, Any]] = {}
    for it in all_rss:
        tid = it["thread_id"]
        prev = by_thread.get(tid)
        if not prev or (it.get("published_at") or "") > (prev.get("published_at") or ""):
            by_thread[tid] = it
    log(f"Unikke politihændelser: {len(by_thread)} (fra {len(all_rss)} RSS-poster)")

    newest_rss = max((it.get("published_at") or "") for it in all_rss) if all_rss else ""
    feeds_ok = sum(1 for d in DISTRICTS if any(it["district"] == d["id"] for it in all_rss))
    reuse_police = False
    if existing and newest_rss and feeds_ok == len(DISTRICTS):
        prev = existing.get("newest_rss") or ""
        if not prev:
            inc = [i for i in (existing.get("incidents") or []) if i.get("source") == "politiupdate"]
            prev = max((i.get("updated_at") or i.get("published_at") or "") for i in inc) if inc else ""
        if prev and newest_rss <= prev:
            reuse_police = True
            log(f"Ingen nye POLITI UPDATE-meddelelser (nyeste RSS {newest_rss} ≤ {prev}). Genbruger politidata.")

    if reuse_police:
        police = annotate_police(
            [i for i in (existing.get("incidents") or []) if i.get("source") == "politiupdate"]
        )
    else:
        threads: dict[str, dict[str, Any]] = {}
        log("Henter fuld tekst for hver politihændelse…")
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
        log("Klassificerer og geokoder politi…")
        police = []
        for tid, rss in by_thread.items():
            inc = build_incident(threads.get(tid) or {}, rss["district"], rss)
            police.append(inc)
        police = annotate_police(police)

    log("Henter ODIN, trafik, strømafbrud, varsler og helikoptere…")
    odin, st_odin = fetch_odin()
    trafik, st_vd = fetch_vejdirektoratet()
    strom, st_gpd = fetch_outages()
    vejr, st_dmi = fetch_dmi_warnings()
    hems, fleet, st_hems = fetch_hems()

    save_geo_cache()

    incidents = police + odin + trafik + strom + vejr + hems
    incidents.sort(key=lambda x: x.get("updated_at") or x.get("published_at") or "", reverse=True)

    pinned = sum(1 for i in incidents if i.get("lat") is not None)
    by_dist: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    for i in incidents:
        if i.get("district"):
            by_dist[i["district"]] = by_dist.get(i["district"], 0) + 1
        by_type[i.get("type") or "andet"] = by_type.get(i.get("type") or "andet", 0) + 1
        by_cat[i.get("category") or "andet"] = by_cat.get(i.get("category") or "andet", 0) + 1

    sources_status = {
        "politiupdate": {
            "ok": feeds_ok > 0,
            "count": len(police),
            "endpoint": "https://via.ritzau.dk/rss/short-messages/latest?publisherId={id}",
            "reused": reuse_police,
        },
        "odin": st_odin,
        "vejdirektoratet": st_vd,
        "elnet": st_gpd,
        "dmi": st_dmi,
        "adsb": st_hems,
    }

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_copenhagen": datetime.now(ZoneInfo("Europe/Copenhagen")).isoformat(timespec="seconds"),
        "newest_rss": newest_rss,
        "source": (
            "POLITI UPDATE, ODIN 112-puls, Vejdirektoratet, Green Power Denmark, "
            "DMI/MeteoAlarm, adsb.lol"
        ),
        "note": (
            "De 12 politikredses officielle X-konti er ikke længere aktive "
            "og er sat til beskyttet. Operative politimeddelelser hentes fra "
            "POLITI UPDATE. Brand- og redningsalarmer kommer fra ODIN (kun "
            "station, ikke præcis adresse). Facebook og Instagram skrames ikke."
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
            "by_category": by_cat,
            "elapsed_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        },
        "sources_status": sources_status,
        "hems": fleet,
        "hems_bases": HEMS_BASES,
        "incidents": incidents,
    }
    DATA_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log(
        f"Skrev {DATA_PATH} — {len(incidents)} hændelser, {pinned} med position, "
        f"{payload['stats']['elapsed_seconds']}s"
    )
    log(f"Kategorier: {by_cat}")
    for key, st in sources_status.items():
        log(f"  kilde {key}: ok={st.get('ok')} n={st.get('count')} err={st.get('error')}")



if __name__ == "__main__":
    main()
