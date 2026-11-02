"""Stitch the console recording and the simulator recording into one captioned demo.
Reads web-video/*.webm + web-marks.json, mobile.mp4 + demo-test.log (DEMOMARK lines) + record-start.txt.
Writes famos-demo.mp4 next to this script."""
import glob
import json
import os
import re
import subprocess
import sys

S = os.environ.get("DEMO_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
OUT = os.path.join(S, "famos-demo.mp4")
W, H, FPS = 1920, 1080, 30
BG = "0x141414"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_R = "/System/Library/Fonts/Supplemental/Georgia.ttf"
EXTRA = sys.argv[1:]   # optional extra clips (e.g. the phone's own screen recording) appended before the end card, as path:caption

def run(args):
    print(" ".join(a if " " not in a else repr(a) for a in args)[:200]); subprocess.run(args, check=True)

def textfile(name, text):
    p = os.path.join(S, f"cap-{name}.txt"); open(p, "w").write(text); return p

def captions(marks, offset=0.0, prefix="c"):
    """drawtext filters for [(start, caption)], each shown until the next start."""
    f = []
    for i, (t, cap) in enumerate(marks):
        if not cap: continue
        end = marks[i + 1][0] if i + 1 < len(marks) else t + 60
        tf = textfile(f"{prefix}{i}", cap)
        f.append(f"drawtext=fontfile='{FONT}':textfile='{tf}':fontsize=38:fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=16:"
                 f"x=(w-text_w)/2:y=h-120:enable='between(t,{t - offset:.2f},{end - offset:.2f})'")
    return f

def label(text):
    tf = textfile("lbl-" + re.sub(r"\W", "", text), text)
    return f"drawtext=fontfile='{FONT}':textfile='{tf}':fontsize=26:fontcolor=white@0.85:box=1:boxcolor=black@0.5:boxborderw=10:x=30:y=30"

def card(name, title, sub, secs, sub2=""):
    out = os.path.join(S, f"{name}.mp4")
    t1 = textfile(name + "-t", title); t2 = textfile(name + "-s", sub); t3 = textfile(name + "-s2", sub2)
    vf = (f"drawtext=fontfile='{FONT_R}':textfile='{t1}':fontsize=96:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2-90,"
          f"drawtext=fontfile='{FONT}':textfile='{t2}':fontsize=40:fontcolor=white@0.8:x=(w-text_w)/2:y=(h-text_h)/2+50,"
          f"drawtext=fontfile='{FONT}':textfile='{t3}':fontsize=34:fontcolor=white@0.6:x=(w-text_w)/2:y=(h-text_h)/2+120")
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={BG}:s={W}x{H}:r={FPS}:d={secs}", "-vf", vf,
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    return out

def section(name, src, marks, offset, start, end, lbl, portrait):
    out = os.path.join(S, f"{name}.mp4")
    fit = f"scale=w={W}:h={H}:force_original_aspect_ratio=decrease"
    vf = ",".join([fit, f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={BG}", label(lbl)] + captions(marks, offset, name))
    args = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", src]
    if end: args += ["-t", f"{end - start:.2f}"]
    run(args + ["-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", out])
    return out

parts = [card("card-open", "FamilyOS", "One place for the family's notices, dates and bills.", 4)]

# The console: Playwright's video starts at the context's birth, so the marks are already offsets.
web = sorted(glob.glob(os.path.join(S, "web-video", "*.webm")), key=os.path.getmtime)[-1]
wm = [(m["start"], m["caption"]) for m in json.load(open(os.path.join(S, "web-marks.json")))]
web_start = max(0.0, wm[0][0] - 1.5)
parts.append(section("sec-web", web, wm, web_start, web_start, None, "The console, on the web", False))

# The phone: DEMOMARK lines carry the clock; the recording started at record-start.txt.
t0 = float(open(os.path.join(S, "record-start.txt")).read().strip())
mm = []
for line in open(os.path.join(S, "demo-test.log"), errors="replace"):
    m = re.match(r".*DEMOMARK (\d+\.\d+) (.*)$", line.strip())
    if m: mm.append((float(m.group(1)) - t0, m.group(2)))
end_t = next((t for t, c in mm if c == "end"), None)
mm = [(t, c) for t, c in mm if c != "end"]
start = max(0.0, mm[0][0] - 1.5)
# The test marks a stop after its settling pause, so the screen changes about four seconds before the mark.
parts.append(section("sec-mobile", os.path.join(S, "mobile.mp4"), mm, start + 4.0, start, end_t, "The iPhone app", True))

for i, spec in enumerate(EXTRA):
    path, _, cap = spec.partition(":")
    parts.append(section(f"sec-extra{i}", path, [(0.0, cap)], 0.0, 0.0, None, "On the phone", True))

parts.append(card("card-end", "FamilyOS", "Notices, dates, bills, errands, and the phone's own hands.", 6,
                  "Nothing is paid or booked without a parent's tap. On iOS 27, a school-app alert shares itself."))
lst = os.path.join(S, "concat.txt"); open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", OUT])
print("wrote", OUT, subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", OUT], capture_output=True, text=True).stdout.strip(), "s")
