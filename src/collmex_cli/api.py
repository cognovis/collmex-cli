"""Low-level Collmex API client."""

import csv
import io
from typing import Any

import httpx

from .config import CollmexConfig, get_config


class CollmexError(Exception):
    """Base exception for Collmex API errors."""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class CollmexAuthError(CollmexError):
    """Authentication failed."""


class CollmexAPI:
    """Low-level Collmex API client.

    Handles CSV encoding/decoding and HTTP communication with the Collmex API.
    The Collmex API uses:
    - Semicolon-delimited CSV
    - Windows-1252 encoding
    - Login credentials prepended to each request
    - Multipart form data POST requests
    """

    ENCODING = "windows-1252"
    CSV_DELIMITER = ";"

    def __init__(self, config: CollmexConfig | None = None):
        """Initialize the API client.

        Args:
            config: Optional configuration. If not provided, loads from environment.
        """
        self.config = config or get_config()
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-load HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "CollmexAPI":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _encode_csv(self, rows: list[list[str]]) -> bytes:
        """Encode rows as Collmex CSV format.

        Args:
            rows: List of rows, each row is a list of field values

        Returns:
            Encoded CSV bytes in Windows-1252
        """
        output = io.StringIO()
        writer = csv.writer(
            output,
            delimiter=self.CSV_DELIMITER,
            quotechar='"',
            quoting=csv.QUOTE_ALL,
            lineterminator="\r\n",
        )
        writer.writerows(rows)
        return output.getvalue().encode(self.ENCODING)

    def _decode_csv(self, data: bytes) -> list[list[str]]:
        """Decode Collmex CSV response.

        Args:
            data: Raw response bytes in Windows-1252

        Returns:
            List of rows, each row is a list of field values
        """
        text = data.decode(self.ENCODING)
        reader = csv.reader(
            io.StringIO(text),
            delimiter=self.CSV_DELIMITER,
            quotechar='"',
        )
        return list(reader)

    def _build_login_row(self) -> list[str]:
        """Build the LOGIN row for authentication."""
        return ["LOGIN", self.config.username, self.config.password]

    def request(self, *rows: list[str]) -> list[list[str]]:
        """Send a request to the Collmex API.

        Args:
            *rows: CSV rows to send (LOGIN is prepended automatically)

        Returns:
            List of response rows

        Raises:
            CollmexError: If the API returns an error
            CollmexAuthError: If authentication fails
        """
        # Prepend login row
        all_rows = [self._build_login_row(), *rows]
        payload = self._encode_csv(all_rows)

        # Send as multipart form data
        response = self.client.post(
            self.config.api_url,
            files={"file": ("data.csv", payload, "text/csv")},
        )
        response.raise_for_status()

        # Parse response
        result_rows = self._decode_csv(response.content)

        # Check for errors
        self._check_errors(result_rows)

        return result_rows

    def _check_errors(self, rows: list[list[str]]) -> None:
        """Check response rows for error messages.

        Args:
            rows: Response rows from the API

        Raises:
            CollmexError: If an error message is found
            CollmexAuthError: If authentication failed
        """
        for row in rows:
            if not row:
                continue
            record_type = row[0]
            if record_type == "MESSAGE":
                # MESSAGE format: MESSAGE;type;code;text;line
                # type: E=Error, W=Warning, S=Success
                msg_type = row[1] if len(row) > 1 else ""
                msg_code = row[2] if len(row) > 2 else ""
                msg_text = row[3] if len(row) > 3 else "Unknown error"

                if msg_type == "E":
                    # Check for auth errors
                    if msg_code in ("101001", "101002", "101003"):
                        raise CollmexAuthError(msg_text, msg_code)
                    raise CollmexError(msg_text, msg_code)

    def query(self, record_type: str, **params: Any) -> list[list[str]]:
        """Execute a query against the Collmex API.

        Args:
            record_type: The query type (e.g., "CUSTOMER_GET", "INVOICE_GET")
            **params: Query parameters as keyword arguments

        Returns:
            List of result rows (excluding MESSAGE rows)
        """
        # Build query row - first field is always the record type
        row = [record_type]

        # Add parameters in order (Collmex uses positional CSV fields)
        # The caller must know the correct order
        for value in params.values():
            if value is None:
                row.append("")
            elif isinstance(value, bool):
                row.append("1" if value else "0")
            else:
                row.append(str(value))

        result = self.request(row)

        # Filter out MESSAGE rows
        return [r for r in result if r and r[0] != "MESSAGE"]
