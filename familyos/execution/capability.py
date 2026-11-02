"""The gateway: an agent names a capability and never holds a secret.

Three products arrived at this independently -- Composio's Open Dot takes a
*site* and types the password server-side, CopilotKit keeps service keys out of
the browser, OpenBot's supervisor hands each agent its own computer credential.
None of them solves the session itself, which is the thing that actually sits
in the container.

Here the split is total. Whatever decides *what to do* -- a model, a planner, a
person -- gets a `Capability`: a name, a service, and the origins it may reach.
It carries no cookie, no token and no key, and cannot be turned into one. Only
a `Driver`, which is the code that actually drives a browser, is handed the
lease, and only for the length of a task.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from familyos.execution import disposable, sessions
from familyos.identity import Invalid, Principal

logger = logging.getLogger(__name__)


class NoDriver(Invalid):
    """Nothing is configured to drive a browser, so the task cannot run. Said
    plainly rather than silently doing nothing."""


@dataclass(frozen=True)
class Capability:
    """What the deciding half is allowed to know.

    Deliberately not a credential and deliberately not convertible into one:
    there is no field here that a prompt, a log line or a traceback could leak.
    """
    service: str
    allow_hosts: frozenset[str]
    describes: str

    def __repr__(self) -> str:
        return f"<Capability {self.service} hosts={sorted(self.allow_hosts)}>"


@dataclass(frozen=True)
class Outcome:
    """What a task brought back: evidence, never a fact. It goes through the
    same gateway as a forwarded photo before it is anything at all."""
    pages: list[disposable.Page]
    note: str = ""


class Driver(Protocol):
    """The seam a real browser plugs into.

    Implementations are the only code handed a lease. Playwright on a
    Firecracker microVM, Steel, Browserbase -- all of them satisfy this, and
    none of them changes anything above it.
    """

    async def run(self, lease: sessions.Lease, *, task: str) -> Outcome:
        ...


class RefusingDriver:
    """The default. A deployment with no browser does nothing rather than
    pretending to."""

    async def run(self, lease: sessions.Lease, *, task: str) -> Outcome:
        raise NoDriver("no browser is configured on this deployment, so there is nothing to run the task on")


_driver: Driver = RefusingDriver()


def use_driver(driver: Driver) -> None:
    global _driver
    _driver = driver


def current_driver() -> Driver:
    return _driver


async def capability_for(p: Principal, service: str) -> Capability:
    """What the deciding half may be told. Raises if nobody has signed in --
    the answer to which is a person, not a retry."""
    for row in await sessions.list_for(p):
        if row["service"] == service.strip().lower():
            return Capability(service=row["service"], allow_hosts=frozenset(row["allow_hosts"]),
                              describes=f"a signed-in session for {row['service']}")
    raise sessions.SessionLapsed(f"nobody has signed in to {service}; a member has to do that themselves")


async def perform(p: Principal, capability: Capability, *, task: str, reason: str) -> Outcome:
    """Run one task under one capability.

    The lease is opened here and closed here. The driver sees it; nothing else
    does, and nothing survives the call.
    """
    async with sessions.lease(p, capability.service, reason=reason) as held:
        if held.allow_hosts != capability.allow_hosts:
            # The stored grant is the authority. A capability that has drifted
            # from it -- however it drifted -- is not honoured.
            raise Invalid("this capability no longer matches the stored session")
        outcome = await current_driver().run(held, task=task)
    for page in outcome.pages:
        disposable.approved(page.url, capability.allow_hosts)
    return outcome


def describe() -> str:
    name = type(current_driver()).__name__
    if isinstance(current_driver(), RefusingDriver):
        return "capability gateway: no browser configured, so class-2 tasks are refused"
    return f"capability gateway: {name} drives; secrets never leave the lease"
