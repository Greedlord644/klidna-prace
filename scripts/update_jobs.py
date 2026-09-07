#!/usr/bin/env python3
"""Discover, verify and strictly filter quiet full-time jobs for Iva."""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data/jobs.json"
UA = "Mozilla/5.0 (compatible; KlidnaPrace/1.0; +https://github.com/Greedlord644/klidna-prace)"
ALLOWED_HOSTS = ("jobs.cz", "prace.cz", "jenprace.cz", "dobraprace.cz", "easy-prace.cz",
                 "volnamista.cz", "mpsv.cz", "uradprace.cz", "regionalniportaly.cz",
                 "slavkovsko.cz", "startupjobs.cz", "profesia.cz")
QUERIES = [
    'Praha redaktor korektor editor "plný úvazek" práce',
    'Praha archivář archivace digitalizace katalogizace "plný úvazek"',
    'Praha "zadávání dat" evidence dokumentů "plný úvazek"',
    'Říčany Babice administrativa archivace "plný úvazek"',
    'Praha knihovna muzeum galerie dokumentátor "plný úvazek"',
    'Praha práce s dětmi asistent bez pedagogického vzdělání "plný úvazek"',
]
HARD_REJECT = [
    r"řidičsk[ýé] průkaz.{0,18}(podmín|nutn|požad|skupin)", r"aktivní řidič",
    r"angličtin.{0,24}(výborn|plynul|pokroč|c1|c2|rodil)", r"english.{0,18}(fluent|c1|c2)",
    r"vysokoškolsk.{0,20}(podmín|požad|nutn)", r"pedagogick.{0,24}(vzdělán|minimum|kvalifik)",
    r"praxe.{0,25}(podmín|nutn|požad|alespoň|minimálně)", r"minimálně.{0,8}[1-9].{0,8}(let|rok).{0,15}prax",
    r"pokladn|recepční|call centrum|telemarketing|obchodní zástup|aktivní prodej|oslovování klient",
    r"telefonick.{0,18}(komunik|kontakt)|péče o zákazník|zákaznick.{0,12}(podpor|servis)",
    r"organizace schůzek|vedení kalendář|sekretář|asistent.?(ka)?.{0,20}ředitele|office manager",
    r"skladník|úklid|výrobn.{0,10}(děln|operátor)|zahradník|manuální práce|směnný provoz",
    r"dpp|dpč|brigád|zkrácený úvazek|částečný úvazek",
]
POSITIVE = ["redaktor", "korektor", "editor", "archiv", "digitaliz", "katalogiz", "evidence dokument",
            "zadávání dat", "databáz", "knihovn", "muze", "galeri", "češtin", "text"]
EXPIRED = ["nabídka již není aktivní", "pozice již byla obsazena", "inzerát byl odstraněn",
           "platnost nabídky skončila", "nabídka byla ukončena", "stránka nenalezena"]


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


def meta(raw: str, prop: str) -> str:
    patterns = [rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']']
    for pattern in patterns:
        m = re.search(pattern, raw, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def classify(url: str, raw: str) -> dict | None:
    plain = textify(raw)
    low = plain.lower()
    if len(plain) < 300 or any(x in low for x in EXPIRED) or any(re.search(x, low) for x in HARD_REJECT):
        return None
    if not ("plný úvazek" in low or "pracovní poměr" in low or "hpp" in low):
        return None
    score = sum(3 for x in POSITIVE if x in low)
    if "praha" in low: score += 3
    if any(x in low for x in ("říčany", "babice", "strančice", "mnichovice")): score += 5
    if score < 6:
        return None
    title = meta(raw, "og:title") or re.sub(r"\s+", " ", re.search(r"(?is)<title>(.*?)</title>", raw).group(1) if re.search(r"(?is)<title>(.*?)</title>", raw) else "Pracovní nabídka")
    desc = meta(raw, "og:description") or plain[:900]
    title = re.split(r"\s+[|–-]\s+", title)[0].strip()[:140]
    place = "Babice a okolí" if any(x in low for x in ("říčany", "babice", "strančice", "mnichovice")) else "Praha"
    category = "text" if any(x in low for x in ("redaktor", "korektor", "editor", "text", "nakladatel")) else "admin"
    if any(x in low for x in ("dětmi", "děti", "dětský")): category = "children"
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
    candidates = set(old_by_url) | discover()
    jobs = []
    for url in sorted(candidates):
        status, raw = fetch(url)
        if status == 200:
            job = classify(url, raw)
            # Již ručně prověřený záznam zachováme, pokud jeho detail stále
            # existuje a portál ho neoznačil jako ukončený. Vyhledávací portály
            # totiž často přidávají text cizích nabídek do patičky stránky.
            if not job and url in old_by_url and not any(x in textify(raw).lower() for x in EXPIRED):
                job = dict(old_by_url[url])
            if job: jobs.append(job)
        time.sleep(.15)
    jobs.sort(key=lambda j: (j["category"] == "ozp", -j.pop("_score", 0)))
    now = datetime.now(timezone.utc)
    months = ["", "ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září", "října", "listopadu", "prosince"]
    payload = {"checked_at": now.isoformat(), "checked_display": f"{now.day}. {months[now.month]} {now.year}", "jobs": jobs[:40]}
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
