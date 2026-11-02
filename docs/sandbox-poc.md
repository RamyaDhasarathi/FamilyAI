# Sandbox proof of concept: SPACE (Perplexity), plan of 16 Oct 2026

Question: can a family's long-lived or risky tasks run in an isolated microVM on the operator's own Linux hosting, so that no logged-in
browser profile or credential sits on a laptop? First candidate task: the WhatsApp reader (docs/whatsapp-reading.md), the one place a
credential still lives on disk in the clear. Nothing here is built or run yet.

## What the SPACE docs say (repo `perplexityai/space` at c788098, 15 Oct 2026, Apache-2.0; read in full: introduction, installation,
first-sandbox, execution-environments, templates README)

- **Host.** Linux **x86_64** with **KVM**, `/dev/net/tun`, loop devices, btrfs, and a Docker daemon allowed to run privileged containers.
  "Not macOS." A VM host must expose those devices (nested virtualisation). The documented install is a local **Kind** (Kubernetes) cluster;
  the install guide says it does not cover a Kubernetes-free deployment (the architecture guide describes one).
- **Runtimes.** "Pluggable" is a design boundary, not a feature: the only implemented and production-qualified environment is **E0**: Linux/x86_64
  host, KVM, Firecracker 1.15.1, Linux/x86_64 guest, kernel 6.1.155. aarch64 pins exist but are not production-qualified. There is no
  non-KVM runtime today, so it cannot run on an Apple-silicon Mac.
- **API.** HTTP. Create a sandbox from a template (`seed:latest`, `code-runtime`), choose vCPU/memory/disk, pass `env`; run commands as argv
  arrays with a per-command timeout; stdout/stderr come as a live event stream (not durable logs; reconnecting gives `resync_required`).
  Lifecycle: `:pause` (keeps the VM resident) and `:suspend` (saves VM state and filesystem, releases resources), delete.
  "Do not put credentials in name or metadata." Egress is governed by operator egress profiles. Docs do not say how files or secrets are
  placed into a sandbox beyond `env`.
- **Maturity.** Announced 15 Oct 2026; the project says it powers Perplexity Computer (a claim in a post, not something we verified); fields marked
  "incubating" are outside the supported contract. Open question: custom templates. The docs describe building the system templates `seed` and
  `code-runtime` through an admin CLI and embedded recipes; whether an operator can add a template with Chromium and Playwright is not in what I read.

## The POC, in order, each with its pass condition

0. **A host.** Linux x86_64 with KVM and root. Pass: the install guide's host check prints "Host checks passed". *Needs the operator's hosting (or any
   KVM-capable cloud VM with nested virtualisation).*
1. **Hello sandbox.** Install per `docs/installation.md`; run `examples/first_sandbox.py`. Pass: "Hello from SPACE" and exit 0.
2. **A template with a browser.** Chromium (or Playwright's), Python 3.12 and FamilyOS's reader dependencies on `code-runtime` or a custom
   recipe. Pass: `python -c "from playwright.async_api import async_playwright"` and a headless page load of web.whatsapp.com from inside.
3. **The reader in a sandbox.** Run `PlaywrightReader.start_link` there. The browser profile lives on the sandbox's filesystem, not the laptop; the
   link code or QR is returned over the command stream. Egress profile: web.whatsapp.com and its static/media hosts only. Pass: link, then
   `read` returns the same messages as on the Mac.
4. **Persistence.** `:suspend`, then resume next morning. Pass: still linked; the 30-minute sweep reads again without re-linking.
5. **Measure.** Boot time, memory per sandbox, cost of a suspended one, whether WhatsApp treats a datacentre address differently (a known risk).
6. **Decision note.** Keep SPACE, use a hosted equivalent, or stay as we are; with the FamilyOS adapter sketched.

## The adapter FamilyOS would need (sketch, if the POC passes)

`familyos/execution/sandbox.py`, a collector-style protocol like `harvest.Collector`: `run(task, secrets_for_this_task) -> result`. Rules it must keep:
- **No stored secret in a sandbox.** The household key never enters one; a task gets a short-lived task token and sealed material it needs for that task only.
  WhatsApp's profile is the exception that needs thought: it must stay sealed outside the VM and be mounted for the run, or the VM's disk must be sealed under
  the household key and erased with it.
- **Erasure reaches it.** Deleting a household deletes its sandboxes and snapshots; a suspended snapshot is data and is sealed or deleted.
- **The privacy floor applies.** A sandbox that calls a cloud model is refused for a household whose floor is above cloud.
- **Egress is per task**, from the task's own site list (as `execution/sites.py` does for sessions).

## Risks and unknowns

- The host: our hosting's KVM and nested-virtualisation support is unconfirmed.
- Custom templates may need operator-level admin access to SPACE.
- Very new, 4 open issues, 26 stars at announcement: expect rough edges and API changes.
- WhatsApp may refuse or restrict a datacentre-hosted linked browser.
- Privileged Docker and btrfs on the host widen what the host itself must be trusted with.
