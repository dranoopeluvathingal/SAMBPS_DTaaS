"""SAMBPS DTaaS — Lab Tool

CLI for Claude-powered analysis of research documents.

Commands:
  ping              Verify API connectivity.
  ask <pdf> <q>     Ask a question about a PDF; answer streams to stdout.
                    Same PDF on subsequent calls is served from prompt cache.
"""

import argparse
import base64
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import anthropic

load_dotenv()

MODEL = "claude-opus-4-7"
SYSTEM_PROMPT = (
    "You are a research assistant for SAMBPS DTaaS PhD work — self-healing "
    "adaptive microgrid backup protection systems with digital twins. "
    "Answer precisely from the supplied document. Cite specific sections, "
    "equations, or figures when relevant. If the document does not address "
    "the question, say so explicitly rather than speculating."
)


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key == "your_api_key_here":
        sys.exit(
            "Error: ANTHROPIC_API_KEY missing or still set to placeholder.\n"
            "Edit .env and replace your_api_key_here with your real key."
        )
    return anthropic.Anthropic(api_key=api_key)


def cmd_ping(_args: argparse.Namespace) -> int:
    client = get_client()
    print(f"Testing connection to {MODEL}...")
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=64,
            messages=[{"role": "user", "content": "Reply with exactly: Connection successful!"}],
        )
        for block in msg.content:
            if block.type == "text":
                print(f"Response: {block.text}")
        return 0
    except anthropic.AuthenticationError:
        print("Auth failed — check your API key.", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1


def cmd_ask(args: argparse.Namespace) -> int:
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return 1
    if pdf_path.suffix.lower() != ".pdf":
        print(f"Warning: {pdf_path} does not have a .pdf extension", file=sys.stderr)

    client = get_client()
    pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")

    print(f"[{MODEL} | {pdf_path.name} | adaptive thinking | high effort]\n", file=sys.stderr)
    try:
        with client.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": args.question},
                ],
            }],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
            print()
            u = stream.get_final_message().usage
            print(
                f"\n[tokens — input: {u.input_tokens}, "
                f"cache write: {u.cache_creation_input_tokens or 0}, "
                f"cache read: {u.cache_read_input_tokens or 0}, "
                f"output: {u.output_tokens}]",
                file=sys.stderr,
            )
        return 0
    except anthropic.AuthenticationError:
        print("Auth failed — check your API key.", file=sys.stderr)
        return 1
    except anthropic.BadRequestError as e:
        print(f"Bad request: {e.message}", file=sys.stderr)
        return 1
    except anthropic.APIStatusError as e:
        print(f"API error {e.status_code}: {e.message}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="app.py",
        description="SAMBPS DTaaS lab tool — Claude-powered analysis of research documents.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", help="Verify API connectivity.")

    p_ask = sub.add_parser("ask", help="Ask a question about a PDF document.")
    p_ask.add_argument("pdf", help="Path to PDF file.")
    p_ask.add_argument("question", help="Question to ask (quote if it has spaces).")

    args = parser.parse_args()
    if args.cmd == "ping":
        return cmd_ping(args)
    if args.cmd == "ask":
        return cmd_ask(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
