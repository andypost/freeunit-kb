---
title: "Inbound Chinese domain-name registration scam (freeunit.cn pitch)"
description: "Template 'registrar' email claiming a CN company applied for freeunit .cn domains — a long-running slamming scam; whois facts and response policy"
format: "open-knowledge-format-v1"
updated: "2026-09-28"
maintainer: "andypost"
---

# Inbound CN domain-registration scam ("freeunit" keyword pitch)

## What arrived

Unsolicited email to FreeUnit (2026-09-28) from "Frank Lee (Mr.), Services & Operating
Manager of a Network Service Company ... domain name registration center". Claims:

- an application was received **from "Zhenyi Holdings Ltd"** to register `freeunit` as its
  "internet keyword" plus `freeunit.cn`, `freeunit.com.cn`, `freeunit.net.cn`, `freeunit.org.cn`;
- this "conflicts with your company name or trademark", so please confirm whether FreeUnit
  is affiliated with that CN company.
- Address given: Room 808, No. 818 Yulin Road, Shanghai 200082. T: 0086-134-8281-9147,
  Tel: 0086-21-6191-8696, Fax: 0086-21-6191-8697.

## Verdict: scam template, not a real registrar, not a real applicant

This is the long-documented **"Chinese domain name registration scam"** / *slamming*
scheme (in the wild since ~2005, still active in 2026). Nothing about it is FreeUnit-specific.

Tell-tale signs, all present:

| Signal | Observation |
|---|---|
| Reused phone/fax | `+86-21-6191-8696` / `-8697` and mobile `0086-134-8281-9147` appear across mass campaigns by the same template ("YGCHINA", "China Registry", "Domain Registry China") |
| Reused title | "Services & Operating Manager" is the standard signature slot in this template (cf. Clark Lee, Mike Zhang, Scott Wang, Charles Zhang) |
| Rotating address | Same crew has used 1399 Jinqiao Rd 200120, Yujing Bldg Jihe Rd 201107, Yulin Rd 200082 — all Shanghai, all unverifiable |
| Rotating names | Both parties rotate per send: fake applicant ("Zhenyi Holdings Ltd", earlier: Hua Hai, Baotong, Hongxiang, Shanghong, Yisun, Leigo, Xianda Ltd) and fake sender |
| Invented service | "Internet keyword" / "internet trademark" is not a trademark right anywhere, and CNNIC does not run such a system |
| Fake process | There is **no application/dispute period** for domain registration. First-come, first-served. Nobody has to be "approved" |
| Urgency + forward-to-CEO | Pressure script ("this is urgent") to bypass technical staff |

## Hard facts checked (whois, CNNIC, 2026-09-28)

- `freeunit.cn` — **already registered since 2017-01-06**, registrant is an unrelated Chinese
  company (Xiamen; contact `dwt@duoweitree.com`), registrar Xiamen 35.com
  (`ns1-4.35.net`), expiry **2031-01-06**, `clientTransferProhibited`.
  So nobody can "apply for freeunit.cn" — the claim is impossible on its face.
- `freeunit.com.cn` — **no matching record** (unregistered).
- `freeunit.net.cn` — **no matching record** (unregistered).
- `freeunit.org.cn` — **no matching record** (unregistered).
- "Zhenyi Holdings": no traceable company linked to this email. A generic
  "ZHENYI Holdings Limited" appears in the 2022 BVI gazette, but nothing connects it to
  the message — the applicant name is throwaway boilerplate.

## What happens if you reply

Phase 2 (2-4 days later) is a second email, supposedly from the applicant company itself,
insisting the registration will proceed, followed by an offer from "Frank" to
"protect"/register the names for you during a "dispute period" — at $300-$3000 per name
(a .cn costs ~$10-30 at a real registrar), often with a bogus invoice for merely
answering, and frequently the domains are never actually registered.

## Response policy for FreeUnit

1. **Do not reply.** No reply, no question, no "who are you". Replying confirms a live
   address and moves us to phase 2 / fake invoicing. Mark as spam.
2. **Delete.** Nothing in FreeUnit's plan depends on `freeunit.*.cn`.
3. **If China-facing hosting ever matters**, register through a CNNIC-accredited registrar
   (e.g. Alibaba Cloud, Namecheap/Gandi for .cn resale) at normal rates — never through an
   unsolicited contact.
4. **Optional cheap defensive move** if we ever want the orphans: `freeunit.com.cn`,
   `freeunit.net.cn`, `freeunit.org.cn` are currently free and cost single-digit USD/yr each.
   Not required: FreeUnit does not trade in China, and `freeunit.cn` cannot be obtained
   anyway (held to 2031).
5. **Technical hygiene only if a real lookalike ever appears**: SPF/DKIM/DMARC on
   freeunit.org, registrar lock on core domains, and monitoring of certificate-transparency
   logs for `freeunit*` lookalikes.

## Reference material

- Documented as a recurring scam by registrars/ISPs and security press; the identical
  template text reappears for hundreds of domains per year, including the same phone and fax
  numbers and the same "Services & Operating Manager" signature.
- Analogue: the FreeUnit project gets such mail because the brand name is short and
  dictionary-like, not because of any real CN trademark filing.
