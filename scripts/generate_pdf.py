"""Convert Family OS WORKFLOW_END_TO_END.md into a high-quality, professional PDF document."""
import os
import re
import textwrap
import markdown
from xhtml2pdf import pisa


def format_mermaid_block(mermaid_code: str) -> str:
    """Format Mermaid blocks into visually structured, clean HTML components for PDF."""
    code = mermaid_code.strip()

    # Flowchart / Graph
    if code.startswith("flowchart") or code.startswith("graph"):
        lines = [line.strip() for line in code.split("\n")[1:] if line.strip() and not line.strip().startswith("subgraph") and not line.strip().startswith("end")]
        steps_html = []
        for line in lines:
            if "-->" in line:
                parts = line.split("-->")
                src = parts[0].strip()
                dest = parts[1].strip()
                src = re.sub(r'[\(\[\{\"\)\]\}]', '', src).replace("₹", "Rs. ").replace("➔", "->").replace("—", " -- ")
                dest = re.sub(r'[\(\[\{\"\)\]\}]', '', dest).replace("₹", "Rs. ").replace("➔", "->").replace("—", " -- ")
                steps_html.append(f'<div class="flow-step"><span class="flow-node">{src}</span> <span class="flow-arrow">-&gt;</span> <span class="flow-node highlight">{dest}</span></div>')
        if steps_html:
            content = '\n'.join(steps_html)
            return textwrap.dedent(f"""
<div class="diagram-box">
<div class="diagram-title">FLOWCHART LOGIC OVERVIEW</div>
{content}
</div>
""").strip()

    # Sequence Diagram
    elif code.startswith("sequenceDiagram"):
        lines = code.split("\n")
        seq_steps = []
        step_num = 1
        for line in lines:
            line = line.strip()
            if not line or line.startswith("autonumber") or line.startswith("participant") or line.startswith("actor") or line.startswith("Note") or line.startswith("alt") or line.startswith("else") or line.startswith("end"):
                continue
            if "->>" in line or "-->>" in line:
                arrow = "-->>" if "-->>" in line else "->>"
                parts = line.split(arrow)
                sender = parts[0].strip()
                rest = parts[1].split(":", 1)
                recipient = rest[0].strip()
                desc = rest[1].strip() if len(rest) > 1 else ""
                desc = desc.replace("₹", "Rs. ").replace("➔", "->").replace("—", " -- ")
                is_response = arrow == "-->>"
                seq_steps.append(f"""<tr class="{'seq-resp' if is_response else 'seq-req'}"><td class="seq-num">#{step_num}</td><td class="seq-actor">{sender}</td><td class="seq-arrow">{'&lt;-' if is_response else '-&gt;'}</td><td class="seq-actor">{recipient}</td><td class="seq-desc">{desc}</td></tr>""")
                step_num += 1
        if seq_steps:
            rows = '\n'.join(seq_steps)
            return textwrap.dedent(f"""
<div class="diagram-box">
<div class="diagram-title">SEQUENCE INTERACTION STEPS</div>
<table class="sequence-table">
<thead>
<tr>
<th style="width: 8%;">Step</th>
<th style="width: 20%;">From</th>
<th style="width: 6%;"></th>
<th style="width: 20%;">To</th>
<th style="width: 46%;">Action / Payload</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</div>
""").strip()

    # State Diagram
    elif code.startswith("stateDiagram"):
        lines = code.split("\n")[1:]
        transitions = []
        for line in lines:
            line = line.strip()
            if "-->" in line:
                parts = line.split("-->")
                src = parts[0].strip()
                rest = parts[1].split(":", 1)
                dest = rest[0].strip()
                note = rest[1].strip() if len(rest) > 1 else ""
                note = note.replace("₹", "Rs. ").replace("➔", "->").replace("—", " -- ")
                if src == "[*]":
                    src = "START"
                if dest == "[*]":
                    dest = "END"
                transitions.append(f"""<tr><td><span class="state-badge from">{src}</span></td><td style="text-align: center; color: #2563eb; font-weight: bold;">-&gt;</td><td><span class="state-badge to">{dest}</span></td><td style="color: #475569; font-size: 7.5pt;">{note}</td></tr>""")
        if transitions:
            rows = '\n'.join(transitions)
            return textwrap.dedent(f"""
<div class="diagram-box">
<div class="diagram-title">STATE TRANSITIONS & LIFECYCLE</div>
<table class="state-table">
<thead>
<tr>
<th style="width: 26%;">Current State</th>
<th style="width: 8%;"></th>
<th style="width: 26%;">Next State</th>
<th style="width: 40%;">Transition Trigger</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</div>
""").strip()

    # Fallback to styled code block
    escaped_code = (
        code.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("₹", "Rs. ")
        .replace("➔", "->")
        .replace("—", " -- ")
    )
    return textwrap.dedent(f"""
<div class="diagram-box">
<div class="diagram-title">DIAGRAM SPECIFICATION</div>
<pre class="mermaid-code"><code>{escaped_code}</code></pre>
</div>
""").strip()


def clean_ascii_diagram(text: str) -> str:
    """Replace non-standard unicode box-drawing characters with clean standard ASCII."""
    replacements = {
        "┌": "+", "┐": "+", "└": "+", "┘": "+",
        "├": "+", "┤": "+", "┬": "+", "┴": "+", "┼": "+",
        "│": "|", "─": "-", "═": "=",
        "▲": "^", "▼": "v", "◄": "<", "►": ">",
        "✓": "[x]", "🔒": "[SECURE]", "🚀": "[EXEC]",
        "•": "*", "—": " -- ", "–": " - ",
        "“": '"', "”": '"', "’": "'", "‘": "'",
        "₹": "Rs. ", "➔": "->", "→": "->", "←": "<-",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text


def preprocess_markdown(md_text: str) -> str:
    """Preprocess markdown elements for clean PDF rendering."""
    # 0. Global cleanup of non-standard unicode glyphs that standard PDF fonts lack
    md_text = clean_ascii_diagram(md_text)

    # 1. Transform mermaid code blocks
    def replace_mermaid(match):
        m_code = match.group(1)
        return "\n\n" + format_mermaid_block(m_code) + "\n\n"

    md_text = re.sub(r'```mermaid\s*\n(.*?)\n```', replace_mermaid, md_text, flags=re.DOTALL)

    # 2. Format GitHub Alerts
    def replace_alert(match):
        alert_type = match.group(1).upper()
        content = match.group(2).strip()
        css_class = "alert-note"
        title = "NOTE"
        if alert_type == "IMPORTANT":
            css_class = "alert-important"
            title = "IMPORTANT REQUIREMENT"
        elif alert_type in ("WARNING", "CAUTION"):
            css_class = "alert-warning"
            title = "WARNING / CONSTRAINT"
        elif alert_type == "TIP":
            css_class = "alert-tip"
            title = "BEST PRACTICE TIP"

        return textwrap.dedent(f"""
<div class="alert-box {css_class}">
<div class="alert-title">{title}</div>
<div class="alert-content">{content}</div>
</div>
""").strip()

    md_text = re.sub(
        r'>\s*\[!(NOTE|IMPORTANT|WARNING|CAUTION|TIP)\]\s*\n((?:>.*(?:\n|$))*)',
        lambda m: "\n\n" + replace_alert(
            re.match(r'>\s*\[!(NOTE|IMPORTANT|WARNING|CAUTION|TIP)\]\s*\n((?:.*(?:\n|$))*)', m.group(0))
        ) + "\n\n",
        md_text
    )

    # Clean remaining leading '>' in blockquotes if any
    md_text = re.sub(r'\n>\s*', '\n', md_text)

    # 3. Format LaTeX formulas to clean HTML text
    def replace_math(match):
        f = match.group(1)
        f_clean = f.replace(r"\text{", "").replace("}", "").replace(r"\le", "<=").replace(r"\ge", ">=")
        return f'<span class="math-formula">{f_clean}</span>'

    md_text = re.sub(r'\$\$(.*?)\$\$', replace_math, md_text)
    md_text = re.sub(r'\$([^\$\n]+)\$', replace_math, md_text)

    # 4. Add page breaks before major numbered sections
    for sec_num in [2, 4, 5, 6, 7, 8, 9]:
        target_h = f"\n## {sec_num}."
        if target_h in md_text:
            md_text = md_text.replace(target_h, f'\n\n<div class="page-break"></div>\n\n## {sec_num}.')

    return md_text


def generate_html_document(html_body: str) -> str:
    """Wrap HTML body in a print-ready CSS template for xhtml2pdf."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Family OS — Comprehensive End-to-End Workflow</title>
<style>
    @page {{
        size: a4 portrait;
        margin: 2.2cm 1.5cm 2.2cm 1.5cm;
        @frame header_frame {{
            -pdf-frame-content: header_content;
            left: 42pt; width: 512pt; top: 20pt; height: 25pt;
        }}
        @frame footer_frame {{
            -pdf-frame-content: footer_content;
            left: 42pt; width: 512pt; top: 805pt; height: 25pt;
        }}
    }}

    body {{
        font-family: Helvetica, Arial, sans-serif;
        font-size: 9pt;
        color: #1e293b;
        line-height: 1.45;
    }}

    #header_content {{
        font-size: 7.5pt;
        color: #64748b;
        border-bottom: 0.5pt solid #cbd5e1;
        padding-bottom: 4pt;
        text-transform: uppercase;
        letter-spacing: 0.5pt;
    }}

    #footer_content {{
        font-size: 7.5pt;
        color: #64748b;
        border-top: 0.5pt solid #cbd5e1;
        padding-top: 4pt;
        text-align: right;
    }}

    .page-break {{
        page-break-before: always;
    }}

    /* Typography */
    h1 {{
        font-size: 16pt;
        color: #0f172a;
        margin-top: 0;
        margin-bottom: 6pt;
        font-weight: bold;
    }}

    h2 {{
        font-size: 12pt;
        color: #1e3a8a;
        margin-top: 14pt;
        margin-bottom: 8pt;
        border-bottom: 1.5pt solid #3b82f6;
        padding-bottom: 3pt;
        page-break-after: avoid;
    }}

    h3 {{
        font-size: 10pt;
        color: #1e293b;
        margin-top: 11pt;
        margin-bottom: 5pt;
        font-weight: bold;
        page-break-after: avoid;
    }}

    h4 {{
        font-size: 9pt;
        color: #334155;
        margin-top: 9pt;
        margin-bottom: 4pt;
        font-weight: bold;
        page-break-after: avoid;
    }}

    p {{
        margin-top: 0;
        margin-bottom: 6pt;
        text-align: justify;
    }}

    ul, ol {{
        margin-top: 0;
        margin-bottom: 6pt;
        padding-left: 18pt;
    }}

    li {{
        margin-bottom: 3pt;
    }}

    hr {{
        border: 0;
        border-top: 0.5pt solid #e2e8f0;
        margin: 10pt 0;
    }}

    /* Tables */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin-top: 6pt;
        margin-bottom: 10pt;
        font-size: 8pt;
        page-break-inside: avoid;
    }}

    th {{
        background-color: #1e3a8a;
        color: #ffffff;
        font-weight: bold;
        padding: 5pt 6pt;
        text-align: left;
        border: 0.5pt solid #1e3a8a;
    }}

    td {{
        padding: 4pt 6pt;
        border: 0.5pt solid #e2e8f0;
        vertical-align: top;
    }}

    tr:nth-child(even) td {{
        background-color: #f8fafc;
    }}

    /* Code Blocks */
    pre {{
        background-color: #f1f5f9;
        border: 0.5pt solid #cbd5e1;
        border-radius: 3pt;
        padding: 6pt 8pt;
        font-family: Courier, monospace;
        font-size: 7pt;
        line-height: 1.25;
        margin-top: 4pt;
        margin-bottom: 8pt;
        page-break-inside: avoid;
        white-space: pre-wrap;
    }}

    code {{
        font-family: Courier, monospace;
        background-color: #f1f5f9;
        font-size: 7.5pt;
        padding: 1pt 3pt;
        border-radius: 2pt;
        color: #0f172a;
    }}

    pre code {{
        background-color: transparent;
        padding: 0;
        font-size: 7pt;
    }}

    .math-formula {{
        font-family: Courier, monospace;
        font-weight: bold;
        background-color: #f8fafc;
        padding: 2pt 4pt;
        border: 0.5pt solid #cbd5e1;
        border-radius: 2pt;
        color: #1e3a8a;
        font-size: 8pt;
    }}

    /* Alerts */
    .alert-box {{
        padding: 6pt 10pt;
        margin-top: 6pt;
        margin-bottom: 10pt;
        border-radius: 3pt;
        page-break-inside: avoid;
    }}

    .alert-note {{
        background-color: #eff6ff;
        border-left: 3pt solid #3b82f6;
    }}

    .alert-important {{
        background-color: #faf5ff;
        border-left: 3pt solid #8b5cf6;
    }}

    .alert-warning {{
        background-color: #fffbeb;
        border-left: 3pt solid #f59e0b;
    }}

    .alert-tip {{
        background-color: #f0fdf4;
        border-left: 3pt solid #22c55e;
    }}

    .alert-title {{
        font-size: 7.5pt;
        font-weight: bold;
        text-transform: uppercase;
        margin-bottom: 3pt;
        color: #1e293b;
    }}

    .alert-content {{
        font-size: 8pt;
        color: #334155;
    }}

    /* Diagram Styling */
    .diagram-box {{
        background-color: #f8fafc;
        border: 1pt solid #cbd5e1;
        border-radius: 4pt;
        padding: 6pt 8pt;
        margin-top: 6pt;
        margin-bottom: 10pt;
        page-break-inside: avoid;
    }}

    .diagram-title {{
        font-size: 7.5pt;
        font-weight: bold;
        color: #1e3a8a;
        letter-spacing: 0.5pt;
        margin-bottom: 5pt;
        border-bottom: 0.5pt solid #cbd5e1;
        padding-bottom: 2pt;
    }}

    .sequence-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 7pt;
    }}

    .sequence-table th {{
        background-color: #334155;
        color: #ffffff;
        font-size: 7pt;
        padding: 3.5pt;
    }}

    .sequence-table td {{
        padding: 3pt 4pt;
        border: 0.5pt solid #e2e8f0;
    }}

    .seq-num {{
        font-weight: bold;
        color: #2563eb;
        text-align: center;
    }}

    .seq-actor {{
        font-weight: bold;
        color: #1e293b;
    }}

    .seq-arrow {{
        text-align: center;
        color: #64748b;
        font-weight: bold;
    }}

    .seq-desc {{
        color: #334155;
        font-family: Courier, monospace;
        font-size: 6.5pt;
    }}

    .seq-resp td {{
        background-color: #f8fafc;
    }}

    .state-table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 7.5pt;
    }}

    .state-badge {{
        display: inline-block;
        padding: 1pt 4pt;
        font-size: 6.5pt;
        font-weight: bold;
        border-radius: 2pt;
        font-family: Courier, monospace;
    }}

    .state-badge.from {{
        background-color: #e2e8f0;
        color: #1e293b;
    }}

    .state-badge.to {{
        background-color: #dbeafe;
        color: #1e40af;
    }}

    .flow-step {{
        margin-bottom: 3pt;
        font-size: 7.5pt;
    }}

    .flow-node {{
        display: inline-block;
        background-color: #e2e8f0;
        padding: 1.5pt 4pt;
        border-radius: 2pt;
        font-weight: bold;
        color: #1e293b;
    }}

    .flow-node.highlight {{
        background-color: #dbeafe;
        color: #1e40af;
    }}

    .flow-arrow {{
        color: #3b82f6;
        font-weight: bold;
        margin: 0 4pt;
    }}

    /* Title Cover Box */
    .doc-header-box {{
        background-color: #0f172a;
        color: #ffffff;
        padding: 14pt;
        border-radius: 4pt;
        margin-bottom: 12pt;
    }}

    .doc-header-box h1 {{
        color: #ffffff;
        font-size: 18pt;
        margin: 0 0 5pt 0;
    }}

    .doc-header-box .subtitle {{
        color: #94a3b8;
        font-size: 10pt;
        margin: 0 0 8pt 0;
    }}

    .meta-tag {{
        display: inline-block;
        background-color: #1e293b;
        color: #38bdf8;
        font-size: 7pt;
        font-weight: bold;
        padding: 2pt 5pt;
        border-radius: 2pt;
        margin-right: 5pt;
    }}
</style>
</head>
<body>

<div id="header_content">Family OS &bull; Technical Architecture &amp; Workflow Specification</div>
<div id="footer_content">Confidential &bull; Family OS Core Engine &bull; Page <pdf:pagenumber> of <pdf:pagecount></div>

<div class="doc-header-box">
    <h1>Family OS</h1>
    <div class="subtitle">Comprehensive End-to-End Workflow Specification</div>
    <div>
        <span class="meta-tag">VERSION 0.1.0</span>
        <span class="meta-tag">FGP DETERMINISTIC GOVERNANCE</span>
        <span class="meta-tag">REAL MARKETPLACE ADB AGENT</span>
        <span class="meta-tag">HARD PAYMENT BOUNDARY</span>
    </div>
</div>

{html_body}

</body>
</html>
"""


def convert_markdown_to_pdf(input_md_path: str, output_pdf_path: str) -> bool:
    """Execute complete Markdown to PDF compilation."""
    print(f"Reading markdown from: {input_md_path}")
    with open(input_md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # Preprocess
    print("Preprocessing markdown (diagrams, alerts, page breaks)...")
    processed_md = preprocess_markdown(md_content)

    # Convert to HTML
    print("Converting Markdown to HTML...")
    html_body = markdown.markdown(
        processed_md,
        extensions=["tables", "fenced_code", "toc", "nl2br"]
    )

    # Wrap in layout template
    full_html = generate_html_document(html_body)

    # Compile to PDF
    print(f"Compiling PDF using xhtml2pdf to: {output_pdf_path}...")
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)
    with open(output_pdf_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(full_html, dest=pdf_file)

    if pisa_status.err:
        print(f"Error during PDF generation: {pisa_status.err}")
        return False

    file_size_kb = os.path.getsize(output_pdf_path) / 1024
    print(f"Successfully generated PDF: {output_pdf_path} ({file_size_kb:.1f} KB)")
    return True


if __name__ == "__main__":
    src_md = "d:/FamilyOS/docs/WORKFLOW_END_TO_END.md"
    dst_pdf = "d:/FamilyOS/docs/WORKFLOW_END_TO_END.pdf"
    convert_markdown_to_pdf(src_md, dst_pdf)
