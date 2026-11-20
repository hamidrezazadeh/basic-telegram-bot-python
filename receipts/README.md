# Receipt collector (many Gmail accounts)

Finds receipt emails in all your Gmail accounts and puts them in one CSV file.
PDF and image attachments are saved too. It only **reads** your mail.

## 1. Make an app password for each Gmail

1. Turn on **2-Step Verification**: https://myaccount.google.com/security
2. Create an **app password**: https://myaccount.google.com/apppasswords
3. Copy the 16-letter password.

(IMAP is on by default for Gmail. If not: Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP.)

## 2. Easy way: the website

```bash
python3 web.py
```

Your browser opens http://127.0.0.1:8000. There you can:

- add or remove Gmail accounts (email + app password)
- choose a time range and press **Collect now**
- search the results, open saved PDFs, and download the CSV

The website runs only on your computer. Other computers cannot open it.
Passwords are saved in `accounts.json` and are never sent back to the page.
Press `Ctrl+C` in the terminal to stop it.

## 3. Or use the command line

### Add your accounts

```bash
cp accounts.example.json accounts.json
```

Edit `accounts.json` and put your emails and app passwords.
`accounts.json` is in `.gitignore`, so it is **not** pushed to GitHub.

### Run

```bash
python3 collect_receipts.py              # last 90 days
python3 collect_receipts.py --days 365   # last year
python3 collect_receipts.py --query 'from:(amazon OR uber) newer_than:6m'
```

## Result

- `output/receipts.csv` — date, account, sender, subject, amount guess, attachment paths
- `output/attachments/<account>/...` — saved PDFs and images

The same email in two accounts is kept only once.
`amount_guess` is a simple guess from the email text; check it before you use it.
