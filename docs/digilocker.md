# DigiLocker: who can integrate, and how

Looked up on 8 October 2026 from the primary documents linked below. Not built; kept here for when it is.

## Who can integrate

FamilyOS would register as a **Requester** (an organisation that reads documents with the person's consent). The Partner Organisation Onboarding SOP sets the eligibility:

- Registered in India under MCA, MSME, Startup India, the Societies Act, the Companies Act, the Partnership Act, or as a Trust.
- "Demonstrable experience in providing online services to Indian citizens."
- Listed as eligible: central and state government organisations, **all private organisations**, public limited companies, PSUs, partnership firms, **proprietorship firms**, societies and trusts.
- A functional website that shows the nature, type and mode of the online service delivered to citizens.
- An authorisation from the appropriate authority of the organisation, and official domain email ids.

No fee is mentioned in the SOP.

## How onboarding goes

Through API Setu: create a partner account with an authorised representative's email, a verification call, sign the Terms of Use for Requesters, then technical integration with the onboarding team, testing, and go-live. Steps named in the SOP: identification, evaluation, verification, agreement, technical integration, testing, launch, ongoing support.

## What the API gives

Standard OAuth 2.0 (authorisation code):

- `https://api.digitallocker.gov.in/public/oauth2/1/authorize` and `/public/oauth2/1/token`; the token carries scopes per document class (for example `files.issueddocs`, `file.partners/DRVLC` for a driving licence, `file.partners/PANCR` for PAN).
- Issued documents: `/public/oauth2/2/files/issued` returns each document's `uri`, five-character `doctype`, description, `issuerid` and issuer name, and mime (`application/pdf` or `application/xml`).
- A file API fetches a document by its URI as PDF or XML.
- Pull document: `/public/oauth2/1/pull/pulldocument` fetches a document from an issuer into the person's locker using that issuer's search parameters (for a vehicle, the registration number), after a consent text that must be shown verbatim.

## Insurance in DigiLocker

IRDAI's circular of 9 February 2021 advised all insurers to enable their IT systems to issue policies into DigiLocker. Which insurers actually issue there varies; a person can also upload a policy PDF themselves, which a Requester can read with the `files.uploadeddocs` scope.

## Where it would fit

One consent, then the household's RC, driving licences, PAN and issued policies arrive as notices and the reader files their dates. It replaces downloading a policy PDF from an aggregator's app and sharing it by hand. Needs the Documents card (a structured record of a policy or a vehicle) to hold what comes back.

## Sources

- API Setu DigiLocker page (links to the spec, terms, SOP, signup): https://apisetu.gov.in/digilocker
- Partner Organisation Onboarding SOP: https://cf-media.api-setu.in/resources/Partners-SOP.pdf
- Requester API Specification v1.12 (Oct 2023): https://cf-media.api-setu.in/resources/Requester-APISpecification-V1_12.pdf
- Terms of Use for Requesters (June 2025): https://cf-media.api-setu.in/resources/DigiLocker-Terms-of-User-Requester-june-2025.pdf
- IRDAI advisory via PIB: https://www.pib.gov.in/Pressreleaseshare.aspx?PRID=1697372
