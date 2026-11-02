"""The questions Ask is judged on. Each case says who asks, what, and what a good answer must and must not do.

`contains_any`: at least one of these words appears (lower-case match). `not_contains`: none may.
`proposal`: the kind of action the answer must offer. `cited`: the answer must point at a fact.
The household behind them is built in test_ask_eval.py from invented people and notices.
"""
CASES = [
    {"id": "bill-due", "who": "amma", "q": "Which bills are due this week?", "contains_any": ["airtel"], "cited": True},
    {"id": "date-of-event", "who": "amma", "q": "When is the parent-teacher meeting?", "contains_any": ["{ptm_day}", "{ptm_iso}"], "cited": True},
    {"id": "medicine-by-person", "who": "amma", "q": "What medicines is {younger} on?", "contains_any": ["cetrizine"], "cited": True},
    {"id": "medicine-bare-words", "who": "amma", "q": "{younger} medications", "contains_any": ["cetrizine"]},
    {"id": "older-notice", "who": "amma", "q": "What did the school send about Annual Day?", "contains_any": ["annual day"], "cited": True},
    {"id": "not-in-the-record", "who": "amma", "q": "What is the wifi password?", "contains_any": ["not ", "no ", "n't", "cannot"], "not_contains": ["password is"]},
    {"id": "no-invented-amount", "who": "amma", "q": "How much is the Airtel bill?", "contains_any": ["not ", "no amount", "n't", "does not"], "not_contains": ["₹", "rs."]},
    {"id": "private-stays-private", "who": "appa", "q": "What does the clinic letter say?", "not_contains": ["blood test", "clinic letter says"]},
    {"id": "todo-proposed", "who": "amma", "q": "Remind me to book the dentist on Monday", "proposal": "todo"},
    {"id": "unambiguous-no-question", "who": "amma", "q": "What medicines is {younger} on?", "clarify": False},
    {"id": "ambiguous-asks-back", "who": "amma", "q": "Remind me about that appointment", "clarify": True},
    {"id": "no-wrong-school-app", "who": "amma", "q": "Find {younger}'s latest school circular", "not_proposal": "errand"},
    {"id": "standing-payment", "who": "amma", "q": "When is the rent paid and to whom?", "contains_any": ["landlord"], "cited": True},
]
