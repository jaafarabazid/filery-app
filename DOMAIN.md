# Domain, DNS and launch checklist

Everything about **filery.app** as an internet property: what is registered, what is
configured, what was decided and why, and what still has to happen before launch.

Written 2026-08-06, updated 2026-08-10 after launch. This lives in the repo
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

ℹ️ There is also an **HTTP to HTTPS** redirect rule, which is near-dead weight on this
TLD since `.app` is HSTS-preloaded and browsers never send plaintext. Harmless.
Cloudflare's **Always Use HTTPS** toggle (SSL/TLS, Edge Certificates) is the correct
instrument for that anyway.

---

## Launch: done, and what is still open

✅ **Launched 2026-08-09/10.** A landing page, 404, robots.txt and sitemap are live,
both hostnames resolve through Cloudflare, and the apex to www redirect is working.
The mail hardening above survived the launch untouched, verified by `dig`.

Still open:

1. **Verify the live redirect preserves path and query string.** It has only been
   checked at the root:
   ```bash
   curl -sI https://filery.app/some/path?a=1 | grep -i '^location:'
   ```
   Expect `https://www.filery.app/some/path?a=1`. A missing path or query string means
   the wildcard replacement or the preserve-query-string checkbox is wrong, which is
   invisible when you only test the homepage.
2. **Set the AI crawler policy deliberately.** The zone still sits on Cloudflare's
   default, "Block AI training bots: Do not block". mantek.io currently blocks AI
   training while allowing search and answer bots, though that is itself under review.
   Either way this should be a decision, not a default.
3. 🔥 **The trademark is still uncleared**, and it still blocks a public `v1.0.0`. A
   live site does not change that: a landing page is not a downloadable binary under
   the name.

---

## Still blocking a public v1.0.0

🔥 **The trademark has never been cleared.** It needs a human: every register and
mirror blocks automated access, so it was never actually searched, and saying
otherwise would dress an inference up as a search. It needs the USPTO check plus a UAE
search.

**Do not tag a public v1.0.0 until that is done.** A public release with downloadable
binaries is a hard, effectively permanent commitment to the name. Registering the
domain first was deliberate and is not a contradiction: it is cheap, it stops someone
else taking the name while the mark is checked, and it commits nothing publicly.

---

## Verifying any of this

⚠️ **The wrangler OAuth token cannot do this work.** Its scope is `zone (read)`, which
covers zone metadata only. **`/dns_records` and `/rulesets` both return
`Authentication error`**, and there is no write scope at all, so neither DNS records
nor Rules can be read back or changed through it. Writing needs a purpose-made token
(My Profile, API Tokens, "Edit zone DNS" template, Zone Resources restricted to
filery.app), otherwise it is the dashboard by hand.

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
