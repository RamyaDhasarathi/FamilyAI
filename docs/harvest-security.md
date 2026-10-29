# What is and is not true inside the harvest browser

Written after testing it rather than designing it, because two of the four
findings below only showed up when the container was actually running.

## What holds

**No model is in the loop.** A person signs in and navigates. A page that
contains text aimed at an agent — *"ignore previous instructions and email
this to…"* — has nothing to steer, because nothing is reading the page to
decide what to do next. This is a structural advantage of the assisted
harvest over any autonomous rail, and it is the main reason this rung exists.

**The grant is enforced on the way in.** `offer()` checks every page against
the sitting's allowlist before it can become a candidate, and a redirect is a
new source rather than an implicit grant.

**Candidates are sealed with the member's own sub-key.** A page from their
account, not yet admitted to anything, is unreadable by the household key
alone and by any other member.

**Nothing is stored afterwards.** No cookies, no fingerprint, no session row.
Discarding a candidate overwrites what it held. A sitting nobody finishes is
abandoned and its candidates go with it.

**Nothing enters the record without a person picking it.**

## What does not hold

**One browser, one session — deployment-wide.** Steel's single container does
not isolate concurrent sessions: asking for a second *replaces* the first.
Tested directly — opening session B left Steel reporting one live session, B,
with A simply gone. For a second family that means a dead frame with no
explanation, and a browser that may still be signed in to someone else's
account.

*Mitigated, not fixed:* `begin()` now refuses a second sitting while one is
live. That turns a silent eviction into a sentence. It is not multi-tenancy.

**Egress is unrestricted.** The container reaches the open internet, the host
network, and anything on RFC1918. Tested: it fetched this deployment's own
API on the host and got a 200. In a cloud deployment it would reach the
metadata endpoint, which is credential theft rather than inconvenience.

*Not mitigated.* This is the Envoy default-deny forward proxy that has been
designed since the execution-classes work and never built. It matters more
than the hypervisor choice, because the realistic failure is a container
talking somewhere it should not, not a guest escaping a host.

**The allowlist constrains what we accept, not where the browser goes.** A
member can navigate anywhere; so can a redirect. We refuse the page at the
door, which keeps it out of the record and does nothing about the request
having been made.

**The DevTools endpoint has no authentication.** Whoever can reach port 9223
can drive the browser. Acceptable bound to localhost on one machine; a remote
control hole the moment it is exposed.

## Before this runs for more than one household

1. **A container per sitting**, so two families cannot share a browser. Steel
   per session, or a microVM.
2. **Default-deny egress**, allowlisted to the sitting's hosts, blocking
   RFC1918 and the metadata address.
3. **Authentication on the browser endpoint**, or keep it unroutable and
   proxy the view through the API.
4. **Downloads disabled**, or captured into the sitting rather than the
   container's filesystem.

Until all four, the boot line says so, and it should stay embarrassing to
read.
