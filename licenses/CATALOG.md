# Aegean License Catalog

What AegeanWorks offers, what each license gives a user, and which one a project should carry.
The operative texts are the files beside this catalog; this page is the map, not a substitute.

| License | Free use | Redistribution | Commercial | AI training | DRM-free | Patent grant | OSI open source |
|---|---|---|---|---|---|---|---|
| **AL-1.1** — Aegean License 1.1 | One individual, private non-commercial use | No | ACL-1.0 + certificate | No | n/a | Yes, personal use only | No |
| **AGL-1.1** — Aegean Game License 1.1 | Personal play, streaming, modding, free mods | Free mods only | ACL-1.0 + certificate + asset grant | No | **Yes, contractual covenant** | Yes, for AGL uses | No |
| **ASL-1.1** — Aegean Science License 1.1 | Non-commercial research, teaching, publication, reproducibility | Published research modifications | ACL-1.0 + certificate + data/weights grant | Non-commercial research only | n/a | Yes, for ASL uses | No |
| **ACL-1.0** — Aegean Commercial License 1.0 | 28-day non-production evaluation, once per company group | Within a product, per certificate | Paid, scoped by certificate | Only with `ai-training` Allowance | Per agreement | Yes | No |
| **Restricted notice** | Nobody | No | Separate written agreement | No | n/a | No | No |

"OSI open source" means the Open Source Initiative's Definition, which forbids restricting a field
of endeavour (including commercial use). AL-1.1, AGL-1.1 and ASL-1.1 restrict commercial use, so
they are **source-available**, not open source. The catalog never calls them open source. The 1.0
texts remain in this folder for Versions released under them; 1.1 adds an explicit security-research
permission, moral-rights and data-protection terms, and a GPL/AGPL compatibility statement.

## Which one should a project use?

- **Software, tools, libraries, apps** → AL-1.1 (AIKit's default). Commercial users buy ACL-1.0.
- **Games, interactive fiction, engines, level packs** → AGL-1.1. It adds the DRM-free covenant,
  streaming/recording permission, private servers, modding, and an explicit asset boundary.
- **Research code, notebooks, simulations, benchmarks** → ASL-1.1. It adds publication,
  reproducibility sharing, non-commercial text/data mining and non-commercial ML training.
- **Datasets and model weights** → a project may list them under ASL-1.1 when it owns them; a
  separate data/weights grant is still needed for commercial use. Third-party data keeps its own
  license.
- **Anything valuable enough that public distribution is the risk** → the restricted tier, not a
  public license. It is a forward-only cutoff; earlier releases are not revoked.

A project that mixes domains should choose the license of its **primary deliverable**. A game
engine with a research paper uses AGL-1.1 for the game and can publish the paper's code under
ASL-1.1 separately. Never stack two LICENSE files in one repository: one project, one tier.

## What every license keeps

- **No AI training** outside the science grant or an `ai-training` Allowance.
- **No trademarks**: names, logos and project marks are not licensed.
- **No warranty or support**: pure copyright grants, AS IS, no SLA.
- **No sublicensing or standalone resale.**
- **Forward-only restriction**: a later version may be All Rights Reserved; a copy already
  granted keeps its grant.
- **Assets are separate**: code and logic are licensed; art, audio, datasets and model weights need
  a grant under [ASSET_POLICY.md](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/ASSET_POLICY.md)
  or an explicit asset manifest.
- **Contributions** need the [AegeanWorks CLA](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/CONTRIBUTING_CLA.md)
  so the licensor can relicense them.
- **ACL-1.0 definitions:** ACL-1.0 names AL-1.0 for its definitions; AL-1.1 keeps those definitions
  unchanged, so an existing certificate still reads correctly.

## Strengths

- **One base, three domains.** AL-1.1 is the base; AGL-1.1 and ASL-1.1 add only the clauses their
  domain needs, so the family stays coherent and reviewable.
- **A real commercial path.** Every free tier points to ACL-1.0 and a certificate in the public
  register; the certificate is scoped, time-limited and verifiable offline.
- **A patent grant.** All three free tiers grant patent claims the licensor can license, with a
  patent-defense termination. This is what CC BY-NC lacks and why CC itself recommends against CC
  for software.
- **Security research is allowed.** AL-1.1 makes good-faith security research and coordinated
  disclosure explicit, so the no-circumvention clause cannot be read as a gag on reporting a
  vulnerability.
- **Moral rights and data protection are addressed.** AL-1.1 keeps authors' moral rights and
  requires compliance with data-protection and consumer law instead of silently excluding them.
- **A DRM-free covenant.** AGL-1.1 is not just "we happen not to ship DRM": it promises no
  mandatory client, account binding or activation, forbids a distributor adding DRM, and keeps an
  offline build playable after online services end. This is close to GOG's DRM-free promise, but
  written as a license condition.
- **A science-specific grant.** ASL-1.1 permits publication, reproducibility packages and
  non-commercial ML training without pretending the material is open source or unrestricted.
- **Asset and data boundaries.** The license says what is code, what is an asset/dataset, and what
  needs a separate grant, instead of silently licensing a creator's art with the code.
- **Machine-readable analysis.** AIKit reads project markers, reports confidence and evidence,
  and can apply a high-confidence choice before publishing. Tags and license are chosen from the
  project, not guessed from its name.

## Weaknesses and risks

- **Non-commercial is fact-specific.** "Primarily intended for commercial advantage" is the
  Creative Commons formulation; a court applies it to the facts. A funded academic project, a
  startup evaluating a product, or a monetized channel can all be argued either way. The text
  states examples, but it cannot remove the uncertainty.
- **Custom licenses have adoption friction.** SPDX has no official identifier, so tools see
  `LicenseRef-AL-1.1`, `LicenseRef-AGL-1.1` or `LicenseRef-ASL-1.1` and cannot map them to a known
  policy. That is valid SPDX, but it needs the license text beside the code.
- **Not GPL/AGPL compatible.** The non-commercial restriction is incompatible with GPL-3.0 and
  AGPL-3.0. AL-1.1 says so; a project that needs copyleft compatibility needs a separate permissive
  license, a dual-license path, or a written permission.
- **A license binds recipients, not the world.** A platform, a search index or a person who never
  accepts the terms is not automatically bound. The restricted tier and the register are the
  practical enforcement layers.
- **DRM-free is a promise about builds, not platforms.** A storefront can still require an account
  to download; a console can still impose its own measures. AGL-1.1 says so instead of overpromising.
- **Anti-cheat and multiplayer need judgment.** The carve-out protects legitimate multiplayer
  integrity, but a court or a platform may read "anti-consumer" differently. The clause is written
  to distinguish single-player rights from cheating enforcement.
- **Assets and data are not covered by ACL-1.0.** Commercial use of art, audio, datasets or model
  weights needs a separate grant. Until that grant exists, a commercial certificate covers code
  only.
- **No use-restriction list like OpenRAIL.** ASL-1.1 has a short lawful/ethical clause, not the
  OpenRAIL attachment of prohibited uses. A project that needs a RAIL-style list for model weights
  should add an OpenRAIL-M/D attachment; ASL-1.1 alone is not one.
- **No security, support or update commitment.** The licenses say AS IS. A paid customer may expect
  an SLA; that belongs in the Order Form, not the license.
- **No legal review yet.** These are drafts until counsel reviews them. The counsel note in each
  text is deliberate, not boilerplate.

## How this compares with common licenses

- **Creative Commons BY-NC 4.0** is the reference for a non-commercial grant, and its definition of
  "commercial" informs AGL-1.1 and ASL-1.1. CC itself recommends against using CC licenses for
  software because they do not address source distribution or patents. ASL-1.1 keeps CC's
  non-commercial idea and adds a patent grant, source terms and a data boundary.
- **PolyForm Noncommercial 1.0.0** is the closest standard source-available non-commercial
  software license. It grants use, changes, distribution and a patent license for non-commercial
  purposes. AL-1.1 is stricter (no distribution at all); AGL-1.1 and ASL-1.1 are closer to
  PolyForm in spirit but add domain rights. PolyForm's patent-defense and 32-day cure language is
  a good model; AL-1.1 uses a 30-day cure and the same patent-defense idea.
- **OpenRAIL-M / OpenRAIL-D** add a list of prohibited uses and require the restrictions to travel
  with derivatives. They are a better fit for model weights or sensitive datasets than a general
  research license. ASL-1.1 has a short lawful/ethical clause, not the full RAIL attachment.
- **BSL 1.1, Elastic License 2.0 and SSPL** are source-available licenses that restrict competing
  or hosted use and, for BSL, convert to open source after a change date. AL-1.1 is simpler and
  stricter; ACL-1.0 is the paid path instead of a delayed open-source conversion.
- **MIT, Apache-2.0, GPL and AGPL** permit commercial use and therefore fail the "personal use
  only" goal. Apache-2.0's patent grant is the model for AGL-1.1 and ASL-1.1; its trademark and
  notice clauses are the model for AL-1.1's notice rules.
- **GOG's DRM-free model** is a distribution promise (offline installers, no client required,
  access after a store shutdown), not a license. AGL-1.1 turns the same promise into a condition
  on the licensor and on anyone who distributes a permitted mod or patch.

## Adjacent licenses and why they are not the family

- **Fair Source / FSL-1.1 / BSL-1.1.** Functional Source License 1.1 grants source use except a
  competing use and converts to MIT or Apache-2.0 after two years; BSL does the same with a
  four-year default and a change date. AegeanWorks has no delayed open-source switch: AL-AGL-ASL
  stay source-available and commercial use is paid from day one. A project that wants eventual
  open source should choose FSL or BSL explicitly, not an Aegean text.
- **PolyForm Internal Use / Perimeter.** PolyForm Internal Use permits internal business use;
  Perimeter permits everything except a competing product. ACL-1.0 charges for internal business
  use, which is a deliberate commercial choice; a customer that needs free internal use should be
  offered PolyForm Internal Use or a negotiated ACL scope instead.
- **Llama 3 Community / Gemma Terms / OpenRAIL-M / BLOOM RAIL.** Model licenses add
  acceptable-use rules, monthly-active-user thresholds, naming and attribution, and output terms.
  ASL-1.1 covers non-commercial research and the data/weights addendum covers commercial use, but
  there is no MAU threshold or model-specific acceptable-use schedule; the OpenRAIL attachment is
  the starting point for one.
- **CERN-OHL-P/W/S 2.0.** The CERN Open Hardware Licence covers design files and manufactured
  hardware. The Aegean family covers software, content and data, not hardware; a PCB, enclosure or
  mechanical design needs CERN-OHL or another hardware license.
- **ODbL 1.0 / CDLA-Permissive / CDLA-Sharing.** ODbL adds database share-alike; CDLA separates
  data from software. ASL-1.1 and the data/weights addendum grant Project Data but do not impose a
  database copyleft. A dataset that must stay open should use ODbL or CDLA-Sharing.
- **CC BY 4.0 / CC BY-SA 4.0.** Creative Commons is designed for content and documentation. The
  Aegean licenses cover a project's docs with its code; a docs-only corpus that should be reusable
  under CC BY needs a separate documentation notice.
- **SPDX and REUSE.** An Aegean text is a custom `LicenseRef-*`, not an OSI identifier. New AIKit
  projects get a `REUSE.toml` and `LICENSES/LicenseRef-*.txt`; add per-file headers for a tree that
  mixes licenses. The license text still has to travel with the code.

## Gaps exposed by these comparisons

1. **No delayed-open-source transition** like FSL/BSL. A user who wants eventual open source must
   choose another license or negotiate a future grant.
2. **Internal business use is paid.** PolyForm Internal Use is the standard free alternative; the
   ACL evaluation is only 28 days and non-production.
3. **No model-use schedule.** Llama/Gemma/OpenRAIL have acceptable-use and MAU terms; the OpenRAIL
   attachment is a draft, not an operative model license.
4. **No hardware license.** CERN-OHL covers designs; the family does not.
5. **No data share-alike.** ODbL/CDLA-Sharing are not part of the family.
6. **No docs-only CC option.** CC BY/BY-SA remain better for a standalone documentation corpus.
7. **Per-file SPDX headers** are not added to existing source files; the generated `REUSE.toml`
   and `LICENSES/` are the baseline, and a file copied from a third party needs its own header.

## Drafted instruments

These close the structural gaps without pretending to be operative before counsel review:

1. [Trademark Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/TRADEMARK-POLICY.md) — names, badges and nominative use.
2. [Game Asset Addendum](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/commercial/GAME-ASSET-ADDENDUM-DRAFT.md) — commercial art/audio grant.
3. [Data and Model Weights Addendum](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/commercial/DATA-WEIGHTS-ADDENDUM-DRAFT.md) — commercial datasets and trained weights.
4. [Security Disclosure Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/policies/SECURITY-DISCLOSURE.md)
   and [Support Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/policies/SUPPORT-POLICY.md).
5. [Provenance Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/policies/PROVENANCE-POLICY.md)
   for assets, data and model weights.
6. [OpenRAIL-style Attachment](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/OPENRAIL-ATTACHMENT-DRAFT.md) for sensitive models or datasets.
7. [Dual-License Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/policies/DUAL-LICENSE-POLICY.md)
   for a written permissive or GPL-compatible grant.
8. [Permissive Grant Template](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/commercial/PERMISSIVE-GRANT-TEMPLATE.md)
   for a named MIT/Apache-2.0 grant.
9. [Security SLA Exhibit](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/commercial/SECURITY-SLA-EXHIBIT-DRAFT.md)
   for a commercial response commitment.
10. [SPDX and REUSE Policy](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/policies/SPDX-REUSE-POLICY.md)
   for machine-readable license metadata; new AIKit projects get `REUSE.toml` and `LICENSES/`.

## What is still missing

1. **Counsel review** of AL-1.1, AGL-1.1 and ASL-1.1 and of every draft above; see the
   [Legal Review Checklist](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/LEGAL-REVIEW-CHECKLIST.md).
2. **Operative adoption**: the asset, data/weights and OpenRAIL attachments become binding only when
   an Order Form or a project LICENSE names them; the policy documents are statements of practice,
   not a grant.
3. **A bundled copy of the standard permissive license text** for a granted dual-license request;
   the grant letter template is included, but the recipient must attach the MIT or Apache-2.0 text.
4. **A trademark registration and watch strategy** if the marks are used commercially outside
   Türkiye.
5. **A public security-response SLA** if a commercial customer requires one; today the response
   targets are best-effort.

## Archived drafts

`AL-PU-1.0-DRAFT.md`, `AECL-1.0.md` and `COMMERCIAL-LICENSE-TEMPLATE-DRAFT.md` are superseded
drafts kept for history. They are not operative and must never be copied into a project. The
operative texts are AL-1.1, AGL-1.1, ASL-1.1, ACL-1.0 and the restricted notice.

## Legal review

Before the first paid issuance, counsel reviews the operative texts against
[LEGAL-REVIEW-CHECKLIST.md](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/LEGAL-REVIEW-CHECKLIST.md).
The checklist is a hand-off, not legal advice; a version is release-ready only after counsel signs
the applicable items.

## Verification

Every commercial certificate is checked against the public register
([`licenses/issued.json`](https://github.com/AegeanWorks/Aegean-Licensing/blob/master/licenses/issued.json)).
The digest proves the record was not altered; only AegeanWorks' private signing key proves
authenticity. Personal-use licenses (AL, AGL, ASL) need no certificate. Commercial use always does.

Contact: `aegean-licensing@proton.me`
