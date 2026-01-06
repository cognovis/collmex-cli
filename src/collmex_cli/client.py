"""High-level Collmex client for common operations."""

from datetime import date

from .api import CollmexAPI
from .config import CollmexConfig
from .models import (
    AccountingDocument,
    OpenItem,
    Vendor,
    VendorInvoice,
    format_collmex_date,
)


class CollmexClient:
    """High-level client for Collmex API operations.

    Provides typed methods for common accounting operations.
    """

    def __init__(self, config: CollmexConfig | None = None):
        """Initialize client.

        Args:
            config: Optional configuration. If not provided, loads from environment.
        """
        self.api = CollmexAPI(config)

    def close(self) -> None:
        """Close the API connection."""
        self.api.close()

    def __enter__(self) -> "CollmexClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # =========================================================================
    # Vendors (Lieferanten)
    # =========================================================================

    def get_vendors(
        self,
        vendor_id: int | None = None,
        text: str | None = None,
        only_changed: bool = False,
    ) -> list[Vendor]:
        """Get vendors from Collmex.

        Args:
            vendor_id: Filter by specific vendor ID
            text: Search text
            only_changed: Only return changed records since last query

        Returns:
            List of Vendor objects
        """
        row = ["VENDOR_GET"]
        row.append(str(vendor_id) if vendor_id else "")
        row.append(str(self.api.config.company_id))
        row.append(text or "")
        row.append("")  # due for follow-up
        row.append("")  # postal code/country
        row.append("1" if only_changed else "")
        row.append("")  # system name

        results = self.api.request(row)
        return [Vendor.from_csv_row(r) for r in results if r and r[0] == "CMXLIF"]

    def create_vendor(self, vendor: Vendor) -> list[str]:
        """Create or update a vendor.

        Args:
            vendor: Vendor object to create/update

        Returns:
            Raw API response rows
        """
        return self.api.request(vendor.to_csv_row())

    def match_vendor(
        self,
        iban: str | None = None,
        vat_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Match a vendor by IBAN, VAT ID, or name.

        Matching priority:
        1. IBAN (exact match) - 100% confidence
        2. VAT ID (exact match) - 100% confidence
        3. Name (fuzzy match) - returns candidates

        Args:
            iban: IBAN to search for
            vat_id: VAT ID (USt-IdNr) to search for
            name: Company name to search for

        Returns:
            Dict with match result:
            - {"match": "exact", "vendor_id": 123, "vendor": {...}}
            - {"match": "fuzzy", "candidates": [...]}
            - {"match": "none"}
        """
        vendors = self.get_vendors()

        # 1. Try IBAN match (exact)
        if iban:
            iban_clean = iban.replace(" ", "").upper()
            for v in vendors:
                if v.iban and v.iban.replace(" ", "").upper() == iban_clean:
                    return {
                        "match": "exact",
                        "match_field": "iban",
                        "vendor_id": v.vendor_id,
                        "vendor": v.model_dump(),
                    }

        # 2. Try VAT ID match (exact)
        if vat_id:
            vat_clean = vat_id.replace(" ", "").upper()
            for v in vendors:
                if v.vat_id and v.vat_id.replace(" ", "").upper() == vat_clean:
                    return {
                        "match": "exact",
                        "match_field": "vat_id",
                        "vendor_id": v.vendor_id,
                        "vendor": v.model_dump(),
                    }

        # 3. Try name match (fuzzy)
        if name:
            name_lower = name.lower()
            candidates = []
            for v in vendors:
                vendor_name = v.company_name or f"{v.first_name} {v.last_name}".strip()
                if not vendor_name:
                    continue
                vendor_name_lower = vendor_name.lower()

                # Calculate simple similarity score
                score = self._fuzzy_score(name_lower, vendor_name_lower)
                if score > 0.4:  # Threshold for consideration
                    candidates.append({
                        "vendor_id": v.vendor_id,
                        "name": vendor_name,
                        "score": round(score, 2),
                        "vendor": v.model_dump(),
                    })

            if candidates:
                # Sort by score descending
                candidates.sort(key=lambda x: x["score"], reverse=True)
                # If top match is very good, return as exact
                if candidates[0]["score"] > 0.9:
                    return {
                        "match": "exact",
                        "match_field": "name",
                        "vendor_id": candidates[0]["vendor_id"],
                        "vendor": candidates[0]["vendor"],
                    }
                return {
                    "match": "fuzzy",
                    "candidates": candidates[:5],  # Top 5
                }

        return {"match": "none"}

    def _fuzzy_score(self, s1: str, s2: str) -> float:
        """Calculate fuzzy match score between two strings.

        Uses a simple approach: longest common subsequence ratio.
        """
        # Check for substring match first
        if s1 in s2 or s2 in s1:
            return 0.95

        # Simple token overlap
        tokens1 = set(s1.split())
        tokens2 = set(s2.split())
        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2
        return len(intersection) / len(union)

    # =========================================================================
    # Vendor Invoices (Lieferantenrechnungen)
    # =========================================================================

    def create_vendor_invoice(self, invoice: VendorInvoice) -> list[str]:
        """Create a vendor invoice (books expense in accounting).

        Args:
            invoice: VendorInvoice object

        Returns:
            Raw API response rows
        """
        return self.api.request(invoice.to_csv_row())

    # =========================================================================
    # Open Items (Offene Posten)
    # =========================================================================

    def get_open_items(
        self,
        vendor: bool = False,
        customer_id: int | None = None,
        vendor_id: int | None = None,
        cutoff_date: date | None = None,
    ) -> list[OpenItem]:
        """Get open items (unpaid invoices).

        Args:
            vendor: True for vendor open items, False for customer
            customer_id: Filter by customer ID
            vendor_id: Filter by vendor ID
            cutoff_date: Cutoff date for open items

        Returns:
            List of OpenItem objects
        """
        row = ["OPEN_ITEMS_GET"]
        row.append(str(self.api.config.company_id))
        row.append("1" if vendor else "0")
        row.append(str(customer_id) if customer_id else "")
        row.append(str(vendor_id) if vendor_id else "")
        row.append("")  # vermittler
        row.append(format_collmex_date(cutoff_date) if cutoff_date else "")

        results = self.api.request(row)
        return [OpenItem.from_csv_row(r) for r in results if r and r[0] == "OPEN_ITEM"]

    # =========================================================================
    # Accounting Documents (Buchungen)
    # =========================================================================

    def get_bookings(
        self,
        fiscal_year: int | None = None,
        booking_id: int | None = None,
        account_number: int | None = None,
        customer_id: int | None = None,
        vendor_id: int | None = None,
        invoice_number: str | None = None,
        text: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        include_cancelled: bool = False,
        only_changed: bool = False,
    ) -> list[AccountingDocument]:
        """Get accounting documents/bookings.

        Args:
            fiscal_year: Filter by fiscal year
            booking_id: Filter by booking number
            account_number: Filter by account number
            customer_id: Filter by customer ID
            vendor_id: Filter by vendor ID
            invoice_number: Filter by invoice number
            text: Search in booking text and memo
            date_from: Start date filter
            date_to: End date filter
            include_cancelled: Include cancelled bookings
            only_changed: Only return changed records

        Returns:
            List of AccountingDocument objects
        """
        row = ["ACCDOC_GET"]
        row.append(str(self.api.config.company_id))
        row.append(str(fiscal_year) if fiscal_year else "")
        row.append(str(booking_id) if booking_id else "")
        row.append(str(account_number) if account_number else "")
        row.append("")  # cost center
        row.append(str(customer_id) if customer_id else "")
        row.append(str(vendor_id) if vendor_id else "")
        row.append("")  # asset number
        row.append(str(invoice_number) if invoice_number else "")
        row.append("")  # travel number
        row.append(text or "")
        row.append(format_collmex_date(date_from) if date_from else "")
        row.append(format_collmex_date(date_to) if date_to else "")
        row.append("1" if include_cancelled else "")
        row.append("1" if only_changed else "")

        results = self.api.request(row)
        return [AccountingDocument.from_csv_row(r) for r in results if r and r[0] == "ACCDOC"]

    def get_unmatched_bank_transactions(
        self,
        bank_account: int = 1200,
        fiscal_year: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[AccountingDocument]:
        """Get bank transactions that don't have a matching counter-booking.

        This helps identify bank statement entries that still need invoices/receipts.

        Args:
            bank_account: Bank account number (default: 1200)
            fiscal_year: Filter by fiscal year
            date_from: Start date filter
            date_to: End date filter

        Returns:
            List of unmatched bank transactions
        """
        # Get all bank account bookings
        bookings = self.get_bookings(
            fiscal_year=fiscal_year,
            account_number=bank_account,
            date_from=date_from,
            date_to=date_to,
        )

        # Filter to find entries without matching vendor/customer reference
        # These are typically imported bank transactions without counter-bookings
        unmatched = []
        for booking in bookings:
            # Bank transactions without vendor/customer assignment likely need matching
            if booking.vendor_id is None and booking.customer_id is None:
                # Also check if there's no invoice number
                if not booking.invoice_number:
                    unmatched.append(booking)

        return unmatched
