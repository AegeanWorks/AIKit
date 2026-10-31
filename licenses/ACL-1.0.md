# Aegean Commercial License 1.0 (ACL-1.0)

**Version 1.0 — October 2026**
**Licensor**: AegeanWorks (`aegean-licensing@proton.me`), Türkiye
**SPDX identifier**: `LicenseRef-ACL-1.0`
**Canonical text**: this document. The names “Aegean-E” and “AegeanWorks” refer to the same
licensor; “Aegean-E” is a legacy brand alias used in earlier documents. This agreement was
drafted under the name “AegeanWorks Commercial License Agreement (AECL-1.0)”; no certificate was
issued under that name.

**Acceptance.** Every term of this Agreement is both an obligation and a condition of the
license. Use outside the Scope, the Term or Section 3 is outside the license and is unlicensed
use of the Licensed Software.

> **Counsel note.** This is the operative commercial agreement, but it must be reviewed by
> qualified counsel in the Licensor's jurisdiction before the first paid issuance. Bracketed
> items, if any, identify facts the Licensor must confirm; they are not optional terms.

---

## 1. Definitions

1. **“Licensor”** means AegeanWorks, the operator of the AegeanWorks and Aegean-E projects.
2. **“Licensee”** means the legal entity or individual identified on a valid License Grant
   Certificate, together with its Affiliates covered by that certificate.
3. **“Affiliate”** means an entity that controls, is controlled by, or is under common control
   with the Licensee, where control means more than 50% of the voting interests or equivalent
   authority.
4. **“Licensed Software”** means the specific AegeanWorks projects, repositories, modules, or
   packages identified in the License Grant Certificate.
5. **“License Grant Certificate”** means the digital record issued by Licensor (JSON and
   Markdown) bearing a unique certificate id, the licensee identity, the tier, the term, the
   Scope, any Allowances and a SHA-256 integrity digest, and listed in Licensor's public register
   under Section 6.
6. **“Tier”** means the commercial package named on the certificate (Tier1, Tier2, or Tier3),
   as described in `COMMERCIAL.md`.
7. **“Scope”** means the permitted commercial use named on the certificate, drawn from the
   controlled vocabulary in `licenses/terms.json`.
8. **“Term”** means the period stated on the certificate, beginning on the Effective Date and
   ending on the Expiration Date, or perpetual if the certificate says so.
9. **“Effective Date”** means the issuance date stated on the certificate.
10. **“Permitted Modifications”** means changes, enhancements, adaptations, or extensions of the
    Licensed Software made by or on behalf of Licensee.
11. **“Order Form”** means the written or digital order agreed by the parties that identifies the
    licensee, tier, projects, scope, fees, term, and payment schedule.
12. **“Allowance”** means an exception from Section 3 that applies only when the certificate
    lists it by name, drawn from the controlled vocabulary in `licenses/terms.json`:
    `ai-training` (Section 3.9) and `hosted-service` (Section 3.10).
13. **“Competing Product”** means any product or service, paid or free, that offers the Licensed
    Software, or substantially the same functionality, as a substitute for the Licensed Software
    or for a product Licensor offers with it. A product marketed as a practical substitute is a
    Competing Product.
14. **“Personnel”** means Licensee's employees and individual contractors who use the Licensed
    Software only on Licensee's behalf.

## 2. Grant of Commercial Rights

Subject to this Agreement, the Order Form, and a valid License Grant Certificate, Licensor
grants Licensee a worldwide, non-exclusive, non-transferable right (except as stated in
Section 9) to:

1. **Commercial use.** Use, run, modify, compile, and execute the Licensed Software for
   Commercial or Organizational Use as defined in the Aegean License 1.0 (AL-1.0), within the
   Scope, free of AL-1.0's personal-use limits. For a version Licensor once released under an
   earlier copyleft license, including GNU AGPL-3.0, this Agreement also waives that license's
   source-disclosure obligations for Licensee.
2. **Proprietary integration and closed-source SaaS.** Incorporate the Licensed Software into
   proprietary, closed-source applications, hosted services, cloud APIs, microservices, and
   client-side software without disclosing Licensee's source code or proprietary adaptations.
3. **Closed redistribution.** Distribute binaries or bundled packages containing the Licensed
   Software as part of Licensee's commercial offerings, without an obligation to disclose
   Licensee's product source or modifications. Redistribution of the Licensed Software as a
   standalone developer product or as part of a Competing Product is excluded by Section 3.
   Licensee's customers may use the Licensed Software only as part of Licensee's product, under
   terms at least as protective of Licensor as this Agreement, which forbid extracting,
   redistributing, or reverse engineering it to use it apart from that product. Licensee is
   responsible for its customers' compliance with those terms.
4. **Limited patent grant.** Licensor grants Licensee a non-exclusive, worldwide, royalty-free
   license under those patent claims Licensor owns or controls that are necessarily infringed
   by the Licensed Software as delivered by Licensor, solely to exercise the rights granted in
   this Section. This grant does not extend to combinations with Licensee's own products or to
   modifications. It terminates if Licensee initiates a patent claim alleging that the Licensed
   Software infringes a patent.
5. **Deployed-version permanence.** Versions of the Licensed Software that Licensee lawfully
   deployed in production during the Term may continue to be used in production after the
   Expiration Date. The Term limits the right to obtain and deploy *new* versions; it does not
   revoke rights in already-deployed versions.
6. **Personnel.** Licensee's Personnel may exercise these rights on Licensee's behalf. Licensee
   may share the Licensed Software's source only with its Personnel, under written
   confidentiality obligations, and is responsible for their compliance with this Agreement.

## 3. Conditions and Boundaries

1. **Notice retention.** Licensee must preserve copyright, license, and attribution notices in
   the Licensed Software and in documentation distributed with it. Licensee may place its own
   notices alongside them but may not remove or obscure Licensor's notices.
2. **No standalone resale or competition.** Licensee may not resell, sublicense, rent, or
   distribute the Licensed Software on a standalone basis as a licensing platform or code broker,
   and may not use it to build, offer, or support a Competing Product. Distribution as part of
   Licensee's own non-competing product is permitted.
3. **No sublicensing.** Licensee may not grant third parties rights to the Licensed Software
   except as embedded in Licensee's permitted product, or to an Affiliate under Section 9.
4. **Trademarks.** No trademark, logo, trade dress, or project-name rights are granted. Accurate
   nominative references to the Licensed Software are permitted.
5. **Assets.** This Agreement covers software code and logic only. Non-code assets (art, audio,
   datasets, templates, model weights, brand imagery) are governed by `licenses/ASSET_POLICY.md`
   and require a separate written grant.
6. **Export and sanctions.** Licensee must comply with applicable export-control and sanctions
   laws and must not use the Licensed Software in prohibited destinations or activities.
7. **Lawful use.** Licensee is responsible for its own regulatory compliance, including data
   protection, medical, financial, and consumer-protection obligations.
8. **No circumvention.** Licensee must not move, change, disable, or circumvent any license
   check, license key, certificate verification, or other technical measure in the Licensed
   Software, and must not alter a License Grant Certificate.
9. **No AI training.** Licensee must not use the Licensed Software, or any part of it, to train,
   fine-tune, evaluate, or benchmark a machine-learning or artificial-intelligence model, or
   include it in a dataset for that purpose, unless the certificate lists the `ai-training`
   Allowance.
   Using AI coding assistants to read or edit Licensee's own licensed copy is not prohibited,
   provided the assistant's provider does not train on it.
10. **No hosted resale.** Licensee must not offer the Licensed Software to third parties as a
    hosted or managed service whose main value is the Licensed Software's own features, unless the
    certificate lists the `hosted-service` Allowance.
11. **Restricted versions.** If Licensor moves a project to its restricted tier, versions released
    after the cutoff are covered only if the certificate names them. Versions Licensee received
    before the cutoff stay licensed under Section 2.5.
12. **Your Company.** The license covers the Licensee and the Affiliates the certificate names.
    Use by any other entity, including another Affiliate, needs its own certificate.
13. **Modifications and feedback.** Licensee owns its Permitted Modifications, subject to
    Licensor's rights in the Licensed Software they modify; they may be used only under this
    Agreement. Licensee need not give Licensor feedback, but Licensor may freely use any
    suggestion or feedback Licensee chooses to give.
14. **Tier eligibility.** If Licensee stops meeting the eligibility of its Tier, for example by
    exceeding a revenue threshold, it must tell Licensor within 30 days and move to the
    applicable Tier at its next renewal, or within 60 days for a perpetual certificate.
15. **Use beyond the certificate.** Use beyond the certificate's projects, Scope, Allowances,
    Affiliates, or Term is unlicensed. If a compliance certification under Section 6.5 or any
    other evidence shows such use, Licensee must license it at Licensor's then-current fees,
    from the date the use began, without prejudice to Licensor's other remedies.

## 4. Fees, Payment, and Taxes

1. Fees, currency, payment method, and schedule are set out in the Order Form and agreed by the
   parties in writing. Commercial terms are arranged privately; no payment is collected through
   GitHub, this repository, or any public channel.
2. Payment is complete only when Licensor confirms receipt in writing. A certificate is issued
   only after the Order Form is settled and Licensor has confirmed that fact.
3. Fees are exclusive of taxes. Licensee bears applicable taxes, duties, and withholdings, and
   will provide a valid tax identifier where required.
4. Once a certificate has been issued, fees are non-refundable except where Licensor cannot issue
   a valid certificate for a settled order. In that case Licensor will issue the certificate or
   refund the amount received, using the method agreed in the Order Form.
5. Licensor may decline an order, or require additional verification, before issuing a
   certificate. No license arises from an inquiry, a quote, or an unpaid Order Form.

## 5. Term, Termination, and Survival

1. **Term.** The Term is stated on the certificate. If the certificate is perpetual, the Term
   does not expire.
2. **Termination for breach.** Licensor may terminate this Agreement if Licensee materially
   breaches it and does not cure the breach within 30 days after written notice. Non-payment,
   standalone resale, removal of notices, circumvention, AI training, and use outside the Scope
   are material breaches. A material breach after a cured one may be terminated at once, with no
   further cure period.
3. **Effect of termination.** On termination for breach, every right under this Agreement ends,
   including the right in Section 2.5 to keep using deployed versions: Licensee must stop all use
   and distribution of the Licensed Software and delete it, except copies the law requires it to
   keep. Section 2.5 protects only a Licensee whose Term expired, not one whose license was
   terminated. Licensor marks a terminated certificate revoked in the public register.
4. **Survival.** Sections 1, 3, 4.4, 5.3, 6, 7, 8, and 9 survive termination.

## 6. Verification and Authenticity

1. A certificate is evidence of the grant only if its id and digest are listed as valid in
   Licensor's public register (`licenses/issued.json` in the aegean-licensing repository), or
   Licensor confirms it in writing. The register lists no personal data.
2. The SHA-256 digest proves internal consistency (that the record was not altered); it is
   **not** proof of authenticity, because anyone can recompute a digest. The issuer signature is
   a keyed hash that only Licensor can check; Licensor never publishes its signing key.
3. Licensee and third parties may verify a certificate with
   `python -m aegean_licensing verify <certificate.json> --register licenses/issued.json` or by
   contacting `aegean-licensing@proton.me`.
4. A certificate whose cited terms digest does not match the published agreement, whose
   license type is unknown, whose tier is not defined by that agreement, or which the register
   lists as revoked is invalid.
5. **Compliance certification.** On Licensor's written request, no more than once a year,
   Licensee will confirm in writing within 30 days that its use stays within the certificate's
   projects, Scope and Term.
6. **Frozen text.** Licensor never changes the text of this version after the first certificate
   is issued under it. Changed terms are published as a new version with its own identifier;
   a certificate stays governed by the version it cites.

## 7. Disclaimer of Warranty

THE LICENSED SOFTWARE IS PROVIDED **“AS IS”**, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE, AND
NON-INFRINGEMENT. LICENSOR DOES NOT WARRANT THAT THE SOFTWARE WILL OPERATE UNINTERRUPTED,
ERROR-FREE, SECURE, OR MEET ANY REGULATORY REQUIREMENT. LICENSEE BEARS THE ENTIRE RISK OF USE.

## 8. Limitation of Liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW, LICENSOR AND ITS CONTRIBUTORS ARE NOT LIABLE FOR
INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, PUNITIVE, OR CONSEQUENTIAL DAMAGES, OR FOR LOST DATA,
PROFITS, REVENUE, OR GOODWILL. LICENSOR'S TOTAL AGGREGATE LIABILITY UNDER THIS AGREEMENT IS
LIMITED TO THE FEES ACTUALLY PAID BY LICENSEE FOR THE CERTIFICATE GIVING RISE TO THE CLAIM.
NOTHING IN THIS AGREEMENT LIMITS LIABILITY THAT APPLICABLE LAW DOES NOT ALLOW TO BE LIMITED.

## 9. Assignment and Change of Control

Licensee may assign this Agreement only to an Affiliate or to a successor of all or
substantially all of its business or assets, provided the assignee assumes this Agreement in
writing and Licensee notifies Licensor within 30 days. Any other assignment is void.

## 10. General

- **Governing law.** This Agreement is governed by the laws of the Republic of Türkiye, without
  regard to conflict-of-law rules.
- **Venue.** The courts of Istanbul, Türkiye, have exclusive jurisdiction, subject to any
  mandatory consumer protection rules.
- **Entire agreement.** This Agreement, the Order Form, the License Grant Certificate, and the
  documents they incorporate are the entire agreement on their subject and supersede prior
  discussions.
- **Order of precedence.** The certificate controls the licensee, tier, projects, scope, and
  term; the Order Form controls fees and payment; this Agreement controls the remaining terms.
  A document incorporated by reference controls only the subject it addresses.
- **Severability.** If a provision is unenforceable, it is limited to the minimum extent needed
  and the rest remains in effect.
- **No other rights.** This Agreement implies no right beyond those it expressly grants, and does
  not limit Licensor's right to license the Licensed Software to others on any terms.
- **Language.** This Agreement is written in English. A translation is for convenience only; if
  they differ, the English text controls.
- **No waiver.** A failure or delay in enforcing a provision is not a waiver.
- **Notices.** Notices to Licensor go to `aegean-licensing@proton.me`; notices to Licensee go
  to the contact address on the certificate. Notice is effective when sent with confirmation.
- **No third-party beneficiaries.** This Agreement creates no rights for anyone other than the
  parties.
- **No support or SLA.** Licensor has no obligation to provide support, maintenance, updates, or
  service levels unless a separate written agreement says otherwise.

---

**Contact:** `aegean-licensing@proton.me`
