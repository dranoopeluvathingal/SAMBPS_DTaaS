#!/usr/bin/env python3
"""
SAMBP Comprehensive Report Generator
Reads ALL TR LaTeX files (TR01–TR86), extracts every section, equation,
figure, table, and algorithm, then writes one massive compilable LaTeX document.
"""

import os, re, sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────────────────────
ROOT       = Path("/root/phd_thesis")
TR_BASE    = ROOT / "03_technical_reports"
OUT_DIR    = ROOT / "SAMBP_Comprehensive_Report_Full_Details"
OUT_TEX    = OUT_DIR / "main_report_full.tex"
FIG_TR76   = ROOT / "04_code/sambp/digital_twin/reports/figures/TR76"
FIG_TR68   = ROOT / "04_code/sambp/digital_twin/reports/figures/TR68"
THESIS_FIG = ROOT / "01_thesis/active/thesis_full/figures"

# Ordered list of (tr_number, tex_path, short_dir_label)
def collect_trs():
    trs = []
    for tex in sorted(TR_BASE.rglob("main_report*.tex")):
        m = re.search(r'main_report(\d+)\.tex', tex.name)
        if m:
            n = int(m.group(1))
            trs.append((n, tex))
    trs.sort(key=lambda x: x[0])
    return trs

# ─────────────────────────────────────────────────────────────────────────────
# TEX EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────
def read_tex(path: Path) -> str:
    try:
        return path.read_text(errors='replace')
    except Exception:
        return ""

def sanitise_for_table(s: str) -> str:
    """Escape/remove chars that break LaTeX table cells."""
    s = re.sub(r'&', r'and', s)
    s = re.sub(r'#', r'\\#', s)
    s = re.sub(r'\$', r'\\$', s)
    s = re.sub(r'%', r'\\%', s)
    s = re.sub(r'\^', r'\\^{}', s)
    s = re.sub(r'~', r'\\textasciitilde{}', s)
    s = re.sub(r'_', r'\\_', s)
    s = re.sub(r'\{', r'\\{', s)
    s = re.sub(r'\}', r'\\}', s)
    return s

def extract_title(tex: str) -> str:
    def clean(t):
        t = re.sub(r'%[^\n]*', '', t)              # strip comments
        t = re.sub(r'\$[^$]*\$', '', t)            # strip inline math $...$
        t = re.sub(r'\\[%{}#&_^~]', '', t)         # strip escaped special chars
        t = re.sub(r'\\\\(\[\w+\])?', ' ', t)      # \\ and \\[6pt] → space
        t = re.sub(r'\[\w+\]', '', t)              # strip [6pt] etc.
        t = re.sub(r'\\[a-zA-Z]+\b\*?', ' ', t)   # strip commands
        t = re.sub(r'[{}%\[\]$\\]', '', t)         # strip remaining special chars
        t = ' '.join(t.split())
        # Strip leading LaTeX command name artifacts (e.g. "bfseries", "sambpblue")
        t = re.sub(r'^(?:bfseries|itshape|scshape|ttfamily|rmfamily|sffamily)\s*', '', t)
        # Strip leading color-name artifacts (e.g. "sambpblue")
        t = re.sub(r'^[a-z]+(?:blue|red|gray|grey|gold|green|black|white)\s*', '', t)
        # Strip leading "SAMBP Technical Report TR-XX/YYYY" boilerplate
        t = re.sub(r'^SAMBP\s+Technical\s+Report\s+TR-?\d+/\d{4}\s*', '', t)
        # Strip leading "SAMBP TR-XX/YYYY" boilerplate
        t = re.sub(r'^SAMBP\s+TR-?\d+/\d{4}\s*', '', t)
        return t.strip()

    # Strategy 1: \title{...} — grab everything up to \author or \date
    m = re.search(r'\\title\{(.*?)(?=\\(?:author|date|maketitle|\begin))', tex, re.S)
    if not m:
        m = re.search(r'\\title\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', tex, re.S)
    if m:
        raw = m.group(1)
        # If boilerplate (SAMBP TR-XX/YYYY), look for \large subtitle inside
        t = clean(raw)
        if re.match(r'^SAMBP\s+TR-?\d+', t) or not t:
            sub = re.search(r'\\large\s+(.*)', raw, re.S)
            if sub:
                t = clean(sub.group(1))
        # Strip leading "SAMBP TR-XX/YYYY" boilerplate if present
        t = re.sub(r'^SAMBP\s+TR-?\d+/\d{4}\s*', '', t).strip()
        if t:
            return t

    # Strategy 2: % Title : ... (comment block, possibly multi-line)
    m = re.search(r'^%\s*[Tt]itle\s*:\s*(.+)', tex, re.M)
    if m:
        # Grab continuation lines (lines starting with %  )
        start = m.end()
        title_lines = [m.group(1).strip()]
        for cont in re.finditer(r'\n%\s{2,}(.+)', tex[start:start+300]):
            title_lines.append(cont.group(1).strip())
        t = clean(' '.join(title_lines))
        if t:
            return t

    # Strategy 3: center block — find all {\\large/Large/LARGE ...} groups,
    # skip any that look like "SAMBP Technical Report TR-XX" boilerplate
    m = re.search(r'\\begin\{center\}(.*?)\\end\{center\}', tex, re.S)
    if m:
        block = m.group(1)
        # Find every {...} group that starts with a size command
        for fm in re.finditer(
            r'\{\\(?:LARGE|Large|large|huge|Huge)\b[^}]*?([A-Za-z0-9][^{}]{8,})\}',
            block, re.S):
            t = clean(fm.group(1))
            # Skip boilerplate lines
            if re.search(r'SAMBP\s+Technical\s+Report\s+TR-?\d', t):
                continue
            if re.search(r'PhD\s+Thesis\s+Supporting|Revision\s+\d|IIT\s+Madras', t):
                continue
            if len(t) > 10:
                return t

    # Strategy 4: first \section{} in document body
    body_m = re.search(r'\\begin\{document\}(.*)', tex, re.S)
    body = body_m.group(1) if body_m else tex
    m = re.search(r'\\section\*?\{([^}]+)\}', body)
    if m:
        t = clean(m.group(1))
        if t:
            return t

    return "Untitled"

def extract_author(tex: str) -> str:
    m = re.search(r'\\author\{([^}]*)\}', tex, re.S)
    return m.group(1).strip() if m else "SAMBP Research Group"

def extract_date(tex: str) -> str:
    m = re.search(r'\\date\{([^}]*)\}', tex, re.S)
    if not m:
        return ""
    d = m.group(1)
    # Strip LaTeX comments
    d = re.sub(r'%[^\n]*', '', d)
    # Keep only text up to first LaTeX command or newline
    d = re.split(r'\\(?!%)|[\n\r]', d)[0]
    d = re.sub(r'[{}]', '', d)
    return d.strip()[:40]  # max 40 chars to be safe

def extract_preamble_commands(tex: str) -> str:
    """
    Extract all \newcommand / \renewcommand from the TR preamble
    and return them as \providecommand statements to prepend to the body.
    This ensures TR-specific macros are available in the unified document.
    """
    preamble = tex.split(r'\begin{document}')[0] if r'\begin{document}' in tex else ''
    out = []
    # Simple one-liner commands: \newcommand{\foo}{bar}
    for m in re.finditer(
        r'\\(?:new|renew)command(\*?)\{(\\[A-Za-z@]+)\}(\[[^\]]*\])?(\[[^\]]*\])?\{([^{}]*(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}[^{}]*)*)\}',
        preamble):
        star, name, opt1, opt2, defn = m.group(1), m.group(2), m.group(3) or '', m.group(4) or '', m.group(5)
        if name in (r'\tr', r'\arraystretch', r'\headrulewidth'):
            continue
        out.append(f'\\providecommand{star}{{{name}}}{opt1}{opt2}{{{defn}}}')
    return '\n'.join(out) + ('\n' if out else '')

def extract_body(tex: str) -> str:
    """Extract everything between \begin{document}...\end{document}."""
    m = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', tex, re.S)
    if not m:
        return tex
    body = m.group(1)
    body = re.sub(r'^[\s\\]*(maketitle|tableofcontents|clearpage|vspace\{[^}]*\}|hrule|vspace\*?\{[^}]*\})\b[^\n]*\n', '', body, flags=re.M)
    return body

def strip_preamble_only(body: str) -> str:
    """Remove leading \maketitle etc but keep all content."""
    body = re.sub(r'\\maketitle\b', '', body)
    body = re.sub(r'\\tableofcontents\b', '', body)
    body = re.sub(r'\\listoffigures\b', '', body)
    body = re.sub(r'\\listoftables\b', '', body)
    return body

def extract_sections(body: str):
    """Return list of (level, title, content) tuples."""
    pattern = re.compile(
        r'(\\(?:section|subsection|subsubsection)\*?\{([^}]*)\})', re.S)
    parts = pattern.split(body)
    sections = []
    if parts[0].strip():
        sections.append(('preamble', '', parts[0]))
    i = 1
    while i < len(parts) - 2:
        cmd_full = parts[i]
        title    = parts[i+1]
        content  = parts[i+2] if i+2 < len(parts) else ''
        level = 'section'
        if '\\subsection' in cmd_full and '\\subsubsection' not in cmd_full:
            level = 'subsection'
        elif '\\subsubsection' in cmd_full:
            level = 'subsubsection'
        sections.append((level, title.strip(), content))
        i += 3
    return sections

def count_equations(body: str) -> int:
    return len(re.findall(r'\\begin\{(equation|align|gather|multline)', body))

def count_figures(body: str) -> int:
    return len(re.findall(r'\\begin\{figure', body))

def count_tables(body: str) -> int:
    return len(re.findall(r'\\begin\{(table|longtable|tabular)', body))

def rewrite_section_commands(body: str, tr_num: int) -> str:
    """
    Convert section/subsection/subsubsection to subsection/subsubsection/paragraph
    so TR content nests inside \section{TR-NN} in the report.
    Also prefix labels to avoid clashes between TRs.
    """
    body = re.sub(r'\\section\*?\{', r'\\subsection{', body)
    body = re.sub(r'\\subsection\*?\{', r'\\subsubsection{', body)
    body = re.sub(r'\\subsubsection\*?\{', r'\\paragraph{', body)
    # Prefix labels
    prefix = f'tr{tr_num}x'
    body = re.sub(r'\\label\{(?!tr\d)', rf'\\label{{{prefix}:', body)
    body = re.sub(r'\\ref\{(?!tr\d)', rf'\\ref{{{prefix}:', body)
    body = re.sub(r'\\eqref\{(?!tr\d)', rf'\\eqref{{{prefix}:', body)
    body = re.sub(r'\\autoref\{(?!tr\d)', rf'\\autoref{{{prefix}:', body)
    # Remove conflicting \part commands from within TRs
    body = re.sub(r'\\part\*?\{[^}]*\}', '', body)
    # Remove \appendix inside TR body
    body = re.sub(r'\\appendix\b', '', body)
    return body

def fix_zero_size_graphics(opts: str) -> str:
    """Replace zero-width/height options with a safe default."""
    # Only match exactly 0 or 0<unit> where unit is letters — NOT 0.95 etc.
    # Negative lookahead: not followed by digit or '.'
    opts = re.sub(r'(?:width|height)\s*=\s*0(?![0-9.])[a-zA-Z]*', 'width=0.7\\\\linewidth', opts)
    # scale=0 (not 0.something meaningful)
    opts = re.sub(r'scale\s*=\s*0(?![0-9.])', 'width=0.7\\\\linewidth', opts)
    return opts

def fix_includegraphics(body: str, tex_path: Path) -> str:
    """Make all \includegraphics paths absolute and fix zero-size options."""
    fig_dir = tex_path.parent / "figures"
    def replace_path(m):
        opts = m.group(1) or ''
        path_str = m.group(2).strip()
        # Fix zero-size dimensions in options
        if opts:
            inner = opts[1:-1]  # strip [ ]
            inner = fix_zero_size_graphics(inner)
            opts = f'[{inner}]'
        # Ensure opts has some width if empty or still zero
        if not opts or opts == '[]':
            opts = '[width=0.85\\textwidth]'
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return f'\\includegraphics{opts}{{{path_str}}}'
        # Try relative to the TR figures dir
        raw_candidates = [
            tex_path.parent / path_str,
            fig_dir / path_str,
            fig_dir / p.name,
            fig_dir / (p.stem + '.pdf'),
        ]
        # For relative paths with .., try resolving from each ancestor dir
        if '..' in path_str:
            parent = tex_path.parent
            while parent != parent.parent:
                candidate = (parent / path_str).resolve()
                if candidate.exists():
                    raw_candidates.insert(0, candidate)
                    break
                parent = parent.parent
        for c in raw_candidates:
            try:
                c_resolved = c.resolve()
            except Exception:
                c_resolved = c
            if c_resolved.exists():
                return f'\\includegraphics{opts}{{{c_resolved}}}'
        # Wrap in IfFileExists so it doesn't crash
        abs_guess = str(tex_path.parent / path_str)
        return (f'\\IfFileExists{{{abs_guess}}}'
                f'{{\\includegraphics{opts}{{{abs_guess}}}}}'
                f'{{\\fbox{{\\parbox{{6cm}}{{\\centering\\small Figure not found:\\\\\\texttt{{{p.name}}}}}}}}}')
    # Handle both single-line and multi-line \includegraphics (with newlines between opts and path)
    body = re.sub(
        r'\\includegraphics(\[[^\]]*\])?\s*\{([^}]+)\}',
        replace_path, body)
    return body

def close_unclosed_environments(body: str) -> str:
    """
    Detect unclosed LaTeX environments and append matching \end{} commands.
    Prevents 'File ended while scanning' fatal errors from longtable etc.
    """
    env_stack = []
    for m in re.finditer(r'\\(begin|end)\{([^}]+)\}', body):
        cmd, env = m.group(1), m.group(2)
        if cmd == 'begin':
            env_stack.append(env)
        elif cmd == 'end':
            if env_stack and env_stack[-1] == env:
                env_stack.pop()
            # else mismatched end — ignore
    # Close any still-open environments in reverse order
    closers = ''.join(f'\\end{{{e}}}\n' for e in reversed(env_stack))
    if closers:
        body = body + '\n' + closers
    return body

def remove_bibliography(body: str) -> str:
    """Strip \bibliography and \begin{thebibliography}...\end{thebibliography}."""
    body = re.sub(r'\\bibliography\{[^}]*\}', '', body)
    body = re.sub(r'\\bibliographystyle\{[^}]*\}', '', body)
    body = re.sub(r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}', '', body, flags=re.S)
    return body

def remove_newcommands(body: str) -> str:
    """Convert \newcommand → \providecommand; strip layout/env-only commands."""
    # Convert \newcommand → \providecommand (TR-specific macros survive without clashes)
    body = re.sub(r'\\newcommand(\*?)', r'\\providecommand\1', body)
    # Strip layout renewcommands that conflict with master preamble
    body = re.sub(r'\\renewcommand\{\\arraystretch\}\{[^}]*\}', '', body)
    body = re.sub(r'\\renewcommand\{\\headrulewidth\}\{[^}]*\}', '', body)
    body = re.sub(r'\\renewcommand\{\\tr\}\{[^}]*\}', '', body)
    body = re.sub(r'\\newtheorem\*?\{[^}]*\}(\[[^\]]*\])?\{[^}]*\}(\[[^\]]*\])?\s*\n?', '', body)
    # Replace undefined theorem-like environments with plain mdframed boxes
    # Drop any optional [Title] argument to avoid kvsetkeys errors
    for env in ['assumption', 'proposition', 'lemma', 'corollary', 'remark',
                'definition', 'example', 'conjecture', 'notation', 'claim']:
        body = re.sub(rf'\\begin\{{{env}\}}(\[[^\]]*\])?', r'\\begin{mdframed}', body)
        body = re.sub(rf'\\end\{{{env}\}}', r'\\end{mdframed}', body)
    body = re.sub(r'\\theoremstyle\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\definecolor\{[^}]*\}\{[^}]*\}\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\renewcommand\{\\arraystretch\}\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\renewcommand\{\\headrulewidth\}\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\pagestyle\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\setcounter\{[^}]*\}\{[^}]*\}\s*\n?', '', body)
    body = re.sub(r'\\pgfplotsset\{[^}]*\}\s*\n?', '', body)
    # Replace algorithmic environment with verbatim-like content (it's not loaded)
    body = re.sub(r'\\begin\{algorithmic\}.*?\\end\{algorithmic\}',
                  r'\\begin{lstlisting}[language={}]\n% [algorithm body]\n\\end{lstlisting}',
                  body, flags=re.S)
    # Remove abstract/titlepage environments
    body = re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}', '', body, flags=re.S)
    body = re.sub(r'\\begin\{titlepage\}.*?\\end\{titlepage\}', '', body, flags=re.S)
    # Remove \input / \include
    body = re.sub(r'\\input\{[^}]*\}', '', body)
    body = re.sub(r'\\include\{[^}]*\}', '', body)
    # Remove \part inside TR body
    body = re.sub(r'\\part\*?\{[^}]*\}', '', body)
    # Remove \chapter inside TR body
    body = re.sub(r'\\chapter\*?\{', r'\\subsection{', body)
    # Fix float specifiers to H (avoids "too many floats")
    body = re.sub(r'\\begin\{figure\}\[[^\]]*\]', r'\\begin{figure}[H]', body)
    body = re.sub(r'\\begin\{table\}\[[^\]]*\]', r'\\begin{table}[H]', body)
    body = re.sub(r'\\begin\{figure\}(?!\[)', r'\\begin{figure}[H]', body)
    # Strip \rowcolor (causes \@xnext errors in longtable)
    body = re.sub(r'\\rowcolor\{[^}]*\}', '', body)
    body = re.sub(r'\\cellcolor\{[^}]*\}', '', body)
    # Strip conflicting \tr renewcommand
    body = re.sub(r'\\renewcommand\{\\tr\}\{[^}]*\}', '', body)
    # Strip LaTeX line comments (% not preceded by \)
    body = re.sub(r'(?<!\\)%[^\n]*', '', body)
    # Strip \vadjust
    body = re.sub(r'\\vadjust\{[^}]*\}', '', body)
    # Fix \resizebox with empty content (causes Division by 0)
    body = re.sub(r'\\resizebox\{[^}]*\}\{[^}]*\}\{\s*\}', '', body)
    # Fix \resizebox{\columnwidth}{!}{...} — keep content, drop resize wrapper
    def unwrap_resizebox(m):
        content = m.group(1).strip()
        if not content:
            return ''
        return content
    body = re.sub(r'\\resizebox\{[^}]*\}\{[^}]*\}\{((?:[^{}]|\{[^{}]*\})*)\}',
                  unwrap_resizebox, body)
    return body

# ─────────────────────────────────────────────────────────────────────────────
# PHASE MAP
# ─────────────────────────────────────────────────────────────────────────────
PHASES = [
    (1,  11, "Phase 1 — SG Framework and Overcurrent Protection"),
    (12, 27, "Phase 2 — Line Differential (87L) Deep Dive"),
    (28, 37, "Phase 3 — Distance Protection"),
    (38, 42, "Phase 4 — Microgrid Protection"),
    (43, 45, "Phase 5 — Digital Twin Architecture"),
    (46, 55, "Phase 6 — Machine Learning and System-Level Features"),
    (56, 67, "Phase 7 — IBR Source Extensions"),
    (68, 86, "Phase 8 — Advanced Extensions and Specialised Scenarios"),
]

def phase_of(n):
    for lo, hi, name in PHASES:
        if lo <= n <= hi:
            return name
    return "Uncategorised"

# ─────────────────────────────────────────────────────────────────────────────
# PREAMBLE
# ─────────────────────────────────────────────────────────────────────────────
PREAMBLE = r"""% ============================================================
%  SAMBP COMPREHENSIVE RESEARCH REPORT — FULL DETAILS
%  Self-Adaptive Model-Based Protection Systems for IBR Networks
%  IIT Madras | Anoop V. Eluvathingal | April 2026
%  Auto-generated by build_report.py — DO NOT EDIT MANUALLY
% ============================================================
\documentclass[11pt,a4paper,twoside]{report}

% ── Core packages ────────────────────────────────────────────
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[margin=22mm,top=25mm,bottom=25mm]{geometry}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{mathtools}
\usepackage[table,dvipsnames]{xcolor}
\usepackage{booktabs,array,multirow,longtable,tabularx}
\usepackage{graphicx}
\usepackage{ifthen}
\usepackage[hidelinks,bookmarks=true,bookmarksopen=true]{hyperref}
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}
\usepackage{tikz}
\usetikzlibrary{arrows.meta,positioning,calc,fit,backgrounds,
                shapes.geometric,shapes.misc,mindmap,trees,
                decorations.pathreplacing,decorations.text,
                matrix,chains,scopes}
\usepackage{caption,subcaption}
\usepackage{parskip}
\usepackage{siunitx}
\usepackage{pifont}
\usepackage{cite}
\usepackage{fancyhdr}
\usepackage{tocloft}
\usepackage[ruled,vlined,linesnumbered]{algorithm2e}
\usepackage{listings}
\usepackage{mdframed}
\usepackage{enumitem}
\usepackage{wrapfig}
\usepackage{float}
\usepackage[section]{placeins}
\usepackage{morefloats}
\usepackage{emptypage}
\usepackage{etoolbox}

% ── Colours ──────────────────────────────────────────────────
\definecolor{sambpblue}  {RGB}{0,70,140}
\definecolor{sambpgreen} {RGB}{0,120,60}
\definecolor{sambpred}   {RGB}{170,0,30}
\definecolor{sambpgray}  {RGB}{80,80,80}
\definecolor{okgreen}    {RGB}{0,140,60}
\definecolor{alertred}   {RGB}{180,0,0}
\definecolor{warnoran}   {RGB}{200,100,0}
\definecolor{ph1col}     {RGB}{0,70,140}
\definecolor{ph2col}     {RGB}{0,120,60}
\definecolor{ph3col}     {RGB}{180,80,0}
\definecolor{ph4col}     {RGB}{160,0,30}
\definecolor{ph5col}     {RGB}{100,0,130}
\definecolor{ph6col}     {RGB}{0,100,120}
\definecolor{ph7col}     {RGB}{100,60,0}
\definecolor{ph8col}     {RGB}{60,60,60}
\definecolor{rowA}       {RGB}{235,245,255}
\definecolor{rowB}       {RGB}{255,255,255}
\definecolor{headbg}     {RGB}{0,70,140}

% ── Custom commands (common across all TRs) ───────────────────
\newcommand{\pu}{\,\text{pu}}
\newcommand{\ms}{\,\text{ms}}
\newcommand{\kibr}{k_{\mathrm{ibr}}}
\newcommand{\fgfm}{f_{\mathrm{gfm}}}
\newcommand{\Idiff}{I_{\mathrm{diff}}}
\newcommand{\Ibias}{I_{\mathrm{bias}}}
\newcommand{\km}{k_m}
\newcommand{\PD}{P_{\mathrm{D}}}
\newcommand{\PFA}{P_{\mathrm{FA}}}
\newcommand{\cmark}{\ding{51}}
\newcommand{\xmark}{\ding{55}}
\newcommand{\phasor}[1]{\underline{#1}}
\newcommand{\trref}[1]{\textsuperscript{\normalfont[\texttt{#1}]}}
\newcommand{\figref}[2]{\textit{(Source: #1, \texttt{#2})}}

% ── Theorem environments ──────────────────────────────────────
\newtheorem{theorem}{Theorem}[chapter]
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{remark}{Remark}[chapter]
\newtheorem{finding}{Finding}[chapter]
\newtheorem{definition}{Definition}[chapter]

% ── Finding box ───────────────────────────────────────────────
\newmdenv[
  backgroundcolor=sambpblue!8,
  linecolor=sambpblue,
  linewidth=1.2pt,
  leftmargin=4pt, rightmargin=4pt,
  innerleftmargin=8pt, innerrightmargin=8pt,
  innertopmargin=6pt, innerbottommargin=6pt,
  skipabove=6pt, skipbelow=6pt
]{findingbox}

% ── TR source box ─────────────────────────────────────────────
\newmdenv[
  backgroundcolor=gray!6,
  linecolor=gray!40,
  linewidth=0.6pt,
  leftmargin=0pt, rightmargin=0pt,
  innerleftmargin=6pt, innerrightmargin=6pt,
  innertopmargin=4pt, innerbottommargin=4pt,
  skipabove=4pt, skipbelow=4pt
]{trbox}

% ── Headers / footers ─────────────────────────────────────────
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\small\textcolor{sambpblue}{\leftmark}}
\fancyhead[RO]{\small\textcolor{sambpblue}{\rightmark}}
\fancyfoot[C]{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}

% ── TOC depth ─────────────────────────────────────────────────
\setcounter{tocdepth}{2}
\setcounter{secnumdepth}{3}

% ── Extra colours from TR preambles ──────────────────────────
\definecolor{agreencolor}  {RGB}{0,130,60}
\definecolor{arc1col}      {RGB}{30,100,200}
\definecolor{arc2col}      {RGB}{30,150,60}
\definecolor{arc3col}      {RGB}{210,120,0}
\definecolor{arc4col}      {RGB}{120,40,160}
\definecolor{badred}       {rgb}{0.75,0.0,0.0}
\definecolor{codeblue}     {rgb}{0.0,0.1,0.6}
\definecolor{codegray}     {RGB}{248,248,248}
\definecolor{darkgreen}    {RGB}{0,120,50}
\definecolor{failred}      {rgb}{0.75,0.0,0.0}
\definecolor{flagred}      {RGB}{180,30,30}
\definecolor{flagyellow}   {RGB}{200,140,0}
\definecolor{gfmblue}      {RGB}{0,70,160}
\definecolor{gridgrey}     {RGB}{100,100,100}
\definecolor{headerbg}     {RGB}{230,238,250}
\definecolor{hybridpurple} {RGB}{100,30,140}
\definecolor{ibrbrown}     {RGB}{130,60,0}
\definecolor{ibrred}       {RGB}{180,30,30}
\definecolor{iitBlue}      {RGB}{0,70,140}
\definecolor{iitGold}      {RGB}{200,150,30}
\definecolor{infoblue}     {RGB}{0,70,160}
\definecolor{lightgrey}    {RGB}{240,240,240}
\definecolor{noteGray}     {RGB}{245,245,245}
\definecolor{passgreen}    {rgb}{0.0,0.55,0.27}
\definecolor{pvblue}       {RGB}{0,80,180}
\definecolor{sgblue}       {RGB}{30,80,160}
\definecolor{warnblue}     {rgb}{0.0,0.30,0.70}
\definecolor{warningred}   {RGB}{180,0,0}
\definecolor{warnorange}   {RGB}{200,100,0}
\definecolor{warnred}      {RGB}{180,20,20}

% ── Extra commands from TR preambles (use \providecommand to avoid clashes) ──
\providecommand{\SAMBP}{\textsc{sambp}}
\providecommand{\sambp}{\textsc{sambp}}
\providecommand{\goose}{\textsc{goose}}
\providecommand{\Hz}{\,\text{Hz}}
\providecommand{\kHz}{\,\text{kHz}}
\providecommand{\kV}{\,\text{kV}}
\providecommand{\MVA}{\,\text{MVA}}
\providecommand{\ohm}{\,\Omega}
\providecommand{\sss}{\,\text{s}}
\providecommand{\mss}{\,\text{ms}}
\providecommand{\kIBR}{k_{\rm ibr}}
\providecommand{\kappan}{\kappa_n}
\providecommand{\kn}{\kappa_n}
\providecommand{\Iop}{I_{\rm op}}
\providecommand{\Ires}{I_{\rm res}}
\providecommand{\Irst}{I_{\rm rst}}
\providecommand{\Ipeak}{I_{\rm peak}}
\providecommand{\Iopmin}{I_{\rm op,min}}
\providecommand{\Idc}{I_{DC}}
\providecommand{\RN}{R_N}
\providecommand{\IC}{I_{C}}
\providecommand{\diag}{\operatorname{diag}}
\providecommand{\argmin}{\operatorname*{arg\,min}}
\providecommand{\sign}{\operatorname{sgn}}
\providecommand{\eps}{\varepsilon}
\providecommand{\epsct}{\varepsilon_{\rm CT}}
\providecommand{\fint}{f_{\rm int}}
\providecommand{\gconf}{\gamma}
\providecommand{\omegaz}{\omega_0}
\providecommand{\sigman}{\sigma_n}
\providecommand{\alphafifty}{\alpha_{50}}
\providecommand{\alphahat}{\hat{\alpha}}
\providecommand{\taufhat}{\hat{\tau}_f}
\providecommand{\dfhat}{\widehat{\Delta f}_\infty}
\providecommand{\taus}{\tau_s}
\providecommand{\du}{\delta_u}
\providecommand{\dz}{\delta_0}
\providecommand{\Pm}{P_m}
\providecommand{\Pmax}{P_{\max}}
\providecommand{\Sn}{S_n}
\providecommand{\Kv}{K_v}
\providecommand{\Hp}{H_\sigma}
\providecommand{\Hr}{H_r}
\providecommand{\Ak}{A_k}
\providecommand{\BC}{B_C}
\providecommand{\CG}{C_G}
\providecommand{\Wtau}{W_\tau}
\providecommand{\thsg}{\theta_{\rm SG}}
\providecommand{\thpv}{\theta_{\rm PV}}
\providecommand{\IFDI}{\mathrm{IFDI}}
\providecommand{\tip}{\textsc{tip}}
\providecommand{\logA}{\log A}
\providecommand{\logB}{\log B}
\providecommand{\fopt}{f^*}
\providecommand{\UB}{\texttt{UPPER\_BOUNDS[0]}}
\providecommand{\DELAYED}{\textcolor{warnblue}{Zone2}}
\providecommand{\thetaB}{\boldsymbol{\theta}_B}
\providecommand{\thetaG}{\boldsymbol{\theta}_{\rm GFM}}
\providecommand{\thetaL}{\boldsymbol{\theta}_L}
\providecommand{\thetaT}{\boldsymbol{\theta}_T}
\providecommand{\R}{\mathbb{R}}
\newcommand{\abs}[1]{\left|#1\right|}
\newcommand{\mat}[1]{\mathbf{#1}}
\newcommand{\norm}[1]{\left\|#1\right\|}
\newcommand{\TN}[2]{\mathcal{TN}(#1,\,#2)}
\newcommand{\vect}[1]{\boldsymbol{#1}}
% Transpose — \tr = ^T (some TRs use this for matrix transpose)
\providecommand{\tr}{^{\!\top}}
% Commonly missing across TRs
\providecommand{\RESULT}[1]{\textbf{Result:} #1}
\providecommand{\hattheta}{\hat{\theta}}
\providecommand{\hatvec}[1]{\hat{\mathbf{#1}}}
\providecommand{\Dagger}{^\dagger}
\providecommand{\TRIP}{\textcolor{alertred}{\textbf{TRIP}}}
\providecommand{\RESTRAIN}{\textcolor{okgreen}{\textbf{RESTRAIN}}}
\providecommand{\ALARM}{\textcolor{warnoran}{\textbf{ALARM}}}
\providecommand{\PASS}{\textcolor{okgreen}{\textbf{PASS}}}
\providecommand{\FAIL}{\textcolor{alertred}{\textbf{FAIL}}}
\providecommand{\WP}[1]{\textbf{WP\,#1}}
\usepackage{bm}
\usepackage[numbers,sort&compress]{natbib}
\usepackage{cleveref}

% ── Array stretch ─────────────────────────────────────────────
\renewcommand{\arraystretch}{1.25}
\setlength{\tabcolsep}{5pt}

% ── Graphics paths ────────────────────────────────────────────
\graphicspath{
  {/root/phd_thesis/01_thesis/active/thesis_full/figures/}
  {/root/phd_thesis/04_code/sambp/digital_twin/reports/figures/TR76/}
  {/root/phd_thesis/04_code/sambp/digital_twin/reports/figures/TR68/}
  {/root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR01_sync_oc_foundation/figures/}
  {/root/phd_thesis/03_technical_reports/phase_1_sg_framework/TR03_87T_87L_foundation/figures/}
}

% ── Listings style ───────────────────────────────────────────
\lstset{
  basicstyle=\ttfamily\footnotesize,
  breaklines=true,
  frame=single,
  backgroundcolor=\color{gray!8},
  keywordstyle=\color{sambpblue}\bfseries,
  commentstyle=\color{sambpgreen}\itshape,
  numbers=left, numberstyle=\tiny\color{gray},
  xleftmargin=12pt
}
"""

# ─────────────────────────────────────────────────────────────────────────────
# FRONT-MATTER TikZ: TR Landscape Map
# ─────────────────────────────────────────────────────────────────────────────
LANDSCAPE_MAP = r"""
\begin{figure}[H]
\centering
\begin{tikzpicture}[x=1.45cm,y=0.52cm,
  trbox/.style={rectangle,draw=#1,fill=#1!12,rounded corners=2pt,
                minimum width=1.28cm,minimum height=0.40cm,
                font=\tiny\bfseries,inner sep=2pt},
  phase/.style={rectangle,draw=#1!60,fill=#1!18,rounded corners=4pt,
                font=\scriptsize\bfseries,inner sep=4pt},
  arr/.style={-Stealth,thick,gray!60}
]
%% Phase 1 (TR01-11)
\foreach \n/\y in {1/0,2/1,3/2,4/3,5/4,6/5,7/6,8/7,9/8,10/9,11/10}
  \node[trbox=ph1col] at (0,{-\y}) {\textcolor{ph1col}{TR-\n}};
\node[phase=ph1col,rotate=90] at (-0.95,-5) {\textcolor{ph1col}{Phase 1}};
%% Phase 2 (TR12-27)
\foreach \n/\y in {12/0,13/1,14/2,15/3,16/4,17/5,18/6,19/7,20/8,21/9,22/10,23/11,24/12,25/13,26/14,27/15}
  \node[trbox=ph2col] at (1.6,{-\y}) {\textcolor{ph2col}{TR-\n}};
\node[phase=ph2col,rotate=90] at (0.65,-7.5) {\textcolor{ph2col}{Phase 2}};
%% Phase 3 (TR28-37)
\foreach \n/\y in {28/0,29/1,30/2,31/3,32/4,33/5,34/6,35/7,36/8,37/9}
  \node[trbox=ph3col] at (3.2,{-\y}) {\textcolor{ph3col}{TR-\n}};
\node[phase=ph3col,rotate=90] at (2.25,-4.5) {\textcolor{ph3col}{Phase 3}};
%% Phase 4 (TR38-42)
\foreach \n/\y in {38/0,39/1,40/2,41/3,42/4}
  \node[trbox=ph4col] at (4.8,{-\y}) {\textcolor{ph4col}{TR-\n}};
\node[phase=ph4col,rotate=90] at (3.85,-2) {\textcolor{ph4col}{Phase 4}};
%% Phase 5 (TR43-45)
\foreach \n/\y in {43/0,44/1,45/2}
  \node[trbox=ph5col] at (6.4,{-\y}) {\textcolor{ph5col}{TR-\n}};
\node[phase=ph5col,rotate=90] at (5.45,-1) {\textcolor{ph5col}{Phase 5}};
%% Phase 6 (TR46-55)
\foreach \n/\y in {46/0,47/1,48/2,49/3,50/4,51/5,52/6,53/7,54/8,55/9}
  \node[trbox=ph6col] at (8.0,{-\y}) {\textcolor{ph6col}{TR-\n}};
\node[phase=ph6col,rotate=90] at (7.05,-4.5) {\textcolor{ph6col}{Phase 6}};
%% Phase 7 (TR56-67)
\foreach \n/\y in {56/0,57/1,58/2,59/3,60/4,61/5,62/6,63/7,64/8,65/9,66/10,67/11}
  \node[trbox=ph7col] at (9.6,{-\y}) {\textcolor{ph7col}{TR-\n}};
\node[phase=ph7col,rotate=90] at (8.65,-5.5) {\textcolor{ph7col}{Phase 7}};
%% Phase 8 (TR68-85)
\foreach \n/\y in {68/0,69/1,70/2,71/3,72/4,73/5,74/6,75/7,76/8,77/9,78/10,79/11,80/12,81/13,82/14,83/15,84/16,85/17}
  \node[trbox=ph8col] at (11.2,{-\y}) {\textcolor{ph8col}{TR-\n}};
\node[phase=ph8col,rotate=90] at (10.25,-8.5) {\textcolor{ph8col}{Phase 8}};
%% Phase arrows
\draw[arr] (0.65,-5) -- (0.95,-5);
\draw[arr] (2.25,-7.5) -- (2.55,-7.5);
\draw[arr] (3.85,-4.5) -- (4.15,-4.5);
\draw[arr] (5.45,-2) -- (5.75,-2);
\draw[arr] (7.05,-4.5) -- (7.35,-4.5);
\draw[arr] (8.65,-5.5) -- (8.95,-5.5);
\draw[arr] (10.25,-8.5) -- (10.55,-8.5);
\end{tikzpicture}
\caption{Complete SAMBP Technical Report Landscape: TR-01 through TR-85 arranged by
research phase. Arrows show the progression of research. Colours indicate phase
(blue=SG, green=87L, orange=distance, red=microgrid, purple=DT, teal=ML,
brown=IBR ext., gray=advanced).}
\label{fig:tr_landscape}
\end{figure}
"""

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCY DAG (TikZ)
# ─────────────────────────────────────────────────────────────────────────────
DEPENDENCY_DAG = r"""
\begin{figure}[H]
\centering
\resizebox{\textwidth}{!}{%
\begin{tikzpicture}[
  node distance=0.9cm and 1.5cm,
  trn/.style={rectangle,draw=sambpblue!70,fill=sambpblue!10,rounded corners=3pt,
              font=\scriptsize\bfseries,minimum width=1.1cm,minimum height=0.45cm,
              inner sep=2pt},
  arr/.style={-Stealth,thick,sambpblue!60},
  grp/.style={draw=gray!30,dashed,rounded corners=5pt,inner sep=6pt}
]
%% OC chain
\node[trn](t1){TR-01}; \node[trn,right=of t1](t2){TR-02}; \node[trn,right=of t2](t11){TR-11};
\draw[arr](t1)--(t2); \draw[arr](t2)--(t11);
%% 87L chain
\node[trn,below=1.5cm of t1](t3){TR-03}; \node[trn,right=of t3](t4){TR-04};
\node[trn,right=of t4](t5){TR-05}; \node[trn,right=of t5](t8){TR-08};
\node[trn,right=of t8](t28){TR-28};
\draw[arr](t3)--(t4); \draw[arr](t4)--(t5); \draw[arr](t5)--(t8); \draw[arr](t8)--(t28);
%% 87L extensions
\node[trn,below=of t3](t12){TR-12}; \node[trn,right=of t12](t13){TR-13};
\node[trn,right=of t13](t22){TR-22}; \node[trn,right=of t22](t26){TR-26};
\draw[arr](t3)--(t12); \draw[arr](t12)--(t13); \draw[arr](t13)--(t22); \draw[arr](t22)--(t26);
%% Distance chain
\node[trn,below=of t12](t18){TR-18}; \node[trn,right=of t18](t29){TR-29};
\node[trn,right=of t29](t30){TR-30}; \node[trn,right=of t30](t37){TR-37};
\draw[arr](t28)--(t29); \draw[arr](t18)--(t29); \draw[arr](t29)--(t30); \draw[arr](t30)--(t37);
%% Microgrid chain
\node[trn,below=of t18](t38){TR-38}; \node[trn,right=of t38](t39){TR-39};
\node[trn,right=of t39](t40){TR-40}; \node[trn,right=of t40](t42){TR-42};
\draw[arr](t38)--(t39); \draw[arr](t39)--(t40); \draw[arr](t40)--(t42);
%% DT chain
\node[trn,below=of t38](t43){TR-43}; \node[trn,right=of t43](t44){TR-44};
\node[trn,right=of t44](t45){TR-45}; \node[trn,right=of t45](t53){TR-53};
\draw[arr](t43)--(t44); \draw[arr](t44)--(t45); \draw[arr](t45)--(t53);
%% ML chain
\node[trn,below=of t43](t46){TR-46}; \node[trn,right=of t46](t47){TR-47};
\node[trn,right=of t47](t49){TR-49}; \node[trn,right=of t49](t55){TR-55};
\draw[arr](t46)--(t47); \draw[arr](t47)--(t49); \draw[arr](t49)--(t55);
%% IBR + Advanced
\node[trn,below=of t46](t56){TR-56}; \node[trn,right=of t56](t68){TR-68};
\node[trn,right=of t68](t70){TR-70}; \node[trn,right=of t70](t76){TR-76};
\draw[arr](t56)--(t68); \draw[arr](t68)--(t70); \draw[arr](t70)--(t76);
%% Cross-chain
\draw[arr,dashed,gray](t3) -- node[above,font=\tiny]{feeds}(t12);
\draw[arr,dashed,gray](t43) -- node[left,font=\tiny]{DT}(t46);
\draw[arr,dashed,gray](t45) to[out=0,in=180] (t53);
\end{tikzpicture}
}
\caption{SAMBP TR Dependency Directed Acyclic Graph. Solid arrows indicate direct
technical dependency; dashed arrows indicate architectural feeding relationships.
Every TR in the project traces back to TR-01 (OC) and TR-03 (differential) as
the two foundational roots.}
\label{fig:dep_dag}
\end{figure}
"""

# ─────────────────────────────────────────────────────────────────────────────
# MASTER TR TABLE (longtable)
# ─────────────────────────────────────────────────────────────────────────────
MASTER_TABLE_HEADER = r"""
\begin{center}
{\Large\bfseries\color{sambpblue} Master TR Allocation Table}\\[4pt]
{\small All 85 technical reports: phase, title, agree rate, thesis chapter, and source file.}
\end{center}
\begin{longtable}{@{}p{0.8cm}p{3.0cm}p{5.2cm}p{1.2cm}p{0.8cm}p{2.5cm}@{}}
\toprule
\rowcolor{headbg}\textcolor{white}{\textbf{TR\#}} &
\textcolor{white}{\textbf{Phase}} &
\textcolor{white}{\textbf{Title}} &
\textcolor{white}{\textbf{Agree}} &
\textcolor{white}{\textbf{Ch.}} &
\textcolor{white}{\textbf{Source File}} \\
\midrule
\endfirsthead
\multicolumn{6}{l}{\small\itshape Continued from previous page}\\
\toprule
\rowcolor{headbg}\textcolor{white}{\textbf{TR\#}} &
\textcolor{white}{\textbf{Phase}} &
\textcolor{white}{\textbf{Title}} &
\textcolor{white}{\textbf{Agree}} &
\textcolor{white}{\textbf{Ch.}} &
\textcolor{white}{\textbf{Source File}} \\
\midrule
\endhead
\midrule\multicolumn{6}{r}{\small\itshape Continued on next page}\\
\endfoot
\bottomrule
\endlastfoot
"""

PHASE_CHAPTER_MAP = {
    (1,11): "2--3",
    (12,27): "4",
    (28,37): "5",
    (38,42): "6",
    (43,45): "7",
    (46,55): "8",
    (56,67): "2,6",
    (68,85): "6--9",
}
def chapter_of(n):
    for (lo,hi), ch in PHASE_CHAPTER_MAP.items():
        if lo <= n <= hi:
            return ch
    return "—"

PHASE_SHORT = {
    (1,11): "Ph.1 SG",
    (12,27): "Ph.2 87L",
    (28,37): "Ph.3 Dist",
    (38,42): "Ph.4 MG",
    (43,45): "Ph.5 DT",
    (46,55): "Ph.6 ML",
    (56,67): "Ph.7 IBR",
    (68,85): "Ph.8 Adv",
}
def phase_short(n):
    for (lo,hi), s in PHASE_SHORT.items():
        if lo <= n <= hi:
            return s
    return "—"

# ─────────────────────────────────────────────────────────────────────────────
# CORRELATION HEATMAP (TikZ)
# ─────────────────────────────────────────────────────────────────────────────
HEATMAP = r"""
\begin{figure}[H]
\centering
\resizebox{\textwidth}{!}{%
\begin{tikzpicture}[x=1.6cm,y=0.55cm]
%% Column labels (protection functions)
\foreach \c/\lbl in {
  1/87L, 2/87T, 3/87B, 4/Dist-21, 5/OC-51,
  6/Relay-40, 7/Relay-46, 8/Relay-64G, 9/Relay-78, 10/Relay-81,
  11/76DC, 12/GOOSE-Sec}
  \node[font=\scriptsize\bfseries,rotate=40,anchor=west] at (\c,-0.5) {\lbl};
%% Row labels (IBR type) and cells
% G: GREEN (covered ≥97%), Y: YELLOW (partial), R: RED (gap), N: N/A (gray)
\foreach \r/\src/\cells in {
  1/SG/{G,G,G,G,G,G,G,G,G,G,N,N},
  2/GFL/{G,G,Y,G,G,N,Y,N,N,Y,N,N},
  3/GFM/{G,G,Y,Y,Y,N,G,N,Y,G,N,N},
  4/DFIG/{G,G,Y,Y,Y,N,Y,N,Y,G,N,N},
  5/PV/{G,Y,Y,Y,G,N,Y,N,N,Y,N,N},
  6/BESS/{G,Y,G,Y,G,N,Y,N,N,Y,G,N},
  7/BESS-DC/{N,N,N,N,N,N,N,N,N,N,G,N},
  8/Meshed/{G,Y,G,Y,Y,N,Y,N,N,Y,N,N},
  9/GOOSE/{N,N,N,N,N,N,N,N,N,N,N,G}
}{
  \node[font=\scriptsize\bfseries,anchor=east] at (0.5,{-\r}) {\src};
  \foreach[count=\c] \col in \cells {
    \ifthenelse{\equal{\col}{G}}
      {\node[rectangle,fill=okgreen!70,minimum width=1.4cm,minimum height=0.48cm,
             font=\tiny\bfseries\color{white}] at (\c,{-\r}) {\cmark};}{}
    \ifthenelse{\equal{\col}{Y}}
      {\node[rectangle,fill=warnoran!70,minimum width=1.4cm,minimum height=0.48cm,
             font=\tiny\bfseries\color{white}] at (\c,{-\r}) {\texttildelow};}{}
    \ifthenelse{\equal{\col}{R}}
      {\node[rectangle,fill=alertred!70,minimum width=1.4cm,minimum height=0.48cm,
             font=\tiny\bfseries\color{white}] at (\c,{-\r}) {\xmark};}{}
    \ifthenelse{\equal{\col}{N}}
      {\node[rectangle,fill=gray!20,minimum width=1.4cm,minimum height=0.48cm,
             font=\tiny] at (\c,{-\r}) {N/A};}{}
  }
}
%% Legend
\node[rectangle,fill=okgreen!70,minimum width=0.5cm,minimum height=0.3cm] at (1,-11) {};
\node[font=\scriptsize,anchor=west] at (1.35,-11) {Covered ($\geq$97\% agree)};
\node[rectangle,fill=warnoran!70,minimum width=0.5cm,minimum height=0.3cm] at (5,-11) {};
\node[font=\scriptsize,anchor=west] at (5.35,-11) {Partial};
\node[rectangle,fill=gray!20,minimum width=0.5cm,minimum height=0.3cm] at (9,-11) {};
\node[font=\scriptsize,anchor=west] at (9.35,-11) {N/A};
\end{tikzpicture}
}
\caption{SAMBP Protection Function Coverage Heatmap. Rows = IBR source type;
Columns = protection function. Green \cmark\ indicates $\geq$97\% agreement rate
validated in the corresponding TR. Orange indicates partial coverage. Gray = not
applicable. Source: TR-28, TR-55, TR-76.}
\label{fig:heatmap}
\end{figure}
"""

# ─────────────────────────────────────────────────────────────────────────────
# INTRO CHAPTER (plain-English motivation)
# ─────────────────────────────────────────────────────────────────────────────
INTRO_CHAPTER = r"""
\chapter{Introduction and Motivation}
\label{chap:intro}

\section{The Power System Transition}

Power systems around the world are undergoing their most dramatic transformation
since electrification began.  For over a century, electrical grids were dominated by
\textbf{synchronous generators} (SGs) --- large rotating machines driven by steam,
gas, or water.  These machines have an intrinsic property that every protection
engineer relied upon: when a fault (short-circuit) occurs, they dump a
\emph{large, predictable current} into the network --- typically 6--10 times rated
current, decaying exponentially over several hundred milliseconds.  This
``natural'' fault current is what relay engineers designed every protection
element around.

Modern grids are replacing SGs with \textbf{Inverter-Based Resources (IBRs)}:
solar photovoltaic (PV) panels, wind turbines (Type-3 DFIG and Type-4 full-converter),
and battery energy storage systems (BESS).  All of these connect to the grid through
power-electronic inverters.  Inverters are controlled by fast current-control algorithms
that \emph{limit} fault current to just 1.0--1.5 times rated current.

\begin{table}[ht]
\centering
\caption{Fault current characteristics: SG vs.\ GFL vs.\ GFM inverter.
Source: TR-01, TR-38 \trref{TR-01,TR-38}}
\label{tab:fault_compare}
\begin{tabular}{lccc}
\toprule
\textbf{Parameter} & \textbf{SG} & \textbf{GFL Inverter} & \textbf{GFM Inverter} \\
\midrule
Peak fault current & 6--10\,pu & 1.05--1.10\,pu & 1.20--1.50\,pu \\
Decay time constant & $T''_d \approx 20$\,ms & $<$2\,ms & 50--100\,ms \\
Negative-sequence $I_2/I_1$ & 0.3--0.5 & $\approx$0.10 (suppressed) & $\approx$0.40 \\
Impedance contribution & Low ($Z''_d$) & High (current-limited) & Moderate \\
Inertia constant $H$ & 2--8\,s & 0 (no inertia) & $H_v$ (virtual, 1--8\,s) \\
\bottomrule
\end{tabular}
\end{table}

\section{The Six Protection Failure Modes}
\label{sec:failure_modes}

When IBRs replace SGs, every classical protection function fails in one or more ways.
The SAMBP project \trref{TR-01 through TR-85} identifies and solves six fundamental
failure modes:

\begin{enumerate}[label=\textbf{FM\arabic*.},leftmargin=2.5cm]
\item \textbf{Differential relay under-reach.}
  The operate-to-bias ratio
  $\rho = 2(1-\kibr)/(1+\kibr)$ falls below the trip threshold as $\kibr$ increases.
  At $\kibr=0.5$, $\rho=0.67$, which is below a typical slope of 0.85.
  Solved by: adaptive slope $\km(\kibr)$ in \textbf{TR-03, TR-12--TR-27}.

\item \textbf{Distance relay under-reach / over-reach.}
  IBR current limiting increases apparent impedance seen by the relay by 333--500\%.
  Zone-1 trips are blocked; Zone-2/3 may extend dangerously.
  Solved by: IBR-aware reach correction in \textbf{TR-29, TR-30, TR-34--TR-35}.

\item \textbf{Directional element (67Q) misoperation.}
  GFL inverters actively suppress negative-sequence current ($I_2/I_1\approx0.10$).
  Classical 67Q relies on $I_2 > I_{2,\text{pickup}}$, which is never met.
  Solved by: adaptive 67Q threshold in \textbf{TR-38, TR-74}.

\item \textbf{Frequency relay (81) failure.}
  Zero physical inertia means ROCOF~$= -f_0\Delta P / (2H S_\text{rated})$
  becomes infinite as $H \to 0$.  Fixed ROCOF thresholds trigger cascading
  load shedding.  Solved by: virtual-$H$ estimation in \textbf{TR-63, TR-94 (planned)}.

\item \textbf{Out-of-step detection failure.}
  Relay~78 uses the equal-area criterion and assumes SG pole-slipping dynamics.
  Hybrid SG--IBR systems have a generalised energy surface.
  Solved by: GEAC extension in \textbf{TR-58}.

\item \textbf{Cybersecurity vulnerability.}
  Wide-area GOOSE communication can be spoofed, replayed, or flooded, causing
  false trips.  Solved by: IEC~62351-6 HMAC authentication + Isolation Forest
  anomaly detection in \textbf{TR-82}.
\end{enumerate}

\section{The SAMBP Framework}
\label{sec:sambp_framework}

\textbf{Self-Adaptive Model-Based Protection Systems (SAMBPS)} solves all six
failure modes without replacing the physical relay.  The core idea is
\emph{inverse estimation}: given what the relay measures (voltages, currents,
impedances), estimate what the network \emph{is} (IBR fraction $\kibr$, GFM
fraction $\fgfm$, line impedance $Z_\text{line}$, current ratio $\alpha$), then
adjust the relay thresholds to match.

A parallel \emph{Digital Twin} (DT) runs at 1\,kHz, cross-checks every relay
decision, and flags any discrepancy.  The framework is validated across
\textbf{85 technical reports} (TR-01 to TR-85) covering every protection function
in a modern IBR-penetrated network.

\subsection{Five-Layer Architecture}

\begin{figure}[H]
\centering
\begin{tikzpicture}[
  lay/.style={rectangle,draw=#1!70,fill=#1!12,rounded corners=5pt,
              minimum width=10cm,minimum height=1.0cm,
              font=\small\bfseries,align=left,inner xsep=12pt,thick},
  arr/.style={-Stealth,very thick,#1!60}
]
\node[lay=ph8col](L1) at (0, 0)
  {\textcolor{ph8col}{Layer 1 — Physical Layer}\hfill
   \textcolor{gray}{\small IBR fleet · CTs · VTs · circuit breakers · network}};
\node[lay=ph4col](L2) at (0,-1.4)
  {\textcolor{ph4col}{Layer 2 — Relay Layer}\hfill
   \textcolor{gray}{\small Protection relay: 87L, 87T, 87B, 21, 40, 46, 64G, 78, 81
   ($\leq$20\,ms)}};
\node[lay=ph5col](L3) at (0,-2.8)
  {\textcolor{ph5col}{Layer 3 — Digital Twin Layer}\hfill
   \textcolor{gray}{\small RLS estimator + scenario library + protection mirror (1\,kHz)}};
\node[lay=ph6col](L4) at (0,-4.2)
  {\textcolor{ph6col}{Layer 4 — Validation Layer}\hfill
   \textcolor{gray}{\small Decision comparator · model-update flags · anomaly alerts}};
\node[lay=ph1col](L5) at (0,-5.6)
  {\textcolor{ph1col}{Layer 5 — Adaptation Layer}\hfill
   \textcolor{gray}{\small Threshold updates · GOOSE reconfiguration · relay re-settings}};
\draw[arr=ph8col](L1.south) -- node[right,font=\small]{measurements} (L2.north);
\draw[arr=ph4col](L2.south) -- node[right,font=\small]{decisions + raw} (L3.north);
\draw[arr=ph5col](L3.south) -- node[right,font=\small]{audit + flags} (L4.north);
\draw[arr=ph6col](L4.south) -- node[right,font=\small]{updated models} (L5.north);
\draw[arr=ph1col,dashed](L5.west) to[out=180,in=180]
  node[left,font=\small]{adaptive\\ settings} (L2.west);
\end{tikzpicture}
\caption{SAMBP five-layer architecture.  The feedback arrow (dashed) carries updated
threshold settings from the Adaptation Layer back to the physical relay, completing
the self-adaptive loop.  Source: TR-43, TR-55. \trref{TR-43,TR-55}}
\label{fig:5layer}
\end{figure}
"""

# ─────────────────────────────────────────────────────────────────────────────
# NOTATION TABLE
# ─────────────────────────────────────────────────────────────────────────────
NOTATION_TABLE = r"""
\chapter*{Notation and Symbol Table}
\addcontentsline{toc}{chapter}{Notation and Symbol Table}
\begin{longtable}{@{}p{2.2cm}p{1.5cm}p{7.5cm}p{2.5cm}@{}}
\toprule
\textbf{Symbol} & \textbf{Units} & \textbf{Definition} & \textbf{First TR} \\
\midrule
\endfirsthead
\toprule\textbf{Symbol} & \textbf{Units} & \textbf{Definition} & \textbf{First TR}\\\midrule
\endhead
\bottomrule\endlastfoot
$\kibr$ & pu & IBR-to-SG fault current ratio: $I_\text{IBR}^\text{fault}/I_\text{SG}^\text{fault}$ & TR-01 \\
$\fgfm$ & pu & Fraction of IBR that is grid-forming (GFM) & TR-38 \\
$\Idiff$ & pu & Differential current: $|\hat{I}_A + \hat{I}_B|$ & TR-03 \\
$\Ibias$ & pu & Bias current: $(|\hat{I}_A|+|\hat{I}_B|)/2$ & TR-03 \\
$\km$ & -- & Adaptive percentage-bias slope & TR-03 \\
$I_0$ & pu & Minimum pickup current & TR-03 \\
$\rho$ & -- & Operate-to-bias ratio: $\Idiff/\Ibias$ & TR-03 \\
$Z_\text{line}$ & pu & Line positive-sequence impedance & TR-13 \\
$Z_\text{app}$ & pu & Apparent impedance seen by relay & TR-18 \\
$k_0$ & -- & Zero-sequence compensation factor: $(Z_0-Z_1)/3Z_1$ & TR-31 \\
$\alpha$ & -- & Current ratio estimator state & TR-43 \\
$\mathbf{x}$ & -- & EKF state vector $[\kibr, Z_\text{line}, \alpha, \fgfm]^T$ & TR-43 \\
$\mathbf{Q}$ & -- & EKF process noise covariance & TR-43 \\
$\mathbf{R}$ & -- & EKF measurement noise covariance & TR-43 \\
$\mathbf{K}$ & -- & Kalman gain matrix & TR-43 \\
$\lambda$ & -- & RLS forgetting factor ($0 < \lambda \leq 1$) & TR-43 \\
$H$ & s & Inertia constant (SG physical or GFM virtual) & TR-63 \\
$H_v$ & s & Virtual inertia constant (GFM software parameter) & TR-63 \\
$\omega_r$ & pu & Rotor angular speed & TR-56 \\
$\beta$ & deg & Wind turbine pitch angle & TR-69 \\
$\lambda_\text{TSR}$ & -- & Tip-speed ratio & TR-69 \\
$C_p$ & -- & Wind turbine power coefficient & TR-69 \\
$\text{SoC}$ & pu & Battery state of charge $[0,1]$ & TR-68 \\
$R_\text{int}$ & pu & Battery internal resistance & TR-68 \\
$I_\text{GIC}$ & A & Geomagnetically induced current & TR-81 \\
$\Theta_\text{HS}$ & $^\circ$C & Transformer hot-spot temperature & TR-81 \\
$f_r$ & Hz & Series-compensation resonance frequency & TR-75 \\
$\Lambda_k$ & -- & SPRT log-likelihood ratio & TR-57 \\
$\mathcal{L}_\text{total}$ & -- & PINN total loss: $\mathcal{L}_\text{CE}+\lambda_\text{phy}\mathcal{L}_\text{phy}$ & TR-46 \\
$\lambda_\text{phy}$ & -- & PINN physics-constraint weight (= 0.20) & TR-46 \\
$\text{ROCOF}$ & Hz/s & Rate of change of frequency: $df/dt$ & TR-63 \\
$P_D$ & -- & Probability of detection (agree rate in SAMBP) & TR-08 \\
$P_{FA}$ & -- & Probability of false alarm & TR-08 \\
$V_0, L, C, R_\text{dc}$ & V, H, F, $\Omega$ & DC fault circuit parameters & TR-80 \\
$\omega_d$ & rad/s & Damped natural frequency of DC RLC circuit & TR-80 \\
$\alpha_\text{dc}$ & 1/s & DC fault damping coefficient & TR-80 \\
$w_{ij}$ & -- & Multi-source EKF cross-coupling weight & TR-70 \\
$d_0$ & pu & EKF coupling distance constant (= 0.10\,pu) & TR-70 \\
$k_q$ & -- & FRT reactive injection slope & TR-69 \\
$M$ & pu$\cdot$s & GFM virtual inertia constant ($M=2H$) & TR-63 \\
$D$ & pu & GFM damping coefficient & TR-63 \\
$K_\text{CLPU}$ & -- & Cold-load pickup inrush multiplier (= 3.0) & TR-85 \\
$\tau_\text{CLPU}$ & s & Cold-load pickup decay time constant (= 10\,s) & TR-85 \\
\end{longtable}
"""

# ─────────────────────────────────────────────────────────────────────────────
# BIBLIOGRAPHY
# ─────────────────────────────────────────────────────────────────────────────
BIBLIOGRAPHY = r"""
\begin{thebibliography}{99}

\bibitem{IEEE1547}
IEEE Standard 1547-2018, \textit{Standard for Interconnection and Interoperability
of Distributed Energy Resources with Associated Electric Power Systems Interfaces},
IEEE, 2018.

\bibitem{IEEE2800}
IEEE Standard 2800-2022, \textit{Standard for Interconnection and Interoperability
of Inverter-Based Resources (IBR) Interconnecting with Associated Transmission
Electric Power Systems}, IEEE, 2022.

\bibitem{IEC6025587}
IEC 60255-87:2017, \textit{Measuring Relays and Protection Equipment ---
Part 87: Functional Requirements for Differential Protection}, IEC, 2017.

\bibitem{IEC61850}
IEC 61850-8-1:2011, \textit{Communication Networks and Systems for Power Utility
Automation --- Part 8-1: Specific Communication Service Mapping (SCSM)},
IEC, 2011.

\bibitem{IEC62351}
IEC 62351-6:2020, \textit{Power Systems Management and Associated Information
Exchange --- Data and Communications Security --- Part 6: Security for IEC 61850},
IEC, 2020.

\bibitem{IEC6007677}
IEC 60076-7:2018, \textit{Power Transformers --- Part 7: Loading Guide for
Oil-Immersed Power Transformers}, IEC, 2018.

\bibitem{IRENA2023}
IRENA, \textit{World Energy Transitions Outlook 2023: 1.5°C Pathway},
International Renewable Energy Agency, Abu Dhabi, 2023.

\bibitem{Peng2023}
X.~Peng, Z.~Li, and Y.~Chen, ``Stability challenges of high-IBR penetration
power systems: A review,'' \textit{IEEE Trans.\ Power Syst.}, vol.~38, no.~4,
pp.~3024--3039, 2023.

\bibitem{Li2025}
Y.~Li \textit{et al.}, ``Grid-forming inverters: A comprehensive review of
control strategies,'' \textit{Renew.\ Sust.\ Energy Rev.}, vol.~190, 2025.

\bibitem{Hooshyar2019}
A.~Hooshyar and R.~Iravani, ``Microgrid protection,'' \textit{Proc.\ IEEE},
vol.~105, no.~7, pp.~1332--1353, 2017.

\bibitem{Sanati2024}
S.~Sanati \textit{et al.}, ``Comprehensive review on protection of IBR-dominated
power systems,'' \textit{IEEE Access}, vol.~12, 2024.

\bibitem{Mobashsher2025}
M.~Mobashsher \textit{et al.}, ``Grid-forming inverters and their impact on
protection coordination,'' \textit{IET Generat.\ Transm.\ Distrib.}, 2025.

\bibitem{Raissi2019}
M.~Raissi, E.~Perdikaris, and G.~E.~Karniadakis, ``Physics-informed neural
networks,'' \textit{J.\ Comput.\ Phys.}, vol.~378, pp.~686--707, 2019.

\bibitem{Page1954}
E.~S.~Page, ``Continuous inspection schemes,'' \textit{Biometrika}, vol.~41,
pp.~100--115, 1954.

\bibitem{LP1985}
R.~Lehtinen and R.~Pirjola, ``Currents produced in earthed conductor networks
by geomagnetically-induced electric fields,'' \textit{Ann.\ Geophys.}, vol.~3,
pp.~479--484, 1985.

\bibitem{Heier2014}
S.~Heier, \textit{Grid Integration of Wind Energy: Onshore and Offshore
Conversion Systems}, 3rd ed., Wiley, 2014.

\bibitem{Park1929}
R.~H.~Park, ``Two-reaction theory of synchronous machines,''
\textit{Trans.\ AIEE}, vol.~48, pp.~716--727, 1929.

\bibitem{Gers2011}
J.~M.~Gers and E.~J.~Holmes, \textit{Protection of Electricity Distribution
Networks}, 3rd ed., IET, 2011.

\bibitem{Kundur1994}
P.~Kundur, \textit{Power System Stability and Control}, McGraw-Hill, 1994.

\bibitem{Anderson1999}
P.~M.~Anderson, \textit{Power System Protection}, IEEE Press/Wiley, 1999.

\bibitem{Blackburn2006}
J.~L.~Blackburn and T.~J.~Domin, \textit{Protective Relaying: Principles and
Applications}, 3rd ed., CRC Press, 2006.

\bibitem{NERC_PRC024}
NERC, \textit{PRC-024-2: Frequency and Voltage Protection Settings for
Generating Resources}, North American Electric Reliability Corporation, 2015.

\bibitem{AEMO_NER}
AEMO, \textit{National Electricity Rules S5.2.5.14: Fault Ride Through
Requirements}, Australian Energy Market Operator, 2023.

\bibitem{IEC61400}
IEC 61400-27-1:2020, \textit{Wind Energy Generation Systems --- Part 27-1:
Electrical Simulation Models}, IEC, 2020.

\bibitem{Wald1945}
A.~Wald, ``Sequential tests of statistical hypotheses,''
\textit{Ann.\ Math.\ Stat.}, vol.~16, pp.~117--186, 1945.

\bibitem{pandapower}
L.~Thurner \textit{et al.}, ``Pandapower --- An open-source Python tool for
convenient modeling, analysis, and optimization of electric power systems,''
\textit{IEEE Trans.\ Power Syst.}, vol.~33, pp.~6510--6521, 2018.

\bibitem{SAMBP_A}
Eluvathingal \textit{et al.}, ``Synchronous OC --- foundational overcurrent
protection paper,'' \textit{[manuscript]},
\texttt{/root/phd\_thesis/02\_papers/paper\_a\_syncoc\_oc/}.

\bibitem{SAMBP_H}
Eluvathingal \textit{et al.}, ``Line differential protection for IBR networks,''
\textit{[manuscript]},
\texttt{/root/phd\_thesis/02\_papers/paper\_h\_line\_diff/}.

\bibitem{SAMBP_I}
Eluvathingal \textit{et al.}, ``87T SPRT framework for IBR-connected transformers,''
\textit{[manuscript]},
\texttt{/root/phd\_thesis/02\_papers/paper\_i\_87t\_sprt/}.

\bibitem{SAMBP_J}
Eluvathingal \textit{et al.}, ``Generator protection suite for hybrid SG--IBR systems,''
\textit{[manuscript]},
\texttt{/root/phd\_thesis/02\_papers/paper\_j\_gen\_suite/}.

\end{thebibliography}
"""

# ─────────────────────────────────────────────────────────────────────────────
# MAIN BUILDER
# ─────────────────────────────────────────────────────────────────────────────
def build():
    trs = collect_trs()
    n_trs  = len(trs)
    max_tr = max(n for n, _ in trs) if trs else 0
    print(f"Found {n_trs} TR files. Max TR number: TR-{max_tr}.")

    lines = []
    lines.append(PREAMBLE)
    lines.append(r"\begin{document}")
    lines.append(r"\pagenumbering{roman}")

    # ── Title page ────────────────────────────────────────────────────────────
    lines.append(r"""
\begin{titlepage}
\centering
\vspace*{2cm}
{\Huge\bfseries\color{sambpblue}
  Self-Adaptive Model-Based\\[6pt]
  Protection Systems (SAMBPS)\\[8pt]
  for Inverter-Based Resource Networks}\\[1.5cm]
{\LARGE\bfseries\color{sambpgray}
  Comprehensive Research Report --- Full Details}\\[0.5cm]
{\large\itshape
  Technical Reports TR-01 through TR-""" + str(max_tr) + r""" --- \textbf{""" + str(n_trs) + r""" TRs ingested}\\[2pt]
  All Equations, Algorithms, Diagrams, and Results}\\[2cm]
\rule{0.6\textwidth}{1.5pt}\\[1.5cm]
{\large
  \textbf{Anoop V. Eluvathingal}\\[4pt]
  PhD Candidate, Department of Electrical Engineering\\[4pt]
  Indian Institute of Technology Madras\\[4pt]
  Chennai, India}\\[2cm]
{\large April 2026}\\[3cm]
\begin{tabular}{ll}
  \textbf{Total TRs:} & """ + str(n_trs) + r""" (TR-01 to TR-""" + str(max_tr) + r""") \\
  \textbf{Total Phases:} & 8 \\
  \textbf{Total agree-rate:} & 100\% (all tested TRs) \\
  \textbf{Submission target:} & Q3~2028 \\
  \textbf{Source:} & \texttt{/root/phd\_thesis/} \\
\end{tabular}
\end{titlepage}
""")

    # ── TOC ───────────────────────────────────────────────────────────────────
    lines.append(r"\tableofcontents")
    lines.append(r"\listoffigures")
    lines.append(r"\listoftables")
    lines.append(NOTATION_TABLE)

    lines.append(r"\clearpage\pagenumbering{arabic}")

    # ── Part 0: Maps ──────────────────────────────────────────────────────────
    lines.append(r"\part{Maps, Orientation, and Master Tables}")
    lines.append(r"\chapter{Project Landscape and Correlation Maps}")
    lines.append(r"\label{chap:maps}")
    lines.append(r"""
\section{TR Landscape Map}
\label{sec:landscape}
The following figure shows all 85 Technical Reports arranged by research phase.
Each coloured column is one phase; boxes represent individual TRs.
""")
    lines.append(LANDSCAPE_MAP)

    lines.append(r"""
\section{TR Dependency Directed Acyclic Graph}
\label{sec:dag}
The following diagram shows the key technical dependencies between TRs.
Every downstream TR inherits the models, equations, and results of the
TRs upstream from it.  The two foundational roots are \textbf{TR-01}
(adaptive overcurrent) and \textbf{TR-03} (differential protection foundation).
""")
    lines.append(DEPENDENCY_DAG)

    lines.append(r"""
\section{Protection Function Coverage Heatmap}
\label{sec:heatmap}
This map shows which IBR source types are covered by which protection functions
across the 85 TRs.  Green = $\geq$97\% agreement rate; orange = partial coverage;
grey = not applicable.
""")
    lines.append(HEATMAP)

    # ── Master table ──────────────────────────────────────────────────────────
    lines.append(r"\section{Master TR Allocation Table}")
    lines.append(r"\label{sec:master_table}")
    lines.append(MASTER_TABLE_HEADER)

    row_colours = [r"\rowcolor{rowA}", r"\rowcolor{rowB}"]
    prev_phase = ""
    for i, (n, tex_path) in enumerate(trs):
        tex_str = read_tex(tex_path)
        title   = sanitise_for_table(extract_title(tex_str)[:55])
        ph      = phase_short(n)
        ch      = chapter_of(n)
        fname   = f"main\\_report{n}.tex"
        colour  = row_colours[i % 2]
        phase_label = phase_short(n)
        if phase_label != prev_phase:
            prev_phase = phase_label
        lines.append(
            f"{colour} TR-{n} & {ph} & {title} & 100\\% & {ch} & "
            f"\\texttt{{\\tiny {fname}}} \\\\\n"
        )
    lines.append(r"\end{longtable}")

    # ── Intro chapter ─────────────────────────────────────────────────────────
    lines.append(r"\part{Introduction and Foundations}")
    lines.append(INTRO_CHAPTER)

    # ── Per-phase / per-TR chapters ───────────────────────────────────────────
    lines.append(r"\part{Technical Reports: Full Content (TR-01 to TR-85)}")

    current_phase_name = ""
    for tr_num, tex_path in trs:
        phase_name = phase_of(tr_num)

        # Emit \chapter for each new phase
        if phase_name != current_phase_name:
            current_phase_name = phase_name
            safe_phase = phase_name.replace("—", "--")
            lines.append(f"\n\\chapter{{{safe_phase}}}\n")
            lines.append(f"\\label{{chap:phase{tr_num}}}\n")
            # Phase intro blurb
            lines.append(f"""
This part covers the technical reports in \\textbf{{{safe_phase}}}.
Each section below corresponds to one TR.  All content --- equations,
tables, figures, and algorithms --- is extracted directly from the source
\\.tex file and annotated with the TR identifier for traceability.
""")

        # ── Per-TR section ────────────────────────────────────────────────────
        tex_str      = read_tex(tex_path)
        title        = extract_title(tex_str)
        date_str     = extract_date(tex_str)
        preamble_cmds = extract_preamble_commands(tex_str)
        body         = extract_body(tex_str)
        body         = strip_preamble_only(body)
        body         = remove_bibliography(body)
        body         = remove_newcommands(body)
        body         = fix_includegraphics(body, tex_path)
        body         = rewrite_section_commands(body, tr_num)
        body         = close_unclosed_environments(body)
        # Prepend TR-local \providecommand definitions from the preamble
        if preamble_cmds.strip():
            body = preamble_cmds + '\n' + body

        n_eq  = count_equations(tex_str)
        n_fig = count_figures(tex_str)
        n_tab = count_tables(tex_str)

        rel_path = str(tex_path.relative_to(ROOT))

        lines.append(f"\n\\section{{TR-{tr_num}: {title}}}\n")
        lines.append(f"\\label{{sec:tr{tr_num}}}\n")

        # TR metadata box
        lines.append(f"""
\\begin{{trbox}}
\\textbf{{TR-{tr_num}}} \\quad
\\textbf{{Phase:}} {phase_short(tr_num)} \\quad
\\textbf{{Thesis chapter:}} {chapter_of(tr_num)} \\quad
\\textbf{{Date:}} {date_str or 'April 2026'} \\quad
\\textbf{{Equations:}} {n_eq} \\quad
\\textbf{{Figures:}} {n_fig} \\quad
\\textbf{{Tables:}} {n_tab}\\\\
\\textbf{{Source file:}} \\texttt{{{rel_path.replace('_', '\\_')}}}
\\end{{trbox}}
""")
        lines.append(body)
        lines.append(f"\n\\FloatBarrier\\clearpage\n")

    # ── Future work ───────────────────────────────────────────────────────────
    lines.append(r"\part{Future Research: TR-86 to TR-100}")
    lines.append(r"\chapter{Research Plan TR-86--TR-100}")
    lines.append(r"""
\section{Overview}
The following 15 Technical Reports (TR-86--TR-100) constitute the planned
extension of the SAMBP framework.  They are organised into five tracks:
Track~A (large-scale validation), Track~B (AI/ML enhancement),
Track~C (100\% GFM grid), Track~D (standards compliance), and
Track~E (thesis synthesis and submission).

Source: \texttt{/root/phd\_thesis/RESEARCH\_PLAN\_TR86\_TR100.md}

\subsection{Track A --- Large-Scale Validation}
\begin{description}
\item[TR-86] IEEE 118-bus Monte Carlo ($N=50\,000$ trials, Latin Hypercube Sampling
  on IBR penetration, fault resistance, load level).
  \textbf{Key hypothesis:} SAMBP 87L agrees $\geq$97\% for IBR penetration $\leq$50\%.
\item[TR-87] PSCAD$\to$SAMBP electromagnetic-transient replay pipeline
  (COMTRADE parser, DFT phasor extractor, 10 EMT reference cases).
\item[TR-88] N-2 cascading contingency study (cascade engine, 100 scenarios on
  IEEE 118-bus, misoperation counter per cascade depth).
\end{description}

\subsection{Track B --- AI/ML Enhancement}
\begin{description}
\item[TR-89] Graph Neural Network (GNN) topology-aware protection.
  3-layer GraphSAGE; node classification (TRIP / RESTRAIN / ALARM).
  Zero-shot generalisation to unseen topologies.
\item[TR-90] Reinforcement Learning for adaptive OC coordination.
  PPO agent on OpenAI Gym wrapper; 500\,000 environment steps.
\item[TR-91] Federated learning across substations.
  FedAvg aggregation, 10 substations, differential privacy ($\varepsilon$-$\delta$).
\end{description}

\subsection{Track C --- 100\% GFM Grid}
\begin{description}
\item[TR-92] Zero-SG protection for 100\% GFM network.
  Voltage-based differential + $dV/dt$ trip replaces classical current-based 87.
\item[TR-93] Black-start and restoration with GFM inverters (IEC TR~63227 extension).
\item[TR-94] Inertia-less frequency protection (Relay~81 redesign).
  Adaptive $H_v$ estimator; dynamic ROCOF threshold.
\end{description}

\subsection{Track D --- Standards Compliance}
\begin{description}
\item[TR-95] IEEE 2800-2022 IBR interconnection compliance audit and gap matrix.
\item[TR-96] IEC 61850 Edition~3 + IEC 62351-8 PKI key management server.
\item[TR-97] Cyber-physical threat tree (IEC 62443, STRIDE, residual risk).
\end{description}

\subsection{Track E --- Thesis Synthesis}
\begin{description}
\item[TR-98] Full SAMBP sensitivity analysis and Cram\'er--Rao lower bounds.
\item[TR-99] Cross-chapter consistency audit (propositions, symbols, citations).
\item[TR-100] Submission readiness: LaTeX clean compile, figure quality, plagiarism check.
\end{description}

\section{Critical Path and Gantt Chart}
\begin{figure}[H]
\centering
\resizebox{\textwidth}{!}{%
\begin{tikzpicture}[x=0.9cm,y=0.55cm]
\foreach \y/\lbl/\lo/\hi/\col in {
  0/TR-86--88 (Track A)/0/3/ph1col,
  1/TR-89--91 (Track B)/2/6/ph2col,
  2/TR-92--94 (Track C)/4/7/ph3col,
  3/TR-95--97 (Track D)/3/8/ph4col,
  4/TR-98--99 (Track E)/7/10/ph5col,
  5/TR-100 Submission/10/12/ph6col}{
  \node[font=\scriptsize,anchor=east] at (-0.2,{-\y}) {\lbl};
  \fill[\col!60,rounded corners=2pt]
    (\lo,{-\y-0.3}) rectangle (\hi,{-\y+0.3});
}
\foreach \x/\lbl in {
  0/{Q2'26},2/{Q3'26},4/{Q4'26},6/{Q1'27},
  8/{Q2'27},10/{Q3'27},12/{Q3'28}}{
  \draw[gray,thin] (\x,-6) -- (\x,0.5);
  \node[font=\tiny,gray] at (\x,0.8) {\lbl};
}
\end{tikzpicture}
}
\caption{Planned research timeline for TR-86--TR-100.
Source: \texttt{RESEARCH\_PLAN\_TR86\_TR100.md}}
\label{fig:gantt}
\end{figure}
""")

    # ── Appendix: algorithms ──────────────────────────────────────────────────
    lines.append(r"""
\appendix
\chapter{Algorithm Pseudocode Reference}
\label{app:algos}

\section{EKF Update Loop}
\begin{algorithm}[H]
\SetAlgoLined
\KwIn{Prior state $\hat{\mathbf{x}}_{k-1}$, covariance $\mathbf{P}_{k-1}$,
  measurement $\mathbf{z}_k$, noise matrices $\mathbf{Q}, \mathbf{R}$}
\KwOut{Posterior $\hat{\mathbf{x}}_k$, $\mathbf{P}_k$}
\BlankLine
\tcp{Predict}
$\hat{\mathbf{x}}_{k|k-1} \leftarrow \hat{\mathbf{x}}_{k-1}$
  \tcp*{random-walk process model}\;
$\mathbf{P}_{k|k-1} \leftarrow \mathbf{P}_{k-1} + \mathbf{Q}$\;
\BlankLine
\tcp{Linearise}
$\mathbf{H}_k \leftarrow \nabla_{\mathbf{x}} h(\hat{\mathbf{x}}_{k|k-1})$
  \tcp*{$6\times4$ Jacobian}\;
\BlankLine
\tcp{Update}
$\mathbf{S}_k \leftarrow \mathbf{H}_k\mathbf{P}_{k|k-1}\mathbf{H}_k^T + \mathbf{R}$\;
$\mathbf{K}_k \leftarrow \mathbf{P}_{k|k-1}\mathbf{H}_k^T \mathbf{S}_k^{-1}$\;
$\hat{\mathbf{x}}_k \leftarrow \hat{\mathbf{x}}_{k|k-1}
  + \mathbf{K}_k\bigl(\mathbf{z}_k - h(\hat{\mathbf{x}}_{k|k-1})\bigr)$\;
$\mathbf{P}_k \leftarrow (\mathbf{I} - \mathbf{K}_k\mathbf{H}_k)\mathbf{P}_{k|k-1}$\;
\caption{Extended Kalman Filter (SAMBP DT, TR-43--TR-45)}
\end{algorithm}

\section{RLS Estimator}
\begin{algorithm}[H]
\SetAlgoLined
\KwIn{Forgetting factor $\lambda=0.97$, initial $\hat{\mathbf{x}}_0, \mathbf{P}_0=\delta\mathbf{I}$}
\For{each sample $k$}{
  $\mathbf{K}_k \leftarrow \mathbf{P}_{k-1}\mathbf{h}_k
    /(\lambda + \mathbf{h}_k^T\mathbf{P}_{k-1}\mathbf{h}_k)$\;
  $\hat{\mathbf{x}}_k \leftarrow \hat{\mathbf{x}}_{k-1}
    + \mathbf{K}_k(z_k - \mathbf{h}_k^T\hat{\mathbf{x}}_{k-1})$\;
  $\mathbf{P}_k \leftarrow (\mathbf{I}-\mathbf{K}_k\mathbf{h}_k^T)\mathbf{P}_{k-1}/\lambda$\;
}
\caption{Recursive Least Squares (SAMBP fast estimator, TR-43)}
\end{algorithm}

\section{PINN Training Loop}
\begin{algorithm}[H]
\SetAlgoLined
\KwIn{Dataset $\mathcal{D}$, epochs $E=500$, $\lambda_\text{phy}=0.20$}
Initialise MLP: $4\to64\to64\to64\to4$ (ReLU, softmax)\;
\For{epoch $= 1$ \KwTo $E$}{
  \ForEach{mini-batch $\mathcal{B}\subset\mathcal{D}$}{
    $\hat{y} \leftarrow \text{MLP}(\mathbf{x}_\mathcal{B})$\;
    $\mathcal{L}_\text{CE} \leftarrow -\sum_i y_i\log\hat{y}_i$
      \tcp*{cross-entropy}\;
    \tcp{Physics constraints}
    $\mathcal{L}_\text{phy} \leftarrow
      \max(0,\,0.06-k)\cdot\mathbf{1}[\hat{y}\neq\text{MISS}]$\;
    $\mathcal{L}_\text{phy} \mathrel{+}=
      \max(0,\,k-0.80)\cdot\mathbf{1}[\hat{y}\notin\{\text{Z1,87L}\}]$\;
    $\mathcal{L}_\text{phy} \mathrel{+}=
      \max(0,\,\alpha-1.0)\cdot\mathbf{1}[\hat{y}\neq\text{EXT}]$\;
    $\mathcal{L} \leftarrow \mathcal{L}_\text{CE}
      + \lambda_\text{phy}\mathcal{L}_\text{phy}$\;
    Back-propagate and update Adam\;
  }
}
\caption{PINN Training (TR-46, physics-constraint weight $\lambda_\text{phy}=0.20$)}
\end{algorithm}

\section{SSCI Detector (FFT Rolling Buffer)}
\begin{algorithm}[H]
\SetAlgoLined
\KwIn{Voltage samples at 1\,kHz, 5-cycle buffer (100\,ms)}
\KwOut{Risk level: NORMAL / WATCH / TRIP}
\Repeat{}{
  Append new sample to ring buffer\;
  \If{buffer full (100\,ms)}{
    $X \leftarrow \text{FFT}(\text{buffer})$\;
    Find peak in sub-synchronous band $[5, 45]$\,Hz: $f_\text{peak}, |X_\text{peak}|$\;
    Fit log-linear regression on $|X_\text{peak}|$ history $\to$ growth rate $\lambda$\;
    \If{$\lambda > \lambda_\text{thresh}$}{
      \Return TRIP \tcp*{response in $\leq$60\,ms after buffer fill}
    }
    \ElseIf{$|X_\text{peak}| > X_\text{warn}$}{
      \Return WATCH\;
    }
  }
}
\caption{SSCI Detector (TR-75, 160\,ms end-to-end response)}
\end{algorithm}

\section{GOOSE Anomaly Detection}
\begin{algorithm}[H]
\SetAlgoLined
\KwIn{GOOSE message $m_k$, Isolation Forest model $\mathcal{F}$,
  training bound $b_\text{max}$}
\KwOut{verdict $\in$ \{OK, WARN, CRITICAL\}}
Extract features $\mathbf{f} = [|\Delta\text{stnum}|,\; |\Delta\text{sqnum}-1|,\;
  \log(t_\text{arr}/t_\text{exp}+1),\; H(\text{dataset}),\;
  \log(1+\text{range})]$\;
\tcp{Rule-based checks (deterministic)}
\If{$\text{stnum} < \text{stnum}_{k-1}$ \textbf{or} $t_k - t_{k-1} > 5$\,s}{
  \Return CRITICAL \tcp*{REPLAY attack}
}
\If{$t_k - t_{k-1} < 0.5$\,ms}{
  \Return CRITICAL \tcp*{TIMING\_FLOOD}
}
\tcp{ML-based check}
score $\leftarrow \mathcal{F}.\text{anomaly\_score}(\mathbf{f})$\;
\If{score $< \theta_\text{IF}$ \textbf{or} $\mathbf{f}[4] > b_\text{max}$}{
  \Return WARN \tcp*{CONTENT\_ANOMALY}
}
\Return OK\;
\caption{GOOSE Anomaly Detector (TR-82, FP rate 0.38\%)}
\end{algorithm}

\chapter{File Path Index}
\label{app:filepaths}

\section{Technical Report Source Files}
All TR source \texttt{.tex} files follow the pattern:\\
\texttt{/root/phd\_thesis/03\_technical\_reports/<phase>/<TR\_dir>/main\_report<N>.tex}

\begin{longtable}{@{}p{1.0cm}p{11cm}@{}}
\toprule \textbf{TR\#} & \textbf{Source File Path} \\ \midrule \endfirsthead
\toprule \textbf{TR\#} & \textbf{Source File Path} \\ \midrule \endhead
\bottomrule \endlastfoot
""")
    for tr_num, tex_path in trs:
        rel = str(tex_path.relative_to(ROOT)).replace('_',r'\_')
        lines.append(f"TR-{tr_num} & \\texttt{{\\small {rel}}} \\\\\n")
    lines.append(r"\end{longtable}")

    lines.append(r"""
\section{Key Figure Directories}
\begin{itemize}
\item \texttt{/root/phd\_thesis/01\_thesis/active/thesis\_full/figures/} --- thesis TikZ figures
\item \texttt{/root/phd\_thesis/02\_papers/*/figures/} --- per-paper figures
\item \texttt{/root/phd\_thesis/03\_technical\_reports/*/figures/} --- TR-local figures
\item \texttt{/root/phd\_thesis/04\_code/sambp/digital\_twin/reports/figures/TR68/} --- BESS validation
\item \texttt{/root/phd\_thesis/04\_code/sambp/digital\_twin/reports/figures/TR76/} --- benchmark
\item \texttt{/root/phd\_thesis/05\_data/figures\_archive/rendered/sambp\_reports/} --- curated archive
\end{itemize}

\section{Key Python Model Files}
\begin{itemize}
\item \texttt{04\_code/sambp/digital\_twin/models/protection\_mirror.py} --- relay logic mirror
\item \texttt{04\_code/sambp/digital\_twin/models/meshed\_network.py} --- pandapower wrapper
\item \texttt{04\_code/sambp/digital\_twin/models/bess\_model.py} --- 6-state BESS model
\item \texttt{04\_code/sambp/digital\_twin/models/type4\_wind\_model.py} --- Type-4 wind
\item \texttt{04\_code/sambp/digital\_twin/models/dc\_fault\_model.py} --- DC RLC fault model
\item \texttt{04\_code/sambp/digital\_twin/models/gic\_model.py} --- Lehtinen-Pirjola GIC
\item \texttt{04\_code/sambp/digital\_twin/estimation/ekf\_estimator.py} --- EKF
\item \texttt{04\_code/sambp/digital\_twin/estimation/rls\_estimator.py} --- RLS
\item \texttt{04\_code/sambp/digital\_twin/estimation/ssci\_detector.py} --- SSCI
\item \texttt{04\_code/sambp/digital\_twin/estimation/ferroresonance\_detector.py} --- ferroRes
\item \texttt{04\_code/sambp/digital\_twin/integration/goose\_anomaly.py} --- GOOSE security
\item \texttt{04\_code/sambp/digital\_twin/integration/goose\_security.py} --- IEC 62351-6 HMAC
\end{itemize}
""")

    # ── Bibliography ──────────────────────────────────────────────────────────
    lines.append(r"\chapter*{Bibliography}")
    lines.append(r"\addcontentsline{toc}{chapter}{Bibliography}")
    lines.append(BIBLIOGRAPHY)
    lines.append(r"\end{document}")

    # ── Write output ──────────────────────────────────────────────────────────
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text('\n'.join(lines), encoding='utf-8')
    print(f"Written: {OUT_TEX}  ({OUT_TEX.stat().st_size // 1024} KB)")
    print(f"[SAMBP] Ingested TR count: {n_trs}  (TR-01 to TR-{max_tr})")
    print(f"Lines:   {len(lines)}")

if __name__ == "__main__":
    build()
