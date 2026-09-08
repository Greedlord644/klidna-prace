#!/usr/bin/env python3
"""Discover, verify and strictly filter quiet full-time jobs for Iva."""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data/jobs.json"
UA = "Mozilla/5.0 (compatible; KlidnaPrace/1.0; +https://github.com/Greedlord644/klidna-prace)"
ALLOWED_HOSTS = ("jobs.cz", "prace.cz", "jenprace.cz", "dobraprace.cz", "easy-prace.cz",
                 "volnamista.cz", "mpsv.cz", "uradprace.cz", "regionalniportaly.cz",
                 "slavkovsko.cz", "startupjobs.cz", "profesia.cz", "praha.eu", "edu.cz",
                 "atlasskolstvi.cz", "pracujveskolstvi.cz", "culturenet.cz", "edu.gov.cz",
                 "edujob.cz", "izus.cz")
QUERIES = [
    'Praha redaktor korektor editor "plný úvazek" práce',
    'Praha archivář archivace digitalizace katalogizace "plný úvazek"',
    'Praha "zadávání dat" evidence dokumentů "plný úvazek"',
    'Říčany Babice administrativa archivace "plný úvazek"',
    'Praha knihovna muzeum galerie dokumentátor "plný úvazek"',
    'Praha práce s dětmi asistent bez pedagogického vzdělání "plný úvazek"',
    'Praha ZUŠ asistent pomocný pracovník "plný úvazek" práce',
    'Praha "dům dětí a mládeže" asistent "plný úvazek" práce',
    'Praha DDM volnočasové aktivity asistent "plný úvazek"',
    'Praha "domov mládeže" asistent pomocný pracovník "plný úvazek"',
    'Říčany ZUŠ DDM asistent práce "plný úvazek"',
]
HARD_REJECT = [
    r"řidičsk[ýé] průkaz.{0,18}(podmín|nutn|požad|skupin)", r"aktivní řidič",
    r"angličtin.{0,24}(výborn|plynul|pokroč|b2|c1|c2|rodil)", r"english.{0,18}(fluent|b2|c1|c2)",
    r"\bv\.?š\.?\s+(vzdělán|ekonom|techn|práv|humanit|směru|oboru)", r"vysokoškolsk.{0,30}(vzdělán|podmín|požad|nutn)",
    r"pedagogick.{0,24}(vzdělán|minimum|kvalifik)",
    r"praxe.{0,25}(podmín|nutn|požad|alespoň|minimálně)", r"minimálně.{0,8}[1-9].{0,8}(let|rok).{0,15}prax",
    r"pokladn|recepční|call centrum|telemarketing|obchodní zástup|aktivní prodej|oslovování klient",
    r"telefonick.{0,18}(komunik|kontakt)|péče o zákazník|zákaznick.{0,12}(podpor|servis)",
    r"organizace schůzek|správa kalendář|vedení kalendář|plánování schůzek|koordinace termín",
    r"koordinace.{0,30}(schůzek|akcí|administrativních aktivit)|vyřizování.{0,25}(korespondence|telefonát)",
    r"příprava.{0,25}(reportů|reportu|prezentací|prezentace)|více úkolů současně|multitask",
    r"sekretář|asistent.?(ka)?.{0,20}ředitele|office manager",
    r"vedoucí|ředitel|manažer|management|vedení.{0,25}(týmu|lidí|pracovník)|řízení týmu|koordinátor",
    r"aktivní komunikac|každodenní kontakt|kontakt se zákazník|kontakt s veřejnost|práce s klient",
    r"komunikační.{0,20}organizační|odolnost vůči stresu|práce pod tlakem",
    r"technik|technické práce|technický pracovník|zvukař|osvětlovač|stavba|bourání scén|údržba technik|elektrotechn",
    r"turis|infocentr|informační centrum|letišt|průvodce|cestovní ruch",
    r"housl|orchestrální hráč|konkurz.{0,30}(herec|herečka|tanečník|hudebník)",
    r"skladník|úklid|výrobn.{0,10}(děln|operátor)|zahradník|manuální práce|směnný provoz",
    r"excel.{0,30}(nutn|podmín|požad|nezbytn|pokroč|výborn|velmi dobr)",
    r"(nutn|podmín|požad|nezbytn|pokroč|výborn|velmi dobr|dobrou znalost).{0,30}excel",
    r"dpp|dpč|brigád|zkrácený úvazek|částečný úvazek|\b(?:1\d|2\d)\s*(?:hod|h)\.?\s*(?:/|týd)",
]
POSITIVE = ["redaktor", "korektor", "editor", "archiv", "digitaliz", "katalogiz", "evidence dokument",
            "zadávání dat", "databáz", "knihovn", "muze", "galeri", "češtin", "text", "zuš",
            "základní uměleck", "dům dětí", "ddm", "domov mládeže", "volnočas", "asistent"]
EXPIRED = ["nabídka již není aktivní", "pozice již byla obsazena", "inzerát byl odstraněn",
           "platnost nabídky skončila", "nabídka byla ukončena", "stránka nenalezena"]

DIRECT_SOURCES = {
    "jobs.cz": (["https://www.jobs.cz/prace/praha/", "https://www.jobs.cz/prace/stredocesky-kraj/"], r"/rpd/\d+/?$"),
    "prace.cz": (["https://www.prace.cz/nabidky/praha/", "https://www.prace.cz/nabidky/stredocesky-kraj/"], r"/(?:firma/[^/]+/)?nabidka/[0-9a-f-]+/?$"),
    "jenprace.cz": (["https://www.jenprace.cz/nabidky/praha", "https://www.jenprace.cz/nabidky/stredocesky-kraj"], r"/nabidka/[^/]+/[^/]+/?$"),
    "dobraprace.cz": (["https://www.dobraprace.cz/nabidka-prace/praha/", "https://www.dobraprace.cz/nabidka-prace/praha-vychod/"], r"/\d+-[^/]+\.html$"),
    "easy-prace.cz": (["https://www.easy-prace.cz/praha", "https://www.easy-prace.cz/praha-vychod"], r"/nabidka/[^/]+/\d+/?$"),
    "volnamista.cz": (["https://www.volnamista.cz/praha", "https://www.volnamista.cz/praha-vychod"], r"/nabidka-prace/[^/]+/\d+/?$"),
    "profesia.cz": (["https://www.profesia.cz/prace/praha/"], r"/prace/[^/]+/O\d+/?$"),
    "edu.gov.cz": (["https://edu.gov.cz/kariera-2/volna-mista-ve-skolstvi/"], r"/job/[^/?]+/?$"),
    "edujob.cz": (["https://www.edujob.cz/nabidky-prace/"], r"/job/\d+/?$"),
    "izus.cz": (["https://www.izus.cz/portal_prace/"], r"/portal_prace/\?id_nabidky_prace=\d+$"),
}

LINK_HINTS = tuple(POSITIVE) + ("administrativ", "dokument", "evidence", "spis", "kulturn", "uměleck",
                                     "děti", "mládež", "absolvent", "back office")


def fetch(url: str, timeout: int = 18) -> tuple[int, str]:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "cs,en;q=0.5"})
    try:
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read(1_500_000).decode(r.headers.get_content_charset() or "utf-8", "replace")
    except Exception:
        return 0, ""


def textify(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw)
    return " ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw)).split())


def discover() -> set[str]:
    urls: set[str] = set()
    for query in QUERIES:
        _, page = fetch("https://html.duckduckgo.com/html/?q=" + quote_plus(query))
        for href in re.findall(r'href=["\']([^"\']+)', page):
            href = html.unescape(href)
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
            host = urlparse(href).netloc.lower()
            if href.startswith("http") and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
                urls.add(href.split("#")[0])
        time.sleep(.4)
    return urls


def discover_direct_sources() -> set[str]:
    """Read each portal's own Prague/near-Prague result list."""
    found: set[str] = set()
    requests = [(host, detail_pattern, page) for host, (pages, detail_pattern) in DIRECT_SOURCES.items() for page in pages]

    def scan(args: tuple[str, str, str]) -> set[str]:
        host, detail_pattern, page = args
        status, raw = fetch(page, timeout=12)
        page_found: set[str] = set()
        if status != 200:
            return page_found
        for match in re.finditer(r'(?is)<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', raw):
            url = urljoin(page, html.unescape(match.group(1))).split("#")[0]
            label = textify(match.group(2)).lower()
            parsed = urlparse(url)
            if not (parsed.netloc.lower() == host or parsed.netloc.lower().endswith("." + host)):
                continue
            target = parsed.path + (("?" + parsed.query) if parsed.query else "")
            if re.fullmatch(detail_pattern, target) and any(hint in (label + " " + target.lower()) for hint in LINK_HINTS):
                page_found.add(url)
        return page_found

    with ThreadPoolExecutor(max_workers=6) as pool:
        for page_found in pool.map(scan, requests):
            found.update(page_found)
    return found


def discover_culturenet() -> set[str]:
    """Read Culturenet's own job archive instead of relying on search results."""
    found: set[str] = set()
    # WordPress REST search returns recent items of all sections; retain only
    # canonical /prace/ detail URLs. This also catches items not shown on page 1.
    for page_no in range(1, 4):
        status, raw = fetch(f"https://www.culturenet.cz/wp-json/wp/v2/search?per_page=100&page={page_no}")
        if status != 200:
            break
        try:
            rows = json.loads(raw)
        except json.JSONDecodeError:
            break
        for row in rows:
            url = str(row.get("url", ""))
            if re.fullmatch(r"https://www\.culturenet\.cz/prace/[^/]+/", url):
                found.add(url)
        if len(rows) < 100:
            break
    for page_no in range(1, 4):
        archive = "https://www.culturenet.cz/prace/" if page_no == 1 else f"https://www.culturenet.cz/prace/page/{page_no}/"
        status, raw = fetch(archive)
        if status != 200:
            break
        before = len(found)
        for href in re.findall(r'href=["\']([^"\']+)', raw, re.I):
            url = urljoin(archive, html.unescape(href)).split("#")[0]
            path = urlparse(url).path.rstrip("/")
            if urlparse(url).netloc.lower().endswith("culturenet.cz") and re.fullmatch(r"/prace/[^/]+", path):
                found.add(url.rstrip("/") + "/")
        if page_no > 1 and len(found) == before:
            break
    return found


def meta(raw: str, prop: str) -> str:
    patterns = [rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']']
    for pattern in patterns:
        m = re.search(pattern, raw, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def relevant_text(url: str, raw: str) -> str:
    """Remove navigation/footer text that can corrupt location and requirement checks."""
    if urlparse(url).netloc.lower().endswith("culturenet.cz"):
        start = raw.find('<div class="page-content page-content--single')
        if start >= 0:
            end = raw.find("</main>", start)
            return textify(raw[start:end if end >= 0 else len(raw)])
    # Most large job portals expose the canonical advert as schema.org
    # JobPosting JSON-LD. It is cleaner than navigation and related offers.
    for block in re.findall(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', raw):
        try:
            node = json.loads(html.unescape(block))
        except (json.JSONDecodeError, TypeError):
            continue
        stack = node if isinstance(node, list) else [node]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                kind = item.get("@type", "")
                if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                    return textify(" ".join(str(item.get(k, "")) for k in ("title", "description", "qualifications", "responsibilities", "jobLocation")))
                stack.extend(v for v in item.values() if isinstance(v, (dict, list)))
    main = re.search(r"(?is)<main\b[^>]*>(.*?)</main>", raw)
    if main:
        return textify(main.group(1))
    return textify(raw)


def classify(url: str, raw: str) -> dict | None:
    plain = relevant_text(url, raw)
    low = plain.lower()
    if len(plain) < 300 or any(x in low for x in EXPIRED) or any(re.search(x, low) for x in HARD_REJECT):
        return None
    if not ("plný úvazek" in low or "plný pracovní úvazek" in low or "hpp" in low):
        return None
    title = meta(raw, "og:title") or re.sub(r"\s+", " ", re.search(r"(?is)<title>(.*?)</title>", raw).group(1) if re.search(r"(?is)<title>(.*?)</title>", raw) else "Pracovní nabídka")
    title = re.split(r"\s+[|–-]\s+", title)[0].strip()[:140]
    location_text = (title + " " + url + " " + plain).lower()
    near = any(x in location_text for x in ("říčany", "babice", "strančice", "mnichovice"))
    prague = bool(re.search(r"\bpraha(?:\s|\b|[0-9-])|\bpraze\b|\bpražsk", location_text))
    outside = any(x in (title + " " + url).lower() for x in ("brno", "ostrava", "žilina", "plzeň", "plzen", "olomouc", "liberec", "pardubice", "hradec-králové", "hradec-kralove", "české-budějovice", "ceske-budejovice"))
    if outside or not (near or prague):
        return None
    score = sum(3 for x in POSITIVE if x in low)
    if prague: score += 3
    if near: score += 5
    if score < 6:
        return None
    desc = plain[:900]
    place = "Babice a okolí" if near else "Praha"
    category = "text" if any(x in low for x in ("redaktor", "korektor", "editor", "text", "nakladatel")) else "admin"
    if any(x in low for x in ("dětmi", "děti", "dětský", "zuš", "základní uměleck",
                              "dům dětí", "ddm", "domov mládeže", "volnočas")):
        category = "children"
    if "ozp" in low or "invalid" in low: category = "ozp"
    caution = " Obecné komunikační požadavky je vhodné ověřit při prvním kontaktu." if "komunikativ" in low else ""
    return {
        "id": hashlib.sha1(url.encode()).hexdigest()[:14], "category": category,
        "location": "near" if place != "Praha" else "prague", "title": title,
        "company": "viz inzerát", "place": place, "salary": "viz inzerát", "date": "ověřeno dnes",
        "source": urlparse(url).netloc.removeprefix("www."),
        "tags": [[{"text":"Text a kultura","admin":"Archivace a evidence","children":"Práce s dětmi","ozp":"Vhodné pro OZP"}[category], "ozp" if category == "ozp" else ""]],
        "why": "Nabídka prošla filtrem kvalifikace, lokality, úvazku a zátěžových požadavků.",
        "description": desc[:900] + caution, "url": url, "_score": score,
    }


def main() -> None:
    old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"jobs": []}
    old_by_url = {j["url"]: j for j in old.get("jobs", [])}
    candidates = set(old_by_url) | discover_culturenet() | discover_direct_sources() | discover()
    jobs = []
    for url in sorted(candidates):
        status, raw = fetch(url)
        if status == 200:
            job = classify(url, raw)
            if job: jobs.append(job)
        time.sleep(.15)
    jobs.sort(key=lambda j: (j["category"] == "ozp", -j.pop("_score", 0)))
    now = datetime.now(timezone.utc)
    months = ["", "ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"]
    payload = {"checked_at": now.isoformat(), "checked_display": f"{now.day}. {months[now.month]} {now.year}", "jobs": jobs[:40]}
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
