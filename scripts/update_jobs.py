#!/usr/bin/env python3
"""Discover, verify and rank calmer jobs for Iva."""

from __future__ import annotations

import hashlib
import html
import json
import re
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
                 "edujob.cz", "izus.cz", "jobs.recruitis.io", "divadlo.cz")
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
    'Praha asistent kultura knihy hračky práce',
    'Praha třídění knih bez praxe práce',
    'Praha vrátný muzeum divadlo galerie práce',
    'Praha jednoduchá práce asistent bez praxe',
]
HARD_REJECT = [
    r"řidičsk[ýé] průkaz.{0,18}(podmín|nutn|požad|skupin)", r"aktivní řidič",
    r"angličtin.{0,24}(výborn|plynul|pokroč|b2|c1|c2|rodil)", r"english.{0,18}(fluent|b2|c1|c2)",
    r"(požadujeme|podmínkou|nutn|nezbytn).{0,35}(vysokoškol|\bv\.?š\.?)",
    r"(vysokoškol|\bv\.?š\.?).{0,35}(podmín|požad|nutn|nezbytn)",
    r"pedagogick.{0,24}(vzdělán|minimum|kvalifik)",
    r"praxe.{0,25}(podmín|nutn|požad|alespoň|minimálně)", r"minimálně.{0,8}[1-9].{0,8}(let|rok).{0,15}prax",
    r"pokladn|call centrum|telemarketing|cold call",
    r"oslovován.{0,30}(klient|zákazník)|akvizic.{0,20}(klient|zákazník)",
    r"telefonick.{0,18}(komunik|kontakt|prodej)|vyřizování.{0,25}telefonát",
    r"(organizace|domluv|plánování|koordinace).{0,25}(schůzek|schůzky|termínů|prohlídek)",
    r"správa kalendář|vedení kalendář|networking",
    r"koordinace.{0,30}(schůzek|akcí|administrativních aktivit)|vyřizování.{0,25}(korespondence|telefonát)",
    r"příprava.{0,25}(reportů|reportu|prezentací|prezentace)|více úkolů současně|multitask",
    r"sekretář|asistent.?(ka)?.{0,20}ředitele|office manager|copywrit|social media",
    r"vedoucí|ředitel|manažer|management|team leader|vedení.{0,25}(týmu|lidí|pracovník)|řízení týmu|koordinátor",
    r"komunikační.{0,20}organizační|odolnost vůči stresu|práce pod tlakem",
    r"technik|technické práce|technický pracovník|zvukař|osvětlovač|stavba|bourání scén|údržba technik|elektrotechn|network administrator|software developer|\bit administrator\b|\bdevops\b",
    r"turis|infocentr|informační centrum|letišt|průvodce|cestovní ruch",
    r"housl|orchestrální hráč|konkurz.{0,30}(herec|herečka|tanečník|hudebník)",
    r"úklid|výrobn.{0,10}(děln|operátor)|zahradník",
    r"excel.{0,30}(nutn|podmín|požad|nezbytn|pokroč|výborn|velmi dobr)",
    r"(nutn|podmín|požad|nezbytn|pokroč|výborn|velmi dobr|dobrou znalost).{0,30}excel",
]
POSITIVE = ["redaktor", "korektor", "editor", "archiv", "digitaliz", "katalogiz", "evidence dokument",
            "zadávání dat", "databáz", "knih", "muze", "galeri", "češtin", "text", "zuš",
            "základní uměleck", "dům dětí", "ddm", "domov mládeže", "volnočas", "asistent",
            "třídění", "vrátn", "hračk", "fotograf"]
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
    "jobs.recruitis.io": (["https://jobs.recruitis.io/knihobot"], r"/knihobot/\d+-[^/?]+/?$"),
    "divadlo.cz": (["https://www.divadlo.cz/ceske-divadlo/prilezitosti/"], r"/clanky/[^/?]+/?$"),
}
SEED_URLS = {
    "https://www.culturenet.cz/prace/hugo-chodi-bos-konkurz-asistenta-ka-prodeje/",
    "https://jobs.recruitis.io/knihobot/458172-brigada-v-knihobotu-hostivar",
    "https://www.divadlo.cz/clanky/narodni-divadlo-konkurz-vratna-vratny-anenskeho-arealu/",
}

LINK_HINTS = tuple(POSITIVE) + ("administrativ", "dokument", "evidence", "spis", "kulturn", "uměleck",
                                     "děti", "mládež", "absolvent", "back office", "vrátn", "knih", "hračk")
STARTUPJOBS_SLUG_HINTS = (
    "admin", "asistent", "assistant", "back-office", "data-entry", "evidence",
    "dokument", "archiv", "katalog", "editor", "redaktor", "korektor", "text",
    "content", "knihov", "muze", "galer", "kultur", "deti", "kids", "mladez",
)

RISK_RULES = [
    ("kontakt se zákazníky", r"komunikac.{0,35}(zákazník|klient|veřejnost)|radit zákazník|péče o zákazník"),
    ("prodej na místě", r"\bprodej(?:e|i|na|ní)?\b|prodejně|proviz"),
    ("angličtina", r"angličtin|anglick|english"),
    ("směny nebo noční provoz", r"směnn|směny|noční služ|noční směn"),
    ("brigáda nebo kratší úvazek", r"\bbrigád|\bdpp\b|\bdpč\b|zkrácený úvazek|částečný úvazek"),
    ("lehčí manuální práce nebo výkonové normy", r"manuální práce|vychystáv|pickuj|kompletuj|třídění knih|normy|orientovaném na výkon|měříme rychlost"),
    ("vrátnice, recepce nebo ostraha", r"\bvrátn|\brecepce\b|ostraha|kamerov|obchůzk|registrace návštěv"),
]


def fetch(url: str, timeout: int = 10) -> tuple[int, str]:
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
    def search(query: str) -> set[str]:
        found: set[str] = set()
        _, page = fetch("https://html.duckduckgo.com/html/?q=" + quote_plus(query), timeout=8)
        for href in re.findall(r'href=["\']([^"\']+)', page):
            href = html.unescape(href)
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
            host = urlparse(href).netloc.lower()
            if href.startswith("http") and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
                found.add(href.split("#")[0])
        return found

    with ThreadPoolExecutor(max_workers=8) as pool:
        for found in pool.map(search, QUERIES):
            urls.update(found)
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


def discover_startupjobs() -> set[str]:
    """Read StartupJobs' official live-offer sitemap directly."""
    status, raw = fetch("https://www.startupjobs.cz/sitemap/offers.xml", timeout=20)
    if status != 200:
        return set()
    found: set[str] = set()
    for value in re.findall(r"(?is)<loc>\s*(.*?)\s*</loc>", raw):
        url = html.unescape(value).strip().split("#")[0]
        parsed = urlparse(url)
        if parsed.netloc.lower() not in ("startupjobs.cz", "www.startupjobs.cz"):
            continue
        if not re.fullmatch(r"/nabidka/\d+/[^/?]+/?", parsed.path):
            continue
        slug = parsed.path.rstrip("/").rsplit("/", 1)[-1].lower()
        if any(hint in slug for hint in STARTUPJOBS_SLUG_HINTS):
            found.add(url)
    return found


def discover_culturenet() -> set[str]:
    """Read Culturenet's own job archive instead of relying on search results."""
    found: set[str] = set()
    # WordPress REST search returns recent items of all sections; retain only
    # canonical /prace/ detail URLs. This also catches items not shown on page 1.
    endpoints = [f"https://www.culturenet.cz/wp-json/wp/v2/search?per_page=100&page={page_no}" for page_no in range(1, 3)]
    endpoints += ["https://www.culturenet.cz/prace/", "https://www.culturenet.cz/prace/page/2/"]

    def scan(endpoint: str) -> set[str]:
        page_found: set[str] = set()
        status, raw = fetch(endpoint, timeout=8)
        if status != 200:
            return page_found
        if "wp-json" in endpoint:
            try:
                rows = json.loads(raw)
            except json.JSONDecodeError:
                return page_found
            for row in rows:
                url = str(row.get("url", ""))
                if re.fullmatch(r"https://www\.culturenet\.cz/prace/[^/]+/", url):
                    page_found.add(url)
            return page_found
        for href in re.findall(r'href=["\']([^"\']+)', raw, re.I):
            url = urljoin(endpoint, html.unescape(href)).split("#")[0]
            path = urlparse(url).path.rstrip("/")
            if urlparse(url).netloc.lower().endswith("culturenet.cz") and re.fullmatch(r"/prace/[^/]+", path):
                page_found.add(url.rstrip("/") + "/")
        return page_found

    with ThreadPoolExecutor(max_workers=4) as pool:
        for page_found in pool.map(scan, endpoints):
            found.update(page_found)
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
    if re.search(r"[А-Яа-я]", plain) or "/ua-" in url.lower():
        return None
    cultural_context = any(x in low for x in ("divadlo", "galerie", "muzeum", "knihovna", "kulturní"))
    if "recep" in low and not cultural_context:
        return None
    employment = "Plný úvazek"
    if re.search(r"\bbrigád|\bdpp\b|\bdpč\b", low):
        employment = "Brigáda / DPP nebo DPČ"
    elif re.search(r"zkrácený úvazek|částečný úvazek", low):
        employment = "Zkrácený úvazek"
    if not ("plný úvazek" in low or "plný pracovní úvazek" in low or "hpp" in low
            or employment != "Plný úvazek"):
        return None
    title = meta(raw, "og:title") or re.sub(r"\s+", " ", re.search(r"(?is)<title>(.*?)</title>", raw).group(1) if re.search(r"(?is)<title>(.*?)</title>", raw) else "Pracovní nabídka")
    if "informační portál" in title.lower():
        heading = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", raw)
        if heading:
            title = textify(heading.group(1))
    title = re.sub(r"\s+-\s+(?:Culturenet|StartupJobs.*|Jobs\.cz.*|Prace\.cz.*)$", "", title, flags=re.I)
    title = re.split(r"\s+\|\s+", title)[0].strip()[:140]
    location_text = (title + " " + url + " " + plain).lower()
    near = any(x in location_text for x in ("říčany", "babice", "strančice", "mnichovice"))
    prague = bool(re.search(r"\bpraha(?:\s|\b|[0-9-])|\bpraze\b|\bprahy\b|\bpražsk", location_text))
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
    core = low[:1200]
    category = "text" if any(x in core for x in ("redaktor", "korektor", "editor", "tvorba text", "úprava text", "nakladatel")) else "admin"
    if any(x in core for x in ("dětmi", "děti", "dětský", "zuš", "základní uměleck",
                              "dům dětí", "ddm", "domov mládeže", "volnočas")):
        category = "children"
    if "ozp" in low or "invalid" in low: category = "ozp"
    warnings = [label for label, pattern in RISK_RULES if re.search(pattern, core)]
    tag_label = {"text":"Text a kultura","admin":"Archivace a evidence","children":"Práce s dětmi","ozp":"Vhodné pro OZP"}[category]
    if "knihobot" in low or "třídění knih" in low:
        tag_label = "Knihy a třídění"
    elif "vrátn" in core:
        tag_label = "Vrátnice a třídění"
    elif category == "children" and "prodej" in low:
        tag_label = "Kultura a asistence"
    tags = [[tag_label, "ozp" if category == "ozp" else ""]]
    if warnings:
        tags.append(["Ke zvážení", "warn"])
        why = "Může být zajímavá, ale před reakcí zvažte: " + "; ".join(warnings) + "."
    else:
        why = "Nabídka prošla filtrem kvalifikace, lokality a zátěžových požadavků."
    salary = "neuvedeno"
    salary_match = re.search(r"\b(\d{2,3}\s*[-–]\s*\d{2,3}\s*kč\s*/?\s*hod(?:inu)?)", low)
    if salary_match:
        salary = salary_match.group(1).replace("kč", "Kč")
    elif "proviz" in core:
        salary = "neuvedeno (provize)"
    date = "ověřeno dnes"
    published = meta(raw, "article:published_time")
    published_match = re.match(r"(\d{4})-(\d{2})-(\d{2})", published)
    if published_match:
        year, month, day = published_match.groups()
        date = f"publikováno {int(day)}. {int(month)}. {year}"
    else:
        visible_date = re.search(r"publikováno:\s*(\d{1,2})\.\s*(\d{1,2})\s*\.\s*(\d{4})", low)
        if visible_date:
            day, month, year = visible_date.groups()
            date = f"publikováno {int(day)}. {int(month)}. {year}"
    return {
        "id": hashlib.sha1(url.encode()).hexdigest()[:14], "category": category,
        "location": "near" if place != "Praha" else "prague", "title": title,
        "company": "viz inzerát", "place": place, "employment": employment,
        "salary": salary, "date": date,
        "source": urlparse(url).netloc.removeprefix("www."),
        "tags": tags, "why": why,
        "description": desc[:900], "url": url, "_score": score, "_risk": len(warnings),
    }


def main() -> None:
    old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"jobs": []}
    old_by_url = {j["url"]: j for j in old.get("jobs", [])}
    discovery = (discover_culturenet, discover_startupjobs, discover_direct_sources, discover)
    candidates = set(old_by_url) | SEED_URLS
    with ThreadPoolExecutor(max_workers=4) as pool:
        for found in pool.map(lambda fn: fn(), discovery):
            candidates.update(found)
    jobs = []
    def inspect(url: str) -> dict | None:
        status, raw = fetch(url, timeout=10)
        if status == 0:
            status, raw = fetch(url, timeout=10)
        if status == 200:
            return classify(url, raw)
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        for job in pool.map(inspect, sorted(candidates)):
            if job:
                jobs.append(job)
    jobs.sort(key=lambda j: (j.get("_risk", 0) > 0, j.get("_risk", 0), j["category"] == "ozp", -j.get("_score", 0)))
    for job in jobs:
        job.pop("_score", None)
        job.pop("_risk", None)
    now = datetime.now(timezone.utc)
    months = ["", "ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"]
    payload = {"checked_at": now.isoformat(), "checked_display": f"{now.day}. {months[now.month]} {now.year}", "jobs": jobs[:40]}
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
