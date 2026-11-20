import os
import tempfile
import unittest
from email.message import EmailMessage

import collect_receipts as cr


class ParseTest(unittest.TestCase):
    def test_parse_receipt(self):
        m = EmailMessage()
        m["Subject"] = "Your receipt from Shop"
        m["From"] = "Shop <no-reply@shop.com>"
        m["Date"] = "Tue, 03 Nov 2026 10:00:00 +0000"
        m["Message-ID"] = "<abc@shop>"
        m.set_content("Item 1  $5.00\nItem 2  $120.00\nTotal: $125.00\n")
        m.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf", filename="receipt.pdf")
        with tempfile.TemporaryDirectory() as d:
            row = cr.parse_message(m.as_bytes(), "me@gmail.com", d)
            self.assertEqual(row["amount_guess"], "$125.00")
            self.assertEqual(row["date"], "2026-11-03 10:00")
            self.assertTrue(row["attachments"].endswith("receipt.pdf"))
            self.assertTrue(os.path.exists(os.path.join(d, row["attachments"])))

    def test_amount_from_html(self):
        m = EmailMessage()
        m.set_content("<p>Order</p><td>Grand Total</td><td>EUR 49.90</td>", subtype="html")
        self.assertEqual(cr.guess_amount(cr.body_text(m)), "EUR 49.90")


if __name__ == "__main__":
    unittest.main()
