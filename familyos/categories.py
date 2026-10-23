"""What kind of mail a notice is, from who sent it and what it is called.

The first real mailbox, 153 messages over 30 days, was 70 securities
notices, 14 food deliveries, 8 insurers' promotions, a dozen newsletters, and
perhaps twenty things a family would call a notice. The extractor read all
of them with the same seriousness, and a life insurer's "lock your premium
before the 21st" became a deadline on the brief beside the income-tax
intimation that actually had one.

So every notice gets a category before it is read, derived and never stored,
from the sending domain first and the subject second. It does three things:

- it is the tag a person sees in the inbox and can filter by;
- a **promotional** or **newsletter** notice may be read for the record but
  never proposes an obligation, because a marketing deadline is not a
  family's deadline;
- it is the hook for the next rule a family will want, "mute this sender",
  which is a category of one.

Domain rules are exact or suffix matches on the sending domain. Subject
rules are last, and only for domains nobody has listed. Unknown stays
unknown; a guess here would be a tag a person has to undo.
"""
from __future__ import annotations

import re
from email.utils import parseaddr

CATEGORIES = ("school", "medical", "government", "bills", "banking", "trading", "insurance", "subscriptions",
              "shopping", "food", "home", "travel", "promo", "newsletter", "developer", "unknown")

# A notice in any of these categories may be read, but nothing in it becomes
# a task. The sender wants something from the family; the family owes nothing.
NEVER_OBLIGATES = frozenset({"promo", "newsletter", "developer"})

# In these categories a dated event that has already happened is a record,
# not a calendar entry: "your order was delivered", "trades executed on the
# 30th", "payment received". The first mailbox put seven of them on the brief
# as MISSED. A school or clinic is different -- a circular sent the morning of
# the PTM is still an invitation -- so those keep same-day events.
RECORDS_THE_PAST = frozenset({"food", "shopping", "trading", "banking", "subscriptions", "home", "travel", "bills"})

# Where a dated event that has already started is still worth a calendar
# entry: a circular sent the morning of the PTM, a clinic's "today at 4".
# Everywhere else, "date of communication: the 23rd" is a record.
KEEPS_TODAY = frozenset({"school", "medical"})

# Exact domains or suffixes, most specific first within a category. Kept to
# senders actually seen; a family's own list will grow from "mute this".
_DOMAINS: list[tuple[str, str]] = [
    # government
    ("incometax.gov.in", "government"), ("gov.in", "government"), ("nic.in", "government"),
    # trading: exchanges, depositories, registrars, brokers
    ("nse.co.in", "trading"), ("bseindia.com", "trading"), ("bseindia.in", "trading"), ("nsdl.com", "trading"),
    ("cdslindia.co.in", "trading"), ("cdslstatement.com", "trading"), ("kfintech.com", "trading"), ("mufg.com", "trading"), ("proxydocs.com", "trading"),
    ("zerodha.net", "trading"), ("zerodha.com", "trading"), ("interactivebrokers.com", "trading"), ("indmoney.com", "trading"), ("wintwealth.com", "trading"),
    # banking
    ("icici.bank.in", "banking"), ("hdfcbank.bank.in", "banking"), ("idfcfirst.bank.in", "banking"),
    ("pnbmail.bank.in", "banking"), ("bank.in", "banking"), ("sbi.co.in", "banking"), ("axisbank.com", "banking"),
    # the addresses the banks' transaction alerts come from
    ("hdfcbank.net", "banking"), ("icicibank.com", "banking"), ("kotak.com", "banking"), ("yesbank.in", "banking"),
    ("indusind.com", "banking"), ("idfcfirstbank.com", "banking"), ("federalbank.co.in", "banking"), ("bankofbaroda.in", "banking"),
    ("pnb.co.in", "banking"), ("unionbankofindia.co.in", "banking"), ("canarabank.com", "banking"),
    # bills
    ("airtel.com", "bills"), ("jio.com", "bills"), ("bsesdelhi.com", "bills"), ("tatapower.com", "bills"),
    # insurance (the real ones; their marketing arms are below)
    ("tataaia.com", "insurance"), ("maxlifeinsurance.com", "insurance"), ("licindia.in", "insurance"),
    ("hdfclife.com", "insurance"), ("icicilombard.com", "insurance"),
    # the aggregator a policy was bought through, and the motor and health
    # insurers it sells: the policy PDF comes from one or the other
    ("policybazaar.com", "insurance"), ("acko.com", "insurance"), ("godigit.com", "insurance"),
    ("tataaig.com", "insurance"), ("bajajallianz.com", "insurance"), ("hdfcergo.com", "insurance"),
    ("reliancegeneral.co.in", "insurance"), ("newindia.co.in", "insurance"), ("uiic.co.in", "insurance"),
    ("sbigeneral.in", "insurance"), ("iffcotokio.co.in", "insurance"), ("royalsundaram.in", "insurance"),
    ("cholainsurance.com", "insurance"), ("zurichkotak.com", "insurance"), ("starhealth.in", "insurance"),
    ("careinsurance.com", "insurance"), ("nivabupa.com", "insurance"), ("futuregenerali.in", "insurance"),
    # subscriptions and receipts
    ("email.apple.com", "subscriptions"), ("apple.com", "subscriptions"), ("google.com", "subscriptions"),
    ("stripe.com", "subscriptions"), ("mail.anthropic.com", "subscriptions"), ("lovable.dev", "subscriptions"),
    ("venice.ai", "subscriptions"), ("netflix.com", "subscriptions"), ("spotify.com", "subscriptions"),
    # shopping and deliveries
    ("amazon.in", "shopping"), ("amazon.com", "shopping"), ("croma.com", "shopping"), ("flipkart.com", "shopping"),
    ("joyalukkas.com", "shopping"), ("bosch-home.com", "home"), ("urbancompany.com", "home"),
    # food
    ("swiggy.in", "food"), ("instamart.in", "food"), ("zomato.com", "food"), ("blinkit.com", "food"),
    # travel
    ("irctc.co.in", "travel"), ("intrcity.com", "travel"), ("makemytrip.com", "travel"), ("redbus.in", "travel"),
    ("indigo.in", "travel"), ("airindia.com", "travel"),
    # marketing arms and newsletters, by the domains they actually use
    ("maxlifeinsurance.info", "promo"), ("connect.tataaia.com", "promo"), ("emailers.idfcfirst.bank.in", "promo"),
    ("mailers.hdfcbank.bank.in", "promo"), ("rmp.flipkart.com", "promo"), ("moneylion.com", "promo"),
    ("technologyadvice.com", "promo"), ("yourbusinessnumber.com", "promo"), ("dune.com", "promo"),
    ("economictimesnews.com", "newsletter"), ("theinformation.com", "newsletter"), ("quora.com", "newsletter"),
    ("beehiiv.com", "newsletter"), ("dailydoseofds.com", "newsletter"), ("tldrnewsletter.com", "newsletter"),
    ("substack.com", "newsletter"), ("medium.com", "newsletter"),
    ("github.com", "developer"), ("gitlab.com", "developer"), ("vercel.com", "developer"),
]

# Subject words, for a domain nobody listed. School and medical come first
# because they are the wedge and the ones a family must not miss.
_SUBJECTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(circular|ptm|parent[- ]teacher|school|class \w+|grade \w+|term \d|exam|fee(s)? due|admission)\b", re.I), "school"),
    (re.compile(r"\b(appointment|prescription|vaccin|lab (report|result)|discharge|clinic|hospital|doctor)\b", re.I), "medical"),
    (re.compile(r"\b(e-?voting|postal ballot|annual (general )?meeting|agm|dividend|contract note|trades? executed|shareholder)\b", re.I), "trading"),
    (re.compile(r"\b(bill|statement|due date|invoice|payment (due|reminder))\b", re.I), "bills"),
    (re.compile(r"\b(receipt|subscription|renew(s|al|ed)?|your plan)\b", re.I), "subscriptions"),
    (re.compile(r"\b(order|delivery|delivered|shipped|out for delivery)\b", re.I), "shopping"),
    (re.compile(r"\b(itinerary|e-?ticket|pnr|booking confirmed|boarding)\b", re.I), "travel"),
    (re.compile(r"\b(unsubscribe|newsletter|digest|top stories|this week in)\b", re.I), "newsletter"),
    (re.compile(r"\b(offer|sale|hurry|limited time|lock (in )?your|exclusive|% off|save (up to|instantly))\b", re.I), "promo"),
]


def sender_domain(source: dict | None) -> str:
    _, address = parseaddr((source or {}).get("from") or "")
    return address.rsplit("@", 1)[-1].lower() if "@" in address else ""


def category_of(channel: str | None, source: dict | None, subject: str | None = None) -> str:
    """The category, by domain first and subject second. A forwarded chat
    message has no institutional sender, so only its words can say."""
    domain = sender_domain(source)
    if domain:
        # The longest suffix wins, so a marketing arm (connect.tataaia.com)
        # is a promo and not the insurer it belongs to (tataaia.com).
        hits = [(len(suffix), category) for suffix, category in _DOMAINS
                if domain == suffix or domain.endswith("." + suffix)]
        if hits:
            return max(hits)[1]
    text = subject if subject is not None else (source or {}).get("subject") or ""
    for pattern, category in _SUBJECTS:
        if pattern.search(text or ""):
            return category
    return "unknown"


def may_obligate(category: str) -> bool:
    return category not in NEVER_OBLIGATES


# What the inbox says when a read found dates in a promotion and proposed none.
WITHHELD_REASON = ("This is a promotion or newsletter, so nothing in it is proposed as a task. "
                   "The dates it mentions are the sender's offers, not the family's deadlines.")
