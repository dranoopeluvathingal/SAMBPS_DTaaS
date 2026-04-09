"""
lock_pdf.py
-----------
Applies 256-bit AES encryption to PDF files to disable text/equation
copy-pasting in compliant viewers while leaving the document freely
openable (blank user password) and printable.

Protection model
----------------
  - User password  : blank  → anyone can open without a prompt
  - Owner password : set    → required to change permissions or remove encryption
  - Encryption     : AES-256 (PDF revision 6, ISO 32000-2)
  - Permissions allowed    : high-res printing, low-res printing, annotations
  - Permissions disabled   : extract (copy/paste text), content modification,
                             form filling, assembly

Honest limitation
-----------------
This is a deterrent, not a cryptographic lock. Specialist tools (qpdf,
Ghostscript, pdf2txt) that ignore permission flags can still extract text.
For pre-publication circulation to trusted reviewers it provides a strong
first layer against casual plagiarism.

Usage
-----
  python lock_pdf.py                # interactive: prompts for owner password
  OWNER_PW=secret python lock_pdf.py  # non-interactive: reads from env var
"""

import pikepdf
import os
import sys
import getpass
from pathlib import Path


# ── Files to protect ──────────────────────────────────────────────────────────
TARGETS = [
    {
        "input":  "new_thesis_edit/thesis_main.pdf",
        "output": "new_thesis_edit/thesis_main_copylocked.pdf",
        "label":  "PhD Thesis",
    },
    {
        "input":  "TSA_meeting_Eluvathingal.pdf",
        "output": "TSA_meeting_Eluvathingal_copylocked.pdf",
        "label":  "TSA Presentation (22 slides)",
    },
    {
        "input":  "TSA_notes_Eluvathingal.pdf",
        "output": "TSA_notes_Eluvathingal_copylocked.pdf",
        "label":  "Speaker Notes (15 pp)",
    },
]

# ── Permission profile ─────────────────────────────────────────────────────────
PERMISSIONS = pikepdf.Permissions(
    accessibility=True,       # allow screen readers (accessibility obligation)
    extract=False,            # ← disable copy/paste of text and equations
    modify_annotation=False,  # disable adding comments/stamps
    modify_assembly=False,    # disable page reordering/insertion
    modify_form=False,        # disable form filling
    modify_other=False,       # disable all other content modification
    print_lowres=True,        # allow low-res printing (draft review)
    print_highres=True,       # allow high-res printing (committee copy)
)


def lock_pdf(input_path: str, output_path: str, owner_password: str, label: str) -> None:
    inp = Path(input_path)
    out = Path(output_path)

    if not inp.exists():
        print(f"  [SKIP] {label}: input not found at {inp}")
        return

    with pikepdf.Pdf.open(str(inp)) as pdf:
        page_count = len(pdf.pages)
        pdf.save(
            str(out),
            encryption=pikepdf.Encryption(
                user="",                  # blank → opens without password prompt
                owner=owner_password,     # locks permission changes
                R=6,                      # revision 6 = AES-256
                aes=True,                 # force AES (not RC4)
                allow=PERMISSIONS,
            ),
            compress_streams=True,
        )

    size_in  = inp.stat().st_size  / 1024
    size_out = out.stat().st_size  / 1024
    print(f"  [OK]   {label}")
    print(f"         {inp.name} ({page_count} pages, {size_in:.0f} KB)")
    print(f"       → {out.name} ({size_out:.0f} KB)")
    print(f"         Encryption : AES-256 (R=6)")
    print(f"         User PW    : <blank>  (opens freely)")
    print(f"         Owner PW   : set      (permissions locked)")
    print(f"         Copy/paste : DISABLED in compliant viewers")
    print(f"         Printing   : ALLOWED  (high-res + low-res)")
    print()


def get_owner_password() -> str:
    # 1. Check environment variable (CI / non-interactive use)
    pw = os.environ.get("OWNER_PW", "").strip()
    if pw:
        print("  Using owner password from OWNER_PW environment variable.")
        return pw

    # 2. Interactive prompt (terminal use)
    print("  Enter the owner password (hidden, not echoed):")
    pw = getpass.getpass("  Owner password: ").strip()
    if not pw:
        print("ERROR: Owner password cannot be blank — it would leave the PDF unprotected.")
        sys.exit(1)

    confirm = getpass.getpass("  Confirm password: ").strip()
    if pw != confirm:
        print("ERROR: Passwords do not match.")
        sys.exit(1)

    return pw


if __name__ == "__main__":
    print("=" * 60)
    print("  SAMBP Thesis PDF Copy-Lock Utility")
    print("  Anoop V Eluvathingal · IIT Madras · 2026")
    print("=" * 60)
    print()

    owner_pw = get_owner_password()
    print()
    print(f"  Protecting {len(TARGETS)} document(s)...\n")

    for t in TARGETS:
        lock_pdf(t["input"], t["output"], owner_pw, t["label"])

    print("=" * 60)
    print("  Done. Distribute the *_copylocked.pdf files.")
    print("  Keep the owner password in a secure location.")
    print("=" * 60)
