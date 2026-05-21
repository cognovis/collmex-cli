#!/bin/bash
# Create visible Apple Mail drafts for a customer invoice.
# Usage: CUSTOMER_EMAIL=... INVOICE_NUMBER=... PDF_PATH=... XML_PATH=... bash create_mail_drafts.sh
set -euo pipefail

CUSTOMER_EMAIL="${CUSTOMER_EMAIL:?CUSTOMER_EMAIL is required}"
INVOICE_NUMBER="${INVOICE_NUMBER:?INVOICE_NUMBER is required}"
PDF_PATH="${PDF_PATH:?PDF_PATH is required}"
XML_PATH="${XML_PATH:?XML_PATH is required}"
BOOKKEEPING_EMAIL="${BOOKKEEPING_EMAIL:-buchhaltung@cognovis.de}"

if [ ! -f "$PDF_PATH" ]; then
  echo "PDF_PATH does not exist: $PDF_PATH" >&2
  exit 1
fi

if [ ! -f "$XML_PATH" ]; then
  echo "XML_PATH does not exist: $XML_PATH" >&2
  exit 1
fi

osascript - "$CUSTOMER_EMAIL" "$BOOKKEEPING_EMAIL" "$INVOICE_NUMBER" "$PDF_PATH" "$XML_PATH" <<'APPLESCRIPT'
on run argv
    set customerEmail to item 1 of argv
    set bookkeepingEmail to item 2 of argv
    set invoiceNumber to item 3 of argv
    set pdfPath to item 4 of argv
    set xmlPath to item 5 of argv

    tell application "Mail"
        activate

        set customerMessage to make new outgoing message with properties {subject:"Rechnung " & invoiceNumber, content:"Guten Tag," & return & return & "anbei erhalten Sie die Rechnung " & invoiceNumber & "." & return & return & "Viele Grüße" & return & "Malte Sussdorff", visible:true}
        tell customerMessage
            make new to recipient at end of to recipients with properties {address:customerEmail}
            make new attachment with properties {file name:POSIX file pdfPath}
        end tell

        set bookkeepingMessage to make new outgoing message with properties {subject:"Rechnung " & invoiceNumber, content:"Anbei Rechnung " & invoiceNumber & " als PDF und XML.", visible:true}
        tell bookkeepingMessage
            make new to recipient at end of to recipients with properties {address:bookkeepingEmail}
            make new attachment with properties {file name:POSIX file pdfPath}
            make new attachment with properties {file name:POSIX file xmlPath}
        end tell
    end tell
end run
APPLESCRIPT
