"""Configuration, read from the environment (prefix FAMILYOS_) or a .env file."""
from __future__ import annotations

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base Sepolia and Ethereum Sepolia. Adding a number here is a decision for counsel, not a configuration change.
WALLET_TESTNET_CHAIN_IDS = frozenset({84532, 11155111})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FAMILYOS_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/familyos"

    # Wraps every household's data key. 32 bytes, base64. Rotating it means
    # re-wrapping the household keys, never re-encrypting the blobs.
    master_key: str = Field(default="", repr=False)

    # Object storage. "local" writes under blob_dir (dev and tests); "s3"
    # talks to any S3-compatible store (AWS, MinIO, R2).
    blob_backend: str = "local"
    blob_dir: str = ".blobs"
    s3_bucket: str = "familyos-originals"
    s3_endpoint_url: str | None = None
    s3_region: str = "ap-south-1"
    s3_access_key_id: str | None = Field(default=None, repr=False)
    s3_secret_access_key: str | None = Field(default=None, repr=False)

    # Parsing runs PyMuPDF, Pillow and Tesseract over bytes a stranger sent,
    # so it runs in a child process with no FAMILYOS_ environment: no master
    # key, no database URL, no object-store credentials. Off only for
    # development, and the boot log says so loudly when it is.
    # Ask every guardian, when they give consent for a child, to say they are the child's parent or lawful guardian. Off by default so nothing existing
    # changes; turn on before DPDP Rule 10 starts (about May 2027) or for the UAE's under-13 rule (docs/children-data-compliance.md).
    require_guardian_declaration: bool = False
    parse_sandbox: bool = True
    parse_timeout_seconds: float = 90.0
    parse_memory_mb: int = 1024
    parse_concurrency: int = 4          # children at once: a page of thumbnails is a page of requests, each up to parse_memory_mb
    parse_cpu_seconds: int = 120
    parse_max_output_bytes: int = 64 * 1024 * 1024
    # Where a stronger boundary goes without the caller knowing. For example:
    #   FAMILYOS_SANDBOX_CMD="bwrap --unshare-net --unshare-pid --die-with-parent --ro-bind / /"
    # A process stops a compromised parser reading our secrets or reaching the
    # database. It does not stop outbound network or a kernel escape; this is
    # the seam for whatever does.
    sandbox_cmd: str | None = None

    # Intake limits.
    max_upload_bytes: int = 25 * 1024 * 1024
    max_email_bytes: int = 30 * 1024 * 1024
    # An export is built in memory and streamed, never stored, so this is a
    # ceiling on one request rather than on a household.
    max_export_bytes: int = 200 * 1024 * 1024

    # Forwarding email: <household inbound token>@<inbound_domain>. The mail
    # provider posts the raw message to /v1/inbound/email with this secret.
    # How long a sign-in token lasts. It slides forward while it is being
    # used, so an active session stays signed in and an abandoned one ends.
    token_lifetime_days: int = 30
    # Where the console lives, so a sign-in link points somewhere a person can
    # open. Local by default; set it for anything a real family uses.
    console_url: str = "http://localhost:8000/app/"
    # Where an assistant that runs in a vendor's cloud (Claude API, Grok) reaches /mcp: a public https address of this server.
    # Empty means those connections cannot run a task; the local Claude Code adapter uses mcp_local_url instead.
    mcp_public_url: str = ""
    mcp_local_url: str = "http://127.0.0.1:8000/mcp"
    # Run `claude -p` on this machine for a connection of provider claude_code. Development only: off unless set.
    allow_local_claude_code: bool = False
    # A sign-in link is short-lived on purpose: it arrives in a mailbox, and a
    # mailbox is not a vault.
    sign_in_link_minutes: int = 15
    # An invitation is opened later, on another person's phone, so it lasts days; an ordinary sign-in link stays minutes.
    invite_link_days: int = 7
    # Passkeys (passkeys.py): the exact web origins that may register and use them, comma separated. A passkey is bound to the address's host, so one made at
    # localhost does not work at the Tailscale address. Set this to the real https address for anything a family uses.
    webauthn_origins: str = "http://localhost:8088,http://localhost:8000,http://127.0.0.1:8088"
    webauthn_rp_name: str = "FamilyOS"
    # How long a household whose key the family holds stays unlocked in memory after they unlock it (familykey.py).
    family_key_unlock_hours: int = 8
    # More than one worker process (docs/deploy.md, "More than one worker"). Off by default: one worker, the unlocked family key only in that process's
    # memory. On, the unlocked key is also kept, wrapped under the master key, in family_key_unlocks until it expires or the household is locked.
    multi_worker: bool = False
    # With several workers: also keep the family's unlocked key in Postgres, wrapped under the server's master key, so one unlock opens every worker and a lock
    # closes them all. A database snapshot plus the master key could then open a household whose key the family holds, for as long as the unlock lasts (hours).
    # Off: each worker keeps its own unlock in memory, as a single worker does, and nothing the operator holds can open the household. Needs multi_worker.
    family_key_share_unlock: bool = False
    family_key_passkey_minutes: int = 15      # how recent a passkey sign-in must be to open the household on a trusted device
    # Store the text read out of notices (quotes, titles, names) sealed under the household key (sealing.py). On by default since 23 Oct 2026;
    # an old row is sealed by the sweep (sealing.backfill), and turning this off stops sealing new text without breaking what is sealed.
    seal_extracted_text: bool = True
    # Watching a public page for a member, through the credential-free class-1
    # reader. Off by default: it is the first thing that reaches outward.
    watches_enabled: bool = False
    watch_sweep_seconds: int = 900
    # Reading the family's own calendar, so a notice can be told it clashes.
    # calendar.readonly is a sensitive scope, not a restricted one: ordinary
    # verification, no CASA. Asked for separately from Gmail for that reason.
    # Steel, self-hosted, as the browser behind an assisted harvest. Unset
    # means sittings still work but have no live view: pages are handed in.
    steel_url: str = ""
    # Which browser runs errands, looks and sign-in sittings: "steel" (the
    # URL above), "local" (Playwright's Chromium on this machine: the
    # family's own address, no session bill, a sitting opens a window here),
    # or "auto": Steel when a URL is set, else local when Chromium is here.
    browser: str = "auto"
    # Errands on a site with no runbook, and looks, by the generalist
    # (familyos/execution/generalist.py): Anthropic's browser toolset over the
    # run's own browser. "off" never; "fallback" when the site has no runbook;
    # "looks" also for every look, runbook or not. The model is an Anthropic
    # model name; empty means the chat model when that is Anthropic's.
    errand_generalist: str = "fallback"
    errand_model: str = ""
    # Asking the record a question. Off by default: it sends more of a
    # family's text to a model provider than extraction alone does, and that
    # is a decision somebody makes rather than a default they inherit.
    # On by default: the Ask window sends what a member may see -- headlines,
    # dates, to-dos, charges -- to the chat model, never a raw notice. Set
    # false on a deployment that must send nothing anywhere.
    # Log each chat question and answer in full. Off: the log carries only
    # lengths and counts. On only while a wrong answer is being chased.
    chat_log_text: bool = False
    ask_enabled: bool = True
    # The chat model, "provider/name"; empty means the extraction model.
    chat_model: str = ""
    calendar_enabled: bool = False
    # Writing accepted dates to the member's own Google Calendar. Asks for
    # calendar.events.owned on connect -- sensitive, ordinary verification --
    # so a member who connected before this was on reconnects once.
    calendar_write_enabled: bool = False
    # A research provider for the public web ("parallel"), used by plans for
    # evidence under each option and by watches for JavaScript pages. Off
    # unless named; its key is read from FAMILYOS_PARALLEL_API_KEY.
    web_research: str = ""
    parallel_api_key: str = Field(default="", repr=False)
    # The household's clock, for "Sunday morning" and all-day events.
    timezone: str = "Asia/Kolkata"
    # The weekly digest: weekday 0=Monday .. 6=Sunday, from this hour.
    digest_enabled: bool = True
    digest_weekday: int = 6
    digest_hour: int = 8
    calendar_sync_seconds: int = 1800

    # Believe X-Forwarded-For for the caller's address (rate limits) only when
    # a proxy you run sets it. Off by default: otherwise anyone can claim any address.
    trust_proxy_headers: bool = False
    # Per hour, per process (familyos/ratelimit.py). 0 turns a limit off.
    rate_sign_in_per_email: int = 5
    rate_sign_in_per_ip: int = 30
    rate_household_per_ip: int = 10
    rate_mcp_failures_per_ip: int = 30   # wrong connection keys on /mcp, per address and hour; once it is reached that address is not tried again until the window passes
    rate_passkey_per_ip: int = 60     # passkey sign-in challenges and attempts; each open challenge is a database row
    rate_tickets_per_member: int = 120   # live-view and phone-driver tickets; each is a database row
    # A signed "Share with FamilyOS" Shortcut built by scripts/make_share_shortcut.py, offered for download to a signed-in member.
    share_shortcut_file: str = ".shortcuts/Share-with-FamilyOS.shortcut"

    inbound_domain: str = "in.familyos.local"
    inbound_webhook_secret: str = Field(default="", repr=False)

    @property
    def inbound_email_enabled(self) -> bool:
        """The placeholder from .env.example is no secret: treat it as unset."""
        return self.inbound_webhook_secret.strip() not in ("", "change-me")
    # WhatsApp Cloud API. Parents forward school messages to this business
    # number; Meta has already verified the sender, so a number that belongs to
    # a member is trusted and one that belongs to nobody is refused.
    # app_secret signs every delivery: without it nothing is accepted.
    whatsapp_app_secret: str = Field(default="", repr=False)
    whatsapp_verify_token: str = Field(default="", repr=False)
    whatsapp_access_token: str = Field(default="", repr=False)
    whatsapp_phone_number_id: str = ""
    # The number as a parent would save it. Meta's phone_number_id is an
    # internal handle and no use to anyone forwarding a message.
    whatsapp_business_number: str = ""
    # A development bridge for unofficial WhatsApp clients, which can read a
    # class group where the Cloud API cannot. Off by default and meant to stay
    # that way: those clients break WhatsApp's terms, the ban lands on the
    # linked number, and a companion session can read every chat on it.
    whatsapp_bridge_enabled: bool = False
    # A member's own WhatsApp Web session, read every half hour for the chats they name. Off by default: it is a linked
    # companion device, which WhatsApp's guidelines list as an unofficial client, so each member also has to say yes.
    whatsapp_watch_enabled: bool = False
    whatsapp_profile_dir: str = ""          # where each member's logged-in browser profile lives; "" = ~/.familyos/whatsapp
    # With more than one worker (multi_worker), the profile directories live on ONE machine and only the worker started with this set to true
    # opens them; the others answer that WhatsApp is read elsewhere and take none of its sweeps. Ignored with one worker, which reads.
    whatsapp_worker: bool = False
    whatsapp_bridge_secret: str = Field(default="", repr=False)
    whatsapp_api_base: str = "https://graph.facebook.com/v21.0"
    # A reminder is business-initiated, so it falls outside WhatsApp's 24-hour
    # customer service window and free text is refused. An approved utility
    # template with two slots -- what it is, and when -- is what gets through.
    # Unset, reminders reach only members who messaged us in the last day.
    whatsapp_template_name: str = ""
    whatsapp_template_language: str = "en"

    # Telegram, offered alongside WhatsApp so a family picks the one they
    # already use. A BotFather token is the whole setup: no business
    # verification, no approved template, and no 24-hour window, so a reminder
    # is an ordinary message. The webhook secret is the only thing standing in
    # front of the inbound URL -- unset, nothing is accepted.
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_webhook_secret: str = Field(default="", repr=False)
    # Live traffic for the school run (publiccontext.py). TomTom's Routing
    # API, 20,000 requests a month free, no card. The only keyed public
    # source: the request carries two points, home and the school, under this
    # key, so it runs only for the two hours before school and the hour before
    # pick-up, and only when the household's "leave by" switch is on. Unset,
    # the school run is the typical drive from public maps and nothing is sent.
    tomtom_api_key: str = Field(default="", repr=False)
    tomtom_country: str = "IN"   # the map search stays in this country
    # The @name a parent sees. Needed for the deep link they open to bind their
    # account, and to tell a message that names the bot in a group from the
    # rest of that group, which is never read.
    telegram_bot_username: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    # Quarantine mail whose From address is not authenticated (DMARC, or
    # DKIM/SPF aligned) by the receiving provider.
    require_sender_auth: bool = True
    # The authserv-id our mail provider stamps on its Authentication-Results
    # header (RFC 8601): "mx.google.com", "amazonses.com", the MX hostname.
    # Only that provider's verdict is believed. Unset, nothing authenticates
    # and every message waits in quarantine for a guardian.
    inbound_authserv_id: str = ""

    # Apply familyos/migrations at startup. Off for a database whose schema
    # someone else manages and this role may not alter (no CREATE): the app
    # then trusts the tables are already there.
    auto_migrate: bool = True
    # Development sign-in: POST /v1/sign-in/dev signs a member in by email
    # alone, through the same link-and-redeem path the mailed link takes, for
    # a deployment with no mail server yet. Anyone who can reach the server
    # can then sign in as anyone whose address they know: never on where the
    # server is reachable by people who are not its developers.
    dev_sign_in: bool = False

    # Durable jobs (familyos/jobs.py, from Orbit).
    jobs_enabled: bool = True
    job_lease_seconds: float = 60.0
    job_max_attempts: int = 5
    job_attach_seconds: float = 20.0

    # Extraction (familyos/extraction). "rules" reads notices in this
    # deployment and sends nothing anywhere. "model" sends the full text of
    # every accepted notice to the provider of extraction_model, so it is named
    # here and never inferred from an API key being present.
    # The model is named provider/model, LiteLLM-style.
    extraction_enabled: bool = True
    extractor: str = "rules"                # rules | model | claude | openai
    extraction_model: str = Field(default="openai/gpt-5.6-sol",
                                  validation_alias=AliasChoices("FAMILYOS_EXTRACTION_MODEL", "RESEARCH_MODEL"))
    extraction_effort: str = "medium"
    # Scripts the OCR should expect, as Tesseract language codes joined by "+".
    # English alone reads a Devanagari notice as noise, not as bad English, so
    # a deployment serving Hindi-medium schools must say so here and have the
    # matching tesseract-ocr-<lang> package installed.
    ocr_languages: str = "eng"
    # A model on this machine, through an OpenAI-compatible server (Ollama by
    # default), for a household that switched "local models" on in its rules.
    # The model is named here ("qwen3:32b"); empty means the switch is not
    # offered. The family's text then never leaves the deployment.
    # Paying for the family. Empty means FamilyOS cannot pay at all, whatever the household's switch says.
    # "crossmint" is the first provider planned; nothing here holds a card, the provider does.
    payments_provider: str = ""
    payments_api_key: str = Field(default="", repr=False)
    payments_project_id: str = ""              # the provider's project id: the issuer of the login tokens (not secret)
    payments_jwt_key_file: str = ".keys/payments_jwt.pem"
    payments_client_key: str = ""              # the provider's client-side key: made to be shown to a browser, unlike the server key
    payments_environment: str = "staging"      # staging until a guardian-run test has passed; "production" spends real money
    local_model: str = ""
    # More places a model can run, as a JSON list (see modelroute.py): a confidential-inference provider, the family's own TEE hosting.
    model_profiles: str = ""
    # Which school uses which phone app, and a school's own bundle id: family-specific, so a local file, not code (execution/apps.py). "" = ~/.familyos/school_apps.json
    school_apps_file: str = ""
    local_model_url: str = "http://localhost:11434/v1"
    # "own" declares that the model at local_model_url is hosting the operator runs (a privacy floor of "own" is then met by it). Empty: own only when the address is this machine.
    local_model_trust: str = ""
    local_model_key: str = Field(default="local", repr=False)     # a server of your own may want one; Ollama ignores it
    # The model that reads a picture (a handwritten prescription, a photographed
    # circular), when it is not the one that reads text: a vision model on this
    # machine ("gemma4" through Ollama). Empty means the local model above.
    picture_model: str = ""
    picture_model_url: str = "http://localhost:11434/v1"     # where picture_model runs: Ollama on this machine by default
    local_model_context: int = 32768       # the model's window, so an answer is asked to fit beside the notice
    # Search by meaning: a small embedding model on this machine (Ollama by
    # default), so "the plumber" finds "Rajesh, pipe repair". Empty turns it
    # off and search is by words alone. Nothing is stored: the vectors live in
    # memory and are rebuilt after a restart, so destroying a household's key
    # still leaves nothing readable behind.
    embed_model: str = "embeddinggemma"
    embed_url: str = "http://localhost:11434/v1"
    embed_key: str = Field(default="local", repr=False)
    # Voice: a voice note or a spoken question turned into words. "local" runs
    # faster-whisper on this machine, so the family's voice never leaves the
    # deployment (the default; the first use downloads the model once);
    # "cloud" posts the audio to an OpenAI-compatible transcription endpoint
    # you name; "off" refuses. The audio is never kept either way, only the
    # words the member then chooses to file.
    # A private option, not part of the product: a member's own daily Health summary from the phone. Off unless this
    # deployment names it (FAMILYOS_HEALTH_ENABLED=true); when off the routes answer 404 and no screen offers it.
    health_enabled: bool = False
    voice_engine: str = "local"
    voice_model: str = "small"             # tiny, base, small, medium, large-v3: slower and better as it grows
    voice_device: str = "cpu"
    voice_compute: str = "int8"
    voice_max_seconds: int = 180
    voice_cloud_url: str = ""              # e.g. https://api.openai.com/v1 or a Sarvam-compatible gateway
    voice_cloud_key: str = Field(default="", repr=False)
    voice_cloud_model: str = "whisper-1"
    anthropic_api_key: str = Field(default="", repr=False,
                                   validation_alias=AliasChoices("FAMILYOS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"))
    # A key made at the organisation rather than inside a workspace is refused
    # unless each request names the workspace it bills to (wrkspc_...). Empty
    # for a workspace-scoped key, which needs nothing.
    anthropic_workspace_id: str = ""
    openai_api_key: str = Field(default="", repr=False,
                                validation_alias=AliasChoices("FAMILYOS_OPENAI_API_KEY", "OPENAI_API_KEY"))

    # Reminders (familyos/reminders.py). One recurring job tells whoever may
    # see an obligation, before its date. Lead times are days before, as a
    # comma-separated list; 0 means on the day.
    reminders_enabled: bool = True
    reminder_lead_days: str = "7,1,0"
    reminder_sweep_seconds: float = 3600.0
    reminder_max_attempts: int = 5
    # "log" writes the reminder to the application log and the audit trail and
    # is the default because it needs nothing configured. "email" needs SMTP.
    reminder_channel: str = "log"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_username: str = ""
    smtp_password: str = Field(default="", repr=False)
    smtp_from: str = ""

    # Reconciliation (familyos/reconcile.py). Links a revised notice to the one
    # it revises. Always proposed, never applied on its own.
    reconciliation_enabled: bool = True

    # Doing something about a notice. Two kinds only -- reply to the school
    # that wrote, and a calendar entry -- and the recipient is derived from the
    # notice rather than supplied, so there is no parameter through which a
    # message could be addressed anywhere else.
    actions_enabled: bool = False
    action_max_attempts: int = 3
    action_sweep_seconds: int = 60

    # Connected Gmail. A member grants read-only access to their own mailbox
    # and the poller looks for school mail in it.
    #
    # `gmail.readonly` is a RESTRICTED scope: Google requires a CASA Tier 2
    # security assessment before an app may ask the public for it, which takes
    # weeks and is re-validated yearly. Until that clears, an OAuth client in
    # testing mode may ask up to 100 named test users -- which is what an
    # alpha is. Nothing here changes between the two; only the Google-side
    # client does.
    google_client_id: str | None = None
    google_client_secret: str | None = Field(default=None, repr=False)
    # Must match a redirect URI registered on the OAuth client exactly.
    google_redirect_uri: str = "http://localhost:8000/v1/google/callback"
    # Signing in is a different callback from connecting a mailbox: one has a
    # member already and the other is finding out who is asking.
    google_sign_in_redirect_uri: str = "http://localhost:8000/v1/sign-in/google/callback"
    # Our data collecting layer (famos-notes/COLLECTION_PLAN.md, decided 30 Oct 2026). On: Google sign-in also asks to read
    # Gmail, Calendar and Tasks, and what is read is kept in a local cache on this machine (familyos/collect/), not in the
    # database, until it is decided where collected data goes. Off: the founder's sign-in, email only, nothing kept.
    google_sign_in_collect: bool = False
    # The local cache's folder (an SQLite file inside, owner-only); outside every repository.
    collect_dir: str = "~/.familyos/collect"
    # The decision layer's model (familyos/collect/decide.py): the local Qwen3.5 server's /methods. Unreachable, the
    # decision is made from the registry alone.
    collect_model_url: str = "http://127.0.0.1:8080"
    collect_model_timeout_s: float = 90.0
    # The browser agent (familyos/collect/browser_agent.py): Claude's browser toolset over Chromium on this Mac, signing in
    # with Connected services. The model was chosen 30 Oct 2026; headless off shows the window as it works.
    collect_agent_model: str = "claude-sonnet-5-5"
    collect_browser_headless: bool = False
    gmail_enabled: bool = False
    gmail_poll_seconds: int = 300
    # What counts as worth reading. Narrow on purpose: the point is school
    # mail, not the member's whole inbox, and every message this does not
    # match is one FamilyOS never sees.
    # A household's administrative life is not only school. These are the
    # words that appear in the subject line of a document somebody has to do
    # something about -- medical, utility, insurance, travel, device -- and
    # nothing else. Narrow on purpose: this query is the only thing standing
    # between a connected mailbox and somebody's work email.
    gmail_query: str = (
        "has:attachment"
        " OR subject:(school OR circular OR notice OR fee OR permission OR consent)"
        " OR subject:(appointment OR prescription OR \"test result\" OR vaccination OR discharge)"
        " OR subject:(bill OR invoice OR statement OR premium OR renewal OR \"due date\" OR receipt)"
        " OR subject:(booking OR itinerary OR \"e-ticket\" OR reservation OR visa OR confirmation)"
        " OR subject:(warranty OR \"service due\" OR maintenance OR delivery)"
        # A bank's own word that money moved: the UPI alert that settles a bill
        # days before the biller's receipt, and the only receipt a UPI payment
        # to a shop ever gets.
        " OR subject:(UPI OR debited OR \"debit alert\" OR \"transaction alert\" OR \"payment received\" OR \"payment successful\" OR paid)")
    # How far back the first pass reaches. A new connection should bring in
    # this term's notices, not a decade of mail.
    gmail_backfill_days: int = 30
    gmail_max_per_poll: int = 25
    # A message that fails to store this many polls in a row is skipped (and said so), not allowed to stall the mailbox for good.
    gmail_skip_after: int = 5
    # The authserv-id on mail Google itself delivered. Mail fetched from a
    # member's own mailbox has already passed Google's checks, and this is how
    # the stored copy says so.
    google_authserv_id: str = "mx.google.com"

    # The optional family wallet (familyos/wallet/, docs/wallet.md). The deployment flag mounts the package at all; each household then opts in with its own
    # switch (rules: wallet_enabled). TEST NETWORKS ONLY in this build: a mainnet chain id is refused here, before anything starts, until a legal review
    # of virtual-asset rules in the countries served has been done. No key, seed or signing capability exists in these settings or anywhere on the server.
    wallet_enabled: bool = False
    wallet_chain_id: int = 84532                                  # Base Sepolia
    wallet_chain_name: str = "Base Sepolia"
    wallet_rpc_url: str = "https://sepolia.base.org"
    wallet_token_address: str = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"   # Circle's USDC on Base Sepolia
    wallet_token_symbol: str = "USDC"
    wallet_token_decimals: int = 6
    wallet_approval_hours: int = 24                               # a proposal, and an approval not yet sent, lapse after this
    wallet_default_per_transfer: int = 10                         # whole tokens: what a new household's limits start at
    wallet_default_per_day: int = 25
    wallet_default_per_month: int = 100

    @field_validator("wallet_chain_id")
    @classmethod
    def _wallet_testnets_only(cls, value: int) -> int:
        if value not in WALLET_TESTNET_CHAIN_IDS:
            raise ValueError(f"wallet_chain_id {value} is not a test network. This build moves test tokens only; a mainnet needs a legal review first "
                             f"(docs/wallet.md). Allowed: {sorted(WALLET_TESTNET_CHAIN_IDS)}.")
        return value


settings = Settings()
