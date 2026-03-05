# Collmex API: Record Type Reference

**Source:** https://www.collmex.de/handbuch_buchhaltung_pro.html#api

## MANDATORY: Always look up the real API docs first

Before implementing ANY new Collmex record type or query:

1. **Fetch the official docs**: `crwl crawl "https://www.collmex.de/handbuch_buchhaltung_pro.html" -o md`
2. Find the relevant section (e.g. "Collmex API: Zahlungseingänge zu externen Rechnungen abfragen")
3. Copy the exact field table into your implementation
4. **Never assume field positions** — Collmex fields are positional CSV, one off-by-one breaks everything

## General API conventions

- **Protocol:** HTTP POST, `Content-Type: text/csv`
- **Encoding:** ISO-8859-1 (default) or UTF-8 (set field 4 of LOGIN to `1`)
- **Delimiter:** `;` (semicolon)
- **Dates:** `YYYYMMDD` format (type `D`), or `TT.MM.JJJJ` in some older response fields
- **Decimals:** German format with comma separator (`195,05`) — use `parse_collmex_decimal()`
- **First row:** Always `LOGIN;username;password`
- **Response errors:** `MESSAGE;E;code;text` rows — checked by `_check_errors()`
- **Rate limit:** 10,000 API calls/day, 5 concurrent per user

## LOGIN

| Nr | Field | Note |
|----|-------|-------|
| 1 | Satzart | `LOGIN` |
| 2 | Benutzer | API username |
| 3 | Passwort | API password |
| 4 | Zeichensatz | Optional: `0`=ISO-8859-1, `1`=UTF-8 |

## ACCDOC_GET → ACCDOC

### Query (ACCDOC_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `ACCDOC_GET` |
| 2 | Firma Nr | I | Company ID |
| 3 | Geschäftsjahr | I | Optional |
| 4 | Nr | I | Booking number |
| 5 | Kontonummer | I | Account number |
| 6 | Kostenstelle | I | Cost center |
| 7 | Kundennummer | I | Customer number |
| 8 | Lieferantennummer | I | Vendor number |
| 9 | Anlagenummer | I | Asset number |
| 10 | Rechnungsnummer | I | Invoice number |
| 11 | Reisenummer | I | Travel number |
| 12 | Text | C | Free text search |
| 13 | Belegdatum von | D | Date from |
| 14 | Belegdatum bis | D | Date to |
| 15 | Stornos | I | `1` = include cancelled |
| 16 | Nur geänderte | I | `1` = only changed since last query |
| 17 | Systemname | C | External system name |
| 18 | Zahlung Nr | I | Payment number |

### Response (ACCDOC)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `ACCDOC` |
| 2 | Firma Nr | I | |
| 3 | Geschäftsjahr | I | |
| 4 | Buchungsnummer | I | |
| 5 | Belegdatum | C | Format TT.MM.JJJJ (legacy) |
| 6 | Gebucht am | C | Format TT.MM.JJJJ (legacy) |
| 7 | Buchungstext | C | |
| 8 | Positionsnummer | I | |
| 9 | Kontonummer | I | |
| 10 | Kontoname | C | |
| 11 | Soll/Haben | I | `0`=Debit, `1`=Credit |
| 12 | Betrag | M | |
| 13 | Kunde Nummer | I | |
| 14 | Kunde Name | C | |
| 15 | Lieferant Nummer | I | |
| 16 | Lieferant Name | C | |
| 17 | Anlage Nummer | I | |
| 18 | Anlage Name | C | |
| 19 | Stornierte Buchung | I | |
| 20 | Kostenstelle | C | |
| 21 | Rechnungsnummer | C | |
| 22 | Kundenauftrag Nummer | I | |
| 23 | Reise Nummer | I | |
| 24 | Zugeordnet Nummer | I | |
| 25 | Zugeordnet Geschäftsjahr | I | |
| 26 | Zugeordnet Positionsnummer | I | |
| 27 | Beleg Nr | I | |
| 28 | Belegdatum | D | ISO format YYYYMMDD |
| 29 | Gebucht am | D | ISO format YYYYMMDD |
| 30 | Internes Memo | C | |
| 31 | Gebucht von | C | Username |

## INVOICE_PAYMENT_GET → INVOICE_PAYMENT

**Important:** Only works for invoices imported via `CMXUMS`. Not for invoices created in Collmex itself.

### Query (INVOICE_PAYMENT_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `INVOICE_PAYMENT_GET` |
| 2 | Firma Nr | I | Company ID |
| 3 | Rechnungsnummer | C | Optional. If empty, returns all invoices. |
| 4 | Nur neue Zahlungen | I | `1` = only new since last query |
| 5 | Systemname | C | External system name |

**No customer_id filter exists.** Filter by invoice number only.

### Response (INVOICE_PAYMENT)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `INVOICE_PAYMENT` |
| 2 | Rechnungsnummer | C | |
| 3 | Datum | D | Payment date (YYYYMMDD) |
| 4 | Gezahlter Betrag | M | Actually paid via bank/cash |
| 5 | Reduzierender Betrag | M | Open item reduced by this amount (may differ due to Skonto/discounts) |
| 6 | Geschäftsjahr | I | Fiscal year of the booking |
| 7 | BuchungNr | I | Booking number |
| 8 | BuchungPos | I | Booking position |
| 9 | Systemname | C | External system name |

**Key:** Geschäftsjahr + BuchungNr + BuchungPos uniquely identify a payment.
When a payment is reversed (storniert), Datum and Betrag are empty.

## OPEN_ITEMS_GET → OPEN_ITEM

### Query (OPEN_ITEMS_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `OPEN_ITEMS_GET` |
| 2 | Firma Nr | I | Company ID |
| 3 | Offene Posten | I | `0`/empty=Customer, `1`=Vendor |
| 4 | Kunde Nr | I | Optional |
| 5 | Lieferant Nr | I | Optional |
| 6 | Vermittler | I | Optional |
| 7 | Stichtag | D | Optional cutoff date |

### Response (OPEN_ITEM)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `OPEN_ITEM` |
| 2 | Firma Nr | I | |
| 3 | Geschäftsjahr | I | |
| 4 | Buchungsnummer | I | |
| 5 | Positionsnummer | I | |
| 6 | Kunde Nummer | I | |
| 7 | Kunde Name | C | |
| 8 | Lieferant Nummer | I | |
| 9 | Lieferant Name | C | |
| 10 | Rechnungsnummer | C | |
| 11 | Belegdatum | D | |
| 12 | Zahlungsbedingung | I | |
| 13 | Fälligkeit | D | |
| 14 | Verzug | I | Days overdue |
| 15 | Mahnstufe | I | Dunning level |
| 16 | Mahndatum | D | Last dunning date |
| 17 | Mahngebühren | M | |
| 18 | Betrag | M | |
| 19 | Bezahlt | M | |
| 20 | Offen | M | |

## VENDOR_GET → CMXLIF

### Query (VENDOR_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `VENDOR_GET` |
| 2 | Lieferanten Nr | I | Optional |
| 3 | Firma Nr | I | Company ID |
| 4 | Text | C | Free text search |
| 5 | Fällig zur Wiedervorlage | I | `1` = only due for follow-up |
| 6 | PLZ/Land | C | Postal code or country search |
| 7 | Nur geänderte | I | `1` = only changed since last query |
| 8 | Systemname | C | External system name |

Response: `CMXLIF` records (see Satzbeschreibung Lieferant in docs).

## CUSTOMER_GET → CMXKND

### Query (CUSTOMER_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `CUSTOMER_GET` |
| 2 | Kunde Nr | I | Optional |
| 3 | Firma Nr | I | Company ID |
| 4 | Text | C | Free text search |
| 5 | Fällig zur Wiedervorlage | I | |
| 6 | PLZ/Land | C | |
| 7 | Adressgruppe | I | |
| 8 | Preisgruppe | I | |
| 9 | Rabattgruppe | I | |
| 10 | Vermittler | I | |
| 11 | Nur geänderte | I | |
| 12 | Systemname | C | |
| 13 | Inaktive | I | `1` = include inactive |

Response: `CMXKND` records.

## ACCBAL_GET → ACC_BAL

### Query (ACCBAL_GET)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `ACCBAL_GET` |
| 2 | Firma Nr | I | |
| 3 | Geschäftsjahr | I | |
| 4 | Datum bis | D | Optional |
| 5 | Kontonummer | I | Optional |
| 6 | Kontengruppe | I | 1=Misc, 2=Assets, 3=Financial, 4=Revenue, 5=Expenses… |
| 7 | Kunde Nr | I | Optional |
| 8 | Lieferant Nr | I | Optional |
| 9 | Kostenstelle | C | Optional |

### Response (ACC_BAL)

| Nr | Field | Type | Note |
|----|-------|------|-------|
| 1 | Satzart | C | `ACC_BAL` |
| 4 | Kontonummer | I | (fields 2-3 not documented) |
| 5 | Kontoname | C | |
| 6 | Saldo | M | |

## Other query types

| Satzart | Description |
|---------|-------------|
| `DATEV_EXPORT_GET` | DATEV export as ZIP |
| `API_LOG_GET` | API error log entries |
| `BANK_STATEMENT_GET_FROM_BANK` | Fetch bank statement via HBCI |
| `EMPLOYEE_GET` | Query employees |
| `API_NOTIFICATION` | Configure change notifications |
