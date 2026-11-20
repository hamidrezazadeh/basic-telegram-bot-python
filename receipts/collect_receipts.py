"""Collect receipt emails from many Gmail accounts into one place.

Uses IMAP + Gmail app passwords. Only the Python standard library is needed.

Usage:
    python collect_receipts.py                 # last 90 days
    python collect_receipts.py --days 30
    python collect_receipts.py --query 'from:amazon newer_than:1y'
"""
import argparse
import csv
import email
import imaplib
import json
import os
import re
import sys
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

IMAP_HOST = "imap.gmail.com"
DEFAULT_QUERY = (
    'subject:(receipt OR invoice OR "order confirmation" OR "your order" '
    'OR payment OR bill OR "purchase") newer_than:{days}d'
)
ATTACH_TYPES = ("application/pdf", "image/")
# Simple money finder: $12.34, €5, 1,234.00 USD, EUR 9.99 ...
AMOUNT_RE = re.compile(
    r"(?:(?:[$€£¥]|USD|EUR|GBP|CAD|AUD)\s?\d[\d,]*(?:\.\d{2})?"
    r"|\d[\d,]*\.\d{2}\s?(?:USD|EUR|GBP|CAD|AUD))"
)
FIELDS = ["date", "account", "from", "subject", "amount_guess", "attachments", "message_id"]
TOTAL_RE = re.compile(r"(?:grand\s+)?total[^\n\d$€£¥]{0,30}", re.I)


def decode(value):
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def safe_name(text, limit=60):
    text = re.sub(r"[^\w.\- ]+", "_", text).strip() or "file"
    return text[:limit]


def body_text(msg):
    """Return plain text of the email (falls back to HTML with tags removed)."""
    plain, html = [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", "replace")
        (plain if ctype == "text/plain" else html).append(text)
    if plain:
        return "\n".join(plain)
    text = "\n".join(html)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"[ \t\r\f]+", " ", text)


def guess_amount(text):
    """Prefer an amount near the word 'total'; else the largest amount found."""
    for m in TOTAL_RE.finditer(text):
        near = AMOUNT_RE.search(text, m.end(), m.end() + 40)
        if near:
            return near.group(0).strip()
    found = AMOUNT_RE.findall(text)
    if not found:
        return ""

    def num(s):
        try:
            return float(re.sub(r"[^\d.]", "", s.replace(",", "")))
        except ValueError:
            return 0.0

    return max(found, key=num).strip()


def save_attachments(msg, folder):
    saved = []
    for part in msg.walk():
        filename = decode(part.get_filename())
        if not filename:
            continue
        if not part.get_content_type().startswith(ATTACH_TYPES):
            continue
        data = part.get_payload(decode=True)
        if not data:
            continue
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, safe_name(filename))
        base, ext = os.path.splitext(path)
        n = 1
        while os.path.exists(path):
            path = f"{base}_{n}{ext}"
            n += 1
        with open(path, "wb") as f:
            f.write(data)
        saved.append(path)
    return saved


def parse_message(raw, account, out_dir):
    msg = email.message_from_bytes(raw)
    subject = decode(msg.get("Subject"))
    try:
        date = parsedate_to_datetime(msg.get("Date"))
        date_str = date.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date, date_str = None, ""
    folder = os.path.join(
        out_dir, "attachments", safe_name(account),
        f"{date.strftime('%Y-%m-%d') if date else 'nodate'}_{safe_name(subject, 40)}",
    )
    return {
        "message_id": (msg.get("Message-ID") or "").strip(),
        "account": account,
        "date": date_str,
        "from": decode(msg.get("From")),
        "subject": subject,
        "amount_guess": guess_amount(body_text(msg)),
        "attachments": "; ".join(
            os.path.relpath(p, out_dir) for p in save_attachments(msg, folder)
        ),
    }


def find_all_mail(conn):
    """Find the 'All Mail' folder (its name changes with the Gmail language)."""
    typ, folders = conn.list()
    for line in folders or []:
        line = line.decode(errors="replace")
        if "\\All" in line:
            return line.rsplit(' "/" ', 1)[-1].strip()
    return "INBOX"


def collect_from_account(acc, query, out_dir, log=print):
    address = acc["email"]
    password = acc["app_password"].replace(" ", "")
    log(f"[{address}] connecting...")
    conn = imaplib.IMAP4_SSL(IMAP_HOST)
    try:
        conn.login(address, password)
        conn.select(find_all_mail(conn), readonly=True)
        # X-GM-RAW lets us use normal Gmail search words over IMAP.
        typ, data = conn.uid("SEARCH", "X-GM-RAW", f'"{query}"'.encode())
        uids = data[0].split() if data and data[0] else []
        log(f"[{address}] found {len(uids)} emails")
        rows = []
        for uid in uids:
            typ, parts = conn.uid("FETCH", uid, "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                rows.append(parse_message(raw, address, out_dir))
        return rows
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def build_query(days=90, query=None):
    return (query or DEFAULT_QUERY.format(days=days)).replace('"', '\\"')


def collect(accounts, query, out_dir, log=print):
    """Collect receipts from all accounts. Writes receipts.csv/.json and returns rows."""
    os.makedirs(out_dir, exist_ok=True)
    all_rows, seen, ok = [], set(), 0
    for acc in accounts:
        try:
            rows = collect_from_account(acc, query, out_dir, log)
            ok += 1
        except imaplib.IMAP4.error as e:
            log(f"[{acc.get('email')}] login/search failed: {e}")
            continue
        except OSError as e:
            log(f"[{acc.get('email')}] network error: {e}")
            continue
        for r in rows:  # same email sent to 2 accounts -> keep once
            key = r["message_id"] or (r["account"], r["date"], r["subject"])
            if key not in seen:
                seen.add(key)
                all_rows.append(r)

    if not ok:
        log("No account worked, so old results were kept.")
        return None

    all_rows.sort(key=lambda r: r["date"], reverse=True)
    with open(os.path.join(out_dir, "receipts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(all_rows)
    with open(os.path.join(out_dir, "receipts.json"), "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=1)
    log(f"Done: {len(all_rows)} receipts saved.")
    return all_rows


def load_accounts(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f).get("accounts", [])


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Collect receipts from many Gmail accounts.")
    ap.add_argument("--accounts", default=os.path.join(here, "accounts.json"))
    ap.add_argument("--days", type=int, default=90, help="how many days back (default 90)")
    ap.add_argument("--query", help="your own Gmail search (overrides --days)")
    ap.add_argument("--out", default=os.path.join(here, "output"))
    args = ap.parse_args()

    if not os.path.exists(args.accounts):
        sys.exit(f"Missing {args.accounts}. Copy accounts.example.json to accounts.json and edit it.")
    collect(load_accounts(args.accounts), build_query(args.days, args.query), args.out)
    print(f"CSV: {os.path.join(args.out, 'receipts.csv')}")


if __name__ == "__main__":
    main()
