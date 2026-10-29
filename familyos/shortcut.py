"""The "Share with FamilyOS" Shortcut for people who will not install the app: built here, signed with macOS's `shortcuts sign` so any iPhone
imports it. scripts/make_share_shortcut.py builds the generic file (the person pastes a token at import); on a Mac-hosted server the console's
download builds one per person with their own phone token already inside, so nothing is pasted."""
import asyncio
import plistlib
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

CLASSES = ["WFAppStoreAppContentItem", "WFArticleContentItem", "WFContactContentItem", "WFDateContentItem", "WFEmailAddressContentItem",
           "WFGenericFileContentItem", "WFImageContentItem", "WFiTunesProductContentItem", "WFLocationContentItem", "WFDCMapsLinkContentItem",
           "WFAVAssetContentItem", "WFPDFContentItem", "WFPhoneNumberContentItem", "WFRichTextContentItem", "WFSafariWebPageContentItem",
           "WFStringContentItem", "WFURLContentItem"]


def _text(string: str, attachments: dict | None = None) -> dict:
    return {"Value": {"string": string, **({"attachmentsByRange": attachments} if attachments else {})},
            "WFSerializationType": "WFTextTokenString"}


def _ref(uuid_: str, name: str) -> dict:
    return {"Value": {"OutputUUID": uuid_, "Type": "ActionOutput", "OutputName": name}, "WFSerializationType": "WFTextTokenAttachment"}


def build(server: str, token: str | None = None) -> dict:
    """Token (asked once at import) -> the household's child names from the server (so a new child appears with no new file) -> Choose from List
    -> POST the shared thing with the chosen name as the tag. "Nobody" is on the list and tags nothing."""
    server = server.rstrip("/")
    token_id, names, split, chosen = (str(uuid.uuid4()).upper() for _ in range(4))
    attach = lambda uid, name, at="{7, 1}": {at: {"OutputUUID": uid, "Type": "ActionOutput", "OutputName": name}}      # noqa: E731
    bearer = _text("Bearer \ufffc", attach(token_id, "Text"))
    header = lambda k, v: {"WFItemType": 0, "WFKey": _text(k), "WFValue": v}       # noqa: E731
    headers = lambda *items: {"Value": {"WFDictionaryFieldValueItems": list(items)}, "WFSerializationType": "WFDictionaryFieldValue"}      # noqa: E731
    return {
        "WFWorkflowClientVersion": "2900", "WFWorkflowClientRelease": "2.0", "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900", "WFWorkflowIcon": {"WFWorkflowIconStartColor": 463140863, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowTypes": ["ActionExtension"], "WFWorkflowInputContentItemClasses": CLASSES, "WFWorkflowHasShortcutInputVariables": True,
        # With no token the person is asked for theirs once, at import; with one, it is theirs already and nothing is asked.
        "WFWorkflowImportQuestions": [] if token else [{"Category": "Parameter", "ActionIndex": 0, "ParameterKey": "WFTextActionText",
                                                        "Text": "Paste your FamilyOS token (FamilyOS -> Household -> Phones and shortcuts)",
                                                        "DefaultValue": ""}],
        "WFWorkflowActions": [
            {"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
             "WFWorkflowActionParameters": {"UUID": token_id, "WFTextActionText": token or ""}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
             "WFWorkflowActionParameters": {"UUID": names, "WFURL": server + "/v1/inbound/share/tags", "WFHTTPMethod": "GET", "ShowHeaders": True,
                                            "WFHTTPHeaders": headers(header("Authorization", bearer))}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.text.split",
             "WFWorkflowActionParameters": {"UUID": split, "text": _ref(names, "Contents of URL"), "WFTextSeparator": "New Lines"}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.choosefromlist",
             "WFWorkflowActionParameters": {"UUID": chosen, "WFInput": _ref(split, "Split Text"), "WFChooseFromListActionPrompt": "Whose is this?"}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
             "WFWorkflowActionParameters": {
                 "WFURL": server + "/v1/inbound/share", "WFHTTPMethod": "POST", "WFHTTPBodyType": "File",
                 "WFRequestVariable": {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"},
                 "ShowHeaders": True,
                 "WFHTTPHeaders": headers(header("Authorization", bearer), header("X-Visibility", _text("private")),
                                          header("X-Tag", _text("\ufffc", attach(chosen, "Chosen Item", "{0, 1}"))))}},
            {"WFWorkflowActionIdentifier": "is.workflow.actions.showresult",
             "WFWorkflowActionParameters": {"Text": _text("Sent to FamilyOS")}},
        ],
    }


def can_sign() -> bool:
    return shutil.which("shortcuts") is not None


def sign_sync(plist: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "in.shortcut"
        raw.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_BINARY))
        done = subprocess.run(["shortcuts", "sign", "--mode", "anyone", "--input", str(raw), "--output", str(out)],
                              capture_output=True, text=True, timeout=60)
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout or "shortcuts sign failed").strip()[:300])


async def signed_for(server: str, token: str) -> bytes:
    """A signed shortcut with this person's token inside. Signing runs off the event loop."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "s.shortcut"
        await asyncio.get_running_loop().run_in_executor(None, sign_sync, build(server, token), out)
        return out.read_bytes()
