"""Internal HTTP runtime seam for ZUGFeRD document enrichment."""

from __future__ import annotations

import base64
import binascii
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .invoice_snapshot import InvoiceSnapshot, InvoiceSnapshotError
from .zugferd import generate_invoice_documents


class DocumentRequest(BaseModel):
    """One document-generation request from the invoice application."""

    model_config = ConfigDict(extra="forbid")

    snapshot: InvoiceSnapshot
    visible_pdf_base64: str


class DocumentResponse(BaseModel):
    """Generated hybrid PDF and sidecar XML encoded for JSON transport."""

    pdf_base64: str
    xml_base64: str


app = FastAPI(
    title="collmex-cli ZUGFeRD service",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _configured_token() -> bytes | None:
    """Load the shared credential from its configured secret file."""
    token_path = os.environ.get("ZUGFERD_AUTH_TOKEN_FILE", "").strip()
    if not token_path:
        return None
    try:
        token = Path(token_path).read_bytes().strip()
    except OSError:
        return None
    return token or None


@app.middleware("http")
async def authenticate_document_requests(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    """Authenticate generation requests before FastAPI parses invoice bodies."""
    if request.url.path.startswith("/v1/zugferd/"):
        expected_token = _configured_token()
        if expected_token is None:
            return JSONResponse(status_code=503, content={"detail": "Service authentication is unconfigured"})

        scheme, separator, credential = request.headers.get("Authorization", "").partition(" ")
        credential_matches = secrets.compare_digest(credential.encode("utf-8"), expected_token)
        if separator != " " or scheme != "Bearer" or not credential_matches:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )
    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return only the invoice object ID and invalid field names."""
    del request
    body = exc.body if isinstance(exc.body, dict) else {}
    snapshot = body.get("snapshot", {}) if isinstance(body, dict) else {}
    supplied_object_id = snapshot.get("object_id") if isinstance(snapshot, dict) else None
    object_id = supplied_object_id if isinstance(supplied_object_id, int) else "unknown"
    fields: set[str] = set()
    for error in exc.errors():
        nested_error = error.get("ctx", {}).get("error")
        if isinstance(nested_error, InvoiceSnapshotError):
            fields.update(nested_error.fields)
            continue
        field = ".".join(str(part) for part in error["loc"] if part not in {"body", "snapshot"})
        fields.add(field or "snapshot")
    return JSONResponse(
        status_code=422,
        content={"detail": f"Invoice {object_id} has invalid fields: {', '.join(sorted(fields))}"},
    )


@app.get("/health")
def health() -> JSONResponse:
    """Report service readiness without exposing configuration."""
    if _configured_token() is None:
        return JSONResponse(status_code=503, content={"status": "unconfigured"})
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/v1/zugferd/documents", response_model=DocumentResponse)
def create_documents(request: DocumentRequest) -> DocumentResponse | JSONResponse:
    """Generate a validated PDF/XML pair from one normalized snapshot."""
    try:
        visible_pdf = base64.b64decode(request.visible_pdf_base64, validate=True)
    except (ValueError, binascii.Error):
        return JSONResponse(
            status_code=422,
            content={
                "detail": f"Invoice {request.snapshot.object_id} has invalid fields: visible_pdf_base64"
            },
        )

    try:
        documents = generate_invoice_documents(request.snapshot, visible_pdf)
    except Exception:  # noqa: BLE001 -- sanitize every generator failure at this transport boundary.
        return JSONResponse(
            status_code=422,
            content={"detail": f"Invoice {request.snapshot.object_id} has invalid fields: document_generation"},
        )
    return DocumentResponse(
        pdf_base64=base64.b64encode(documents.pdf).decode("ascii"),
        xml_base64=base64.b64encode(documents.xml).decode("ascii"),
    )
