# Payments: how FamilyOS would pay, if and when a guardian switches it on (20 Oct 2026)

A design note, not built. Payments stay off by default and behind the guardian switch (see docs/todo.md, "Direction"). Every claim about a provider below was read on
20 Oct 2026 from the provider's page or press coverage; none is independently confirmed, and the places where sources disagree are marked.

## The rule that does not change

FamilyOS never holds money and never holds a card number. A model reads and proposes; a guardian approves exactly what was shown (the errand's fingerprint); a rail executes
inside a limit the guardian set. NPCI's chairman put the same split in one line: decision making and execution must remain separate.

## India: UPI first

- **UPI Reserve Pay** (Razorpay lists it as live): the user consents once and sets a spend limit per merchant; an agent then pays inside it without a PIN each time; the user sees
  each payment and can revoke at any time. One report gives a cap of about Rs 10,000 for up to 90 days.
- **UPI Circle** (Razorpay: "coming soon"): a primary user delegates to another user, which can be an agent. Third-party guides give Rs 5,000 per payment and Rs 15,000 a month for a
  delegate, partial delegation asking the primary user each time. The NPCI circular itself was not found.
- **NPCI Unified Agent Protocol** is reported, not final: registering and verifying agents on UPI, built on the two above. Agent identity, liability and disputes were not defined in
  anything read. Do not build against it; watch it.
- Pilots, from press: ChatGPT (October 2025, with Razorpay and NPCI) and Claude (February 2026), both on Reserve Pay.

Plan: the guardian taps, the family's own UPI app pays, as today. When Reserve Pay is open to us, the guardian sets a per-payee limit once and FamilyOS pays inside it. We stay out of
the money flow.

## Outside India: a one-time card, only for a site that takes nothing else

A single-use virtual card per errand, capped at the approved amount, closes the moment it is used. Which provider is **not settled**: Stripe's own docs say new Indian businesses join
by invite, and nothing read says Issuing is open there or in the UAE; Airwallex sells single-use cards by API but its pages do not name India or the UAE; nothing was found for Lithic,
Marqeta, Rain or Wio. A non-bank issuer in India probably needs an Indian bank or an RBI-approved partner (not checked against the current rule). Questions to put to each provider
in writing: which countries are served for issuing, whether the entity must be registered there, and whether the card is issued on a local or foreign BIN.

## Our own limits, on top of the rail's

The rail's limit is a backstop, not the policy. FamilyOS also enforces, before anything is sent:

1. the amount the guardian approved for this errand, never a model's number;
2. a per-day and per-month ceiling for the household;
3. a guardian tap for any new payee, and for anything over a threshold the household sets;
4. a payee that came from a person or from authenticated mail (`paylinks.upi_trusted`), never from a group message, a share or a page the run read;
5. every payment written to the audit log with who approved what, and one tap to revoke the standing consent.

## To ask

- Razorpay: who can integrate Reserve Pay as an agent, and can a household use it for a child's school fees?
- Airwallex and Stripe: the issuing questions above.

## Sources (read 20 Oct 2026)

- razorpay.com/agentic-payments/
- thepaypers.com, "Razorpay and NPCI launch agentic payments on Claude"
- onmanorama.com, ChatGPT agentic payments pilot (9 Oct 2025)
- outlookbusiness.com and inc42.com, NPCI Unified Agent Protocol
- revrag.ai, NPCI Unified Agent Protocol blog (a vendor's post; its dates for the future are the author's guesses)
- stripe.com/docs/india-exports; airwallex.com issuing pages; razorpay.com/blog/what-is-upi-circle/
