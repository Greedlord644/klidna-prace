# Klidná práce

Jednoduchý dashboard s přísně filtrovanými pracovními nabídkami pro Ivu. Zobrazuje pouze plné úvazky v Praze nebo poblíž Babic, u kterých automatická kontrola nenašla nevhodnou kvalifikaci ani výrazně zátěžové požadavky.

## Aktualizace

Workflow `Aktualizovat pracovní nabídky` se spouští přes `workflow_dispatch`. Vyhledá nové kandidáty, otevře každý přímý odkaz, vyřadí neaktivní nabídky a uloží výsledek do `dist/data/jobs.json`.

Cron-job.org má volat:

`POST https://api.github.com/repos/Greedlord644/klidna-prace/actions/workflows/update-jobs.yml/dispatches`

Hlavičky:

```text
Accept: application/vnd.github+json
Authorization: Bearer GITHUB_TOKEN
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Tělo:

```json
{"ref":"main"}
```

Doporučený interval je jednou za 6 hodin. Token musí mít oprávnění spouštět Actions v tomto repozitáři.

## GitHub Pages

V `Settings → Pages` nastavte jako zdroj `GitHub Actions`. Každá změna dat pak automaticky publikuje aktuální web.
