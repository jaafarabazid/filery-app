# Domain, DNS and launch checklist

Everything about **filery.app** as an internet property: what is registered, what is
configured, what was decided and why, and what remains open.

Written 2026-08-06. Launched and substantially revised 2026-08-10. This lives in the repo
deliberately, because it was worked out in a session on a different project and would
otherwise not travel.

⚠️ **This file was dropped from the remote once already.** A history rewrite on
2026-08-10 removed the commit that added it, and it survived only in one local clone,
which is a poor place for the only copy of the document whose whole purpose is to
travel. **If you rebase or reset this branch, check that `DOMAIN.md` is still on
`origin/main` afterwards.**

---

## The domain

**`filery.app`**, registered **2026-08-05** at Cloudflare Registrar.
**$14.20/year, auto-renew on, expires 2027-08-06.** Registrant is ManTek
Technologies at the Meydan address.

Zone `a056037641f26779fbeda2c2d701500d`, account `a7de0c4d9210c176ccbf15b1a5248b48`.
Authoritative nameservers **`chin.ns.cloudflare.com`** and `henrik.ns.cloudflare.com`.

`filery.com` was never an option: registered 2007, parked with IONOS.

### Why `.app` and not `.io`

Decided 2026-07-17, reaffirmed at purchase. Do not relitigate:

- **`.app` is HSTS-preloaded**, so HTTPS is enforced at the TLD level by browsers
  before a request is even made. For a tool whose promise is safe file handling that
  is substantive, not decorative.
- `.io` reads as a developer product. Filery is a consumer file utility, and that
  audience reads `.com` and `.app`.
- **`.io` has a long-term question over it.** It is the ccTLD for the British Indian
  Ocean Territory, and the UK has agreed to cede the Chagos Islands to Mauritius. A
  ccTLD whose country code may be retired is a poor foundation for a consumer brand.
- Price sealed it: $14.20 against roughly $40 to $70 for `.io`.

---

## DNS as configured

**Address records exist since the 2026-08-09/10 launch**, both apex and `www`, proxied
through Cloudflare. Before that the zone deliberately had none, which is why the four
records below are all about mail: they were put in place while the domain served
nothing.

✅ **The mail records survived the launch untouched**, re-verified by `dig` on
2026-08-10. Adding a site does not disturb them, but re-check after any bulk DNS edit,
because these are the records nobody looks at.

### Anti-spoofing, all four verified by `dig`, not by the dashboard

| record | value | purpose |
|---|---|---|
| `MX filery.app` | `0 .` | null MX, RFC 7505: this domain accepts no mail |
| `TXT filery.app` | `v=spf1 -all` | no host is authorised to send |
| `TXT _dmarc.filery.app` | `v=DMARC1; p=reject; sp=reject; adkim=s; aspf=s;` | reject anything claiming to be us |
| `TXT *._domainkey.filery.app` | `v=DKIM1; p=` | empty key = revoked, for every selector |

A brand-new domain with no reputation is exactly what gets picked up for a phishing
run, and without these anyone could send mail as `@filery.app` with nothing in DNS to
contradict them.

**On `sp=reject`:** redundant today, because an absent `sp` inherits `p`. It earns its
place the day Filery sends mail and the apex is relaxed to onboard a sender. Without
it, **every subdomain silently relaxes too**.

**On `rua`:** deliberately omitted. Aggregate reports sent to an address on a
different domain need an authorization record on the receiving side
(`filery.app._report._dmarc.mantek.io`) or most reporters refuse to send. A parked
domain is not tuning anything. Add `rua` together with that record if Filery ever
sends real mail.

**The DKIM wildcard does not block future DKIM.** An explicit record beats a wildcard
(RFC 4592), so publishing a real `resend._domainkey.filery.app` key later simply
answers instead. Nothing to remove.

---

## Two traps, both hit or narrowly avoided already

⚠️ **Do NOT use Cloudflare's DNS "Email Record Creator" wizard on this zone.** It
*adds* records rather than editing, and it writes an SPF and a `_dmarc` that already
exist. **Two `v=spf1` records is a `permerror`** under RFC 7208, and **two `_dmarc`
records makes receivers skip DMARC entirely.** Running it would silently undo the
table above. Its `*._domainkey` suggestion was the only genuinely missing piece and
was added by hand instead.

⚠️ **When Cloudflare offers to "Create a new proxied DNS record", decline it.** It
appears in the Redirect Rule deploy dialog. It creates a placeholder pointing at a
dummy IP, which converts a clean NXDOMAIN into a live name serving a Cloudflare error
page, and makes any redirect chain end in an error. Choose "Ignore and deploy rule
anyway".

⚠️ **Cloudflare's DNS recommendations panel will permanently flag "Email cannot reach
@filery.app addresses".** That is correct behaviour, not a gap. Its checker reads "no
MX that receives mail" as a defect and cannot distinguish it from a deliberate null
MX. Do not chase that panel to zero.

---

## Canonical form: WWW

**`www.filery.app` is canonical. The apex redirects to it**, matching mantek.io.

```
https://filery.app      301 ->  https://www.filery.app/
https://www.filery.app  200
```

⚠️ **This reverses an earlier decision, on purpose. Do not flip it back.** Between
2026-08-06 and 2026-08-10 this document specified the **apex** as canonical, argued
from a consumer app reading better as `filery.app` on a download button and from
`.app` domains conventionally skipping `www`. That reasoning was real but it was not
worth undoing a shipped, working configuration for, and consistency with mantek.io
has its own value. **Settled on www, 2026-08-10.**

### The rules, as they actually are

**Two Redirect Rules, both active. There is no disabled rule and no `www to apex`
rule**, so there is no loop risk and nothing to clean up.

| # | name | match | action |
|---|---|---|---|
| 1 | `http to https` | `http://*` | 301 to `https://${1}` |
| 2 | `root to www` | `https://filery.app/*` | 301 to `https://www.filery.app/${1}` |

Rule 2 is the canonical enforcement and was written deliberately, not inherited.

ℹ️ Rule 1 is near-dead weight on this TLD, harmlessly: `.app` is HSTS-preloaded, so
browsers upgrade internally and never send plaintext. Cloudflare's **Always Use HTTPS**
toggle (SSL/TLS, Edge Certificates) is the conventional instrument for it. Note also
that `http://filery.app` takes two hops (rule 1, then rule 2) while
`http://www.filery.app` takes one. Not worth optimising, given preload means neither
path is normally travelled.

---

## Launch: done, and what is still open

✅ **Launched 2026-08-09/10.** A landing page, 404, robots.txt and sitemap are live,
both hostnames resolve through Cloudflare, and the apex to www redirect is working.
The mail hardening above survived the launch untouched, verified by `dig`.

✅ **1. Redirect preserves path and query string.** Closed 2026-08-10. Checked beyond
the homepage, because a broken wildcard replacement is invisible at the root:

| request to `filery.app` | `location:` |
|---|---|
| `/some/path?a=1` | `https://www.filery.app/some/path?a=1` |
| `/a/b/c/deep?x=1&y=2` | `https://www.filery.app/a/b/c/deep?x=1&y=2` |
| `/trailing/` | `https://www.filery.app/trailing/` |
| `/?only=query` | `https://www.filery.app/?only=query` |

Re-run after any edit to rule 2:

```bash
curl -sI https://filery.app/some/path?a=1 | grep -i '^location:'
```

✅ **2. Crawler policy decided 2026-08-09: fully open.** Search crawlers, AI answer
engines and AI training crawlers are all allowed. Cloudflare was already on "Do not
block", so no zone change was needed; what changed is that it is now a decision rather
than an inherited default, and it is stated in `site/robots.txt` so the policy is
legible and portable if the site ever leaves Cloudflare. Filery is free and open
source, so discovery and citation are the point, and there is no content here with
licensing value to protect.

ℹ️ Keep three bot categories distinct, because the Cloudflare toggle does not:
**search crawlers** (Googlebot, Bingbot) drive traffic; **AI answer engines**
(OAI-SearchBot, PerplexityBot) fetch live and usually cite with a link, so they drive
traffic too and should never be blocked; **AI training crawlers** (GPTBot, ClaudeBot,
CCBot, Google-Extended) take content and return nothing. Only the third is a values
call. mantek.io blocks that third group, which is under review separately.

Still open: **the trademark position below**, and code signing (an Apple Developer ID
at $99/year, plus a Windows Authenticode certificate). Until signing is bought, both
builds warn on first launch and the landing page tells visitors how to get past it.

---

## The name: searched 2026-08-09

Superseding an earlier note here that said the mark had never been searched. It has
been now. Run by hand in a browser, because every register blocks automated access
exactly as this document warned: Justia returns 403, Trademarkia 403, the USPTO search
API 404.

### What the register says

`FILERY` is a live US registration, and the class is the material fact:

| field | value |
|---|---|
| Mark | FILERY, standard character |
| Registration | 6294999, serial 90125595 |
| Status | 700, Registered; class status Active |
| Filed / registered | 2020-08-20 / 2021-03-16 |
| Owner | Dongguan Hanluxin E-Commerce Co., Ltd (originally Jin Li) |
| **Class** | **016, paper goods** |
| Goods | easels, ballpoint pens, bathroom tissue, baby bibs, bookbinding tape, calendars and diaries, drawing boards, paper doilies, egg cartons, photocopy paper |

**There is no `FILERY` registration in Class 9 (computer software) or Class 42
(software as a service).** The software space is, on the US register, unoccupied.

### The basis for proceeding

**Filery ships as a free, open-source desktop utility.** Trademark rights attach to
the goods and services a mark is registered for, and identical marks routinely coexist
across unrelated classes. Class 016 covers physical stationery sold through consumer
marketplaces; Filery is downloadable software distributed through GitHub and this
domain. Different goods, different channels, different buyers.

Recorded honestly, because a future reader deserves the whole picture: the mark is
**identical rather than merely similar**, and Class 016 is office and filing supplies,
which is conceptually adjacent to file management. That adjacency is the weakest point
in the position, and it is why the conditions below matter.

### What would warrant revisiting

Two changes, either of which strengthens the other side materially:

- **Distributing through an app store.** Store operators act conservatively on
  trademark complaints and tend to remove first and adjudicate later.
- **Charging for it.** "Free and open source" is a genuine mitigating factor but not
  an exemption: liability turns on use in commerce and likelihood of confusion, not on
  revenue.

If either becomes likely, **file `FILERY` in Class 9 first**, roughly $250 to $350 per
class at the USPTO. The examiner may or may not cite the Class 016 registration.

ℹ️ **Worth re-checking cheaply:** a US registration requires a Section 8 declaration of
continued use between the fifth and sixth anniversary. For this registration that
window opened **2026-03-16** and runs to 2027-03-16, with a grace period to September
2027. If it is not filed, the registration cancels. Not something to rely on, but a
one-minute lookup.

ℹ️ **Only the US register was searched.** No UAE search has been done, which would
matter if Filery is ever commercialised through the ManTek entity.

⚠️ This is a record of what was found and decided, not legal advice. Nobody
qualified has reviewed it.

### Note on the earlier "do not ship binaries" rule

This document previously said not to tag a public `v1.0.0` because downloadable
binaries are a hard commitment to the name. **That threshold has already been
crossed, deliberately.** The repository went public on 2026-08-09 with five tagged
releases attached, `v0.9.0` through `v0.9.4`, and the landing page links straight to
the macOS DMG and the Windows installer. That was decided with the Class 016 finding
in hand, not by oversight. Version numbering is now an ordinary release decision.

---

## Verifying any of this

⚠️ **The wrangler OAuth token cannot do the DNS or Rules work.** Corrected 2026-08-10:
it is **not** read-only across the board, as this section previously claimed. Actual
scopes include `pages (write)`, `workers (write)`, `d1 (write)` and `ssl_certs
(write)`, alongside `zone (read)`. So `wrangler pages deploy` works and is how the
site ships.

What genuinely does not work, confirmed by probing:

- The OAuth token is **rejected as a raw `Authorization: Bearer` header** on the REST
  API. Even `GET /pages/projects/...` returns 401. It functions only through wrangler.
- wrangler 4.106 has **no `pages domain` subcommand**, so a custom domain cannot be
  attached from the CLI.
- Attaching a custom domain writes a DNS record, and the token holds only
  `zone (read)`. Blocked on permissions, not tooling.

Writing needs a purpose-made token (My Profile, API Tokens, Zone:DNS:Edit on
filery.app plus Account:Cloudflare Pages:Edit), otherwise it is the dashboard by hand.

**`dig` works and is the better instrument anyway**, because it reads the artefact
rather than the interface that claimed success:

```bash
dig +short TXT _dmarc.filery.app @chin.ns.cloudflare.com
```

**Run a known-positive control first** (`_dmarc.mantek.io` is a good one), so an empty
answer can be told apart from a blind checker.

**Check record COUNT, not just content.** One record per name. Two SPF records is a
permerror; two `_dmarc` records means DMARC is skipped; both fail silently.

**For the DKIM wildcard, query an arbitrary selector**, not the literal `*` name:

```bash
dig +short TXT whatever-nobody-registered._domainkey.filery.app @chin.ns.cloudflare.com
```

Existing and matching are different claims.

---

## Hosting, as actually deployed

The site is a **Cloudflare Pages** project, direct-upload from `site/` in this repo.
Production URL **https://filery.pages.dev**.

⚠️ **The project is named `filery-website`, not `filery`.** It was created as `filery`
and renamed in the dashboard to match `mantekio-website` and `nwcuaenet-website`.
Deploying with the old name fails with a misleading **"Project not found"** while the
site is plainly live. The command is:

```bash
wrangler pages deploy site --project-name=filery-website --branch=main
```

⚠️ **Pages serves `index.html` for unknown paths unless a `404.html` exists.** Before
one was added, `/robots.txt` and `/sitemap.xml` each returned the homepage with a
**200**, and every mistyped URL looked to a crawler like duplicate content. `site/`
now holds a real `404.html`, `robots.txt` and `sitemap.xml`. Verify with:

```bash
curl -o /dev/null -w '%{http_code}\n' https://www.filery.app/no/such/page   # must be 404
```

⚠️ **A `dig` trap at the apex, which nearly caused a live outage.** `dig` shows A and
AAAA records at `filery.app` and no CNAME, which reads like a stray placeholder record.
It is not. That is Cloudflare **flattening the apex CNAME**, the correct and expected
behaviour. Deleting those "A records" deletes the real apex CNAME and takes the site
down. Read the DNS table in the dashboard before concluding anything from `dig` at an
apex.

ℹ️ **Why the apex hung on "Verifying".** A redirect rule was intercepting the apex and
301ing it away before Pages could confirm the hostname routed to the project, so
verification could never succeed. The fix: disable the rule, re-add the custom domain,
let it go Active, then re-enable the rule.

### Canonical metadata lives in the page too

`site/index.html` carries `rel=canonical`, `og:url` and `og:image` pointing at
**www**. If the canonical form is ever changed, change these with it or the page will
contradict the redirect.
