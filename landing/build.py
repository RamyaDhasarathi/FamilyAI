"""Builds the console's signed-out front page (familyos/web_welcome/index.html) from landing/page.html.

page.html is the page as a fragment (title, style, body, script), the same file published as a shared page.
The console copy adds a doctype and head, and one line that tells the page it is served by the console, so its
buttons go to /app/ (sign in, start a household) and a signed-in visitor is sent straight in.
Run: python3 landing/build.py
"""
from pathlib import Path

HERE = Path(__file__).parent
src = (HERE / "page.html").read_text()
head, body = src.split("</style>", 1)
head = head.replace("<title>FamilyOS</title>", "<title>FamilyOS</title>\n<meta name=\"description\" content=\"FamilyOS reads the circulars, bills, receipts and prescriptions that reach your household and turns them into dates you accept. Nothing happens without your yes.\">", 1)
out = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
       + head + "</style>\n<script>window.FOS_CONSOLE = '/app/';</script>\n</head>\n<body>" + body + "\n</body>\n</html>\n")
target = HERE.parent / "familyos" / "web_welcome" / "index.html"
target.parent.mkdir(exist_ok=True)
target.write_text(out)
print("wrote", target, len(out), "bytes")
