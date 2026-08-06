"""Behavior tests for normalized outgoing invoice snapshots."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import get_type_hints

import pikepdf
import pytest
from facturx import xml_check_schematron, xml_check_xsd
from fastapi import Request
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from collmex_cli.invoice_snapshot import InvoiceSnapshot, InvoiceSnapshotError, validate_invoice_snapshot
from collmex_cli.zugferd import generate_invoice_documents
from collmex_cli.zugferd_service import app, authenticate_document_requests


@pytest.fixture
def configured_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, dict[str, str]]:
    token_file = tmp_path / "zugferd-token"
    token_file.write_text("synthetic-test-value\n", encoding="utf-8")
    monkeypatch.setenv("ZUGFERD_AUTH_TOKEN_FILE", str(token_file))
    return TestClient(app), {"Authorization": "Bearer synthetic-test-value"}


def test_authentication_middleware_has_a_complete_public_signature() -> None:
    """The ASGI middleware boundary exposes request, continuation, and response types."""
    annotations = get_type_hints(authenticate_document_requests)

    assert annotations == {
        "request": Request,
        "call_next": RequestResponseEndpoint,
        "return": Response,
    }


def _visible_pdf() -> bytes:
    output = BytesIO()
    document = canvas.Canvas(output, pagesize=(595, 842), invariant=1)
    for text in ("Existing invoice header", "Existing invoice detail page"):
        document.drawString(72, 770, text)
        document.showPage()
    document.save()
    return output.getvalue()


def _snapshot(*, document_kind: str = "invoice") -> dict[str, object]:
    return {
        "object_id": 84001,
        "document_kind": document_kind,
        "document_number": "K-2026-0042",
        "issue_date": "2026-08-06",
        "delivery_date": "2026-08-05",
        "currency": "EUR",
        "seller": {
            "object_id": 10,
            "name": "Example Seller GmbH",
            "street": "Seller Street 1",
            "postal_code": "20095",
            "city": "Hamburg",
            "country_code": "DE",
            "vat_id": "DE123456789",
        },
        "buyer": {
            "object_id": 20,
            "name": "Example Buyer GmbH",
            "street": "Buyer Street 2",
            "postal_code": "10115",
            "city": "Berlin",
            "country_code": "DE",
            "vat_id": "DE987654321",
        },
        "lines": [
            {
                "object_id": 84002,
                "description": "Translation service",
                "quantity": "2.00",
                "unit_code": "HUR",
                "unit_price": "100.00",
                "tax_rate": "19.00",
                "line_total": "200.00",
            },
            {
                "object_id": 84003,
                "description": "Printed material",
                "quantity": "1.00",
                "unit_code": "C62",
                "unit_price": "50.00",
                "tax_rate": "7.00",
                "line_total": "50.00",
            },
        ],
        "taxes": [
            {"rate": "19.00", "basis_amount": "200.00", "tax_amount": "38.00"},
            {"rate": "7.00", "basis_amount": "50.00", "tax_amount": "3.50"},
        ],
        "totals": {
            "line_total": "250.00",
            "tax_basis_total": "250.00",
            "tax_total": "41.50",
            "grand_total": "291.50",
            "due_amount": "291.50",
        },
        "payment_terms": "Payable within 14 days.",
        "due_date": "2026-08-20",
        "payment_means_type_code": "58",
        "payee_iban": "DE02120300000000202051",
        "payee_bic": "BYLADEM1001",
    }


def _embedded_xml(pdf_bytes: bytes) -> bytes:
    attachment = PdfReader(BytesIO(pdf_bytes)).attachments["factur-x.xml"]
    return attachment[0] if isinstance(attachment, list) else attachment


def _visible_page_content(pdf_bytes: bytes) -> list[bytes]:
    return [page.get_contents().get_data() for page in PdfReader(BytesIO(pdf_bytes)).pages]


def _zero_rate_snapshot(category_code: str) -> dict[str, object]:
    snapshot = _snapshot()
    snapshot["lines"] = [
        {
            "object_id": 84002,
            "description": "Translation service",
            "quantity": "2.00",
            "unit_code": "HUR",
            "unit_price": "100.00",
            "tax_rate": "0.00",
            "line_total": "200.00",
            "tax_category_code": category_code,
        }
    ]
    snapshot["taxes"] = [
        {
            "rate": "0.00",
            "basis_amount": "200.00",
            "tax_amount": "0.00",
            "category_code": category_code,
        }
    ]
    snapshot["totals"] = {
        "line_total": "200.00",
        "tax_basis_total": "200.00",
        "tax_total": "0.00",
        "grand_total": "200.00",
        "due_amount": "200.00",
    }
    return snapshot


def _aggregate_rounding_snapshot() -> dict[str, object]:
    snapshot = _snapshot()
    snapshot["lines"] = [
        {
            "object_id": 84002 + index,
            "description": f"Small taxable service {index + 1}",
            "quantity": "1.00",
            "unit_code": "C62",
            "unit_price": "0.03",
            "tax_rate": "19.00",
            "line_total": "0.03",
            "tax_category_code": "S",
        }
        for index in range(2)
    ]
    snapshot["taxes"] = [
        {
            "rate": "19.00",
            "basis_amount": "0.06",
            "tax_amount": "0.01",
            "category_code": "S",
        }
    ]
    snapshot["totals"] = {
        "line_total": "0.06",
        "tax_basis_total": "0.06",
        "tax_total": "0.01",
        "grand_total": "0.07",
        "due_amount": "0.07",
    }
    return snapshot


def test_invoice_snapshot_generates_valid_coherent_document_pair() -> None:
    """One normalized snapshot yields EN 16931 XML and a byte-identical hybrid PDF attachment."""
    original_pdf = _visible_pdf()

    documents = generate_invoice_documents(InvoiceSnapshot.model_validate(_snapshot()), original_pdf)

    assert xml_check_xsd(documents.xml, flavor="factur-x", level="en16931") is True
    assert xml_check_schematron(documents.xml, flavor="factur-x", level="en16931") is True
    assert _embedded_xml(documents.pdf) == documents.xml
    assert len(PdfReader(BytesIO(documents.pdf)).pages) == len(PdfReader(BytesIO(original_pdf)).pages)
    assert _visible_page_content(documents.pdf) == _visible_page_content(original_pdf)
    with pikepdf.open(BytesIO(documents.pdf)) as pdf:
        embedded = pdf.Root["/Names"]["/EmbeddedFiles"]["/Names"][1]
        assert embedded["/AFRelationship"] == pikepdf.Name("/Alternative")
        with pdf.open_metadata() as metadata:
            assert metadata["pdfaid:part"] == "3"
            assert metadata["pdfaid:conformance"] == "B"


@pytest.mark.parametrize(
    ("document_kind", "type_code"),
    [("invoice", "380"), ("credit_note", "381")],
)
def test_document_kind_uses_the_matching_en16931_type_code(document_kind: str, type_code: str) -> None:
    """Invoice corrections use 380 while cancellation credit notes use 381."""
    documents = generate_invoice_documents(
        InvoiceSnapshot.model_validate(_snapshot(document_kind=document_kind)),
        _visible_pdf(),
    )

    assert f"<ram:TypeCode>{type_code}</ram:TypeCode>".encode() in documents.xml
    assert xml_check_schematron(documents.xml, flavor="factur-x", level="en16931") is True


@pytest.mark.parametrize("category_code", ["Z", "AE", "G"])
def test_zero_rate_tax_categories_keep_their_en16931_semantics(category_code: str) -> None:
    """Zero rate, reverse charge, and export invoices cannot be conflated."""
    documents = generate_invoice_documents(
        InvoiceSnapshot.model_validate(_zero_rate_snapshot(category_code)),
        _visible_pdf(),
    )

    assert f"<ram:CategoryCode>{category_code}</ram:CategoryCode>".encode() in documents.xml
    assert xml_check_schematron(documents.xml, flavor="factur-x", level="en16931") is True


def test_tax_breakdown_rounds_the_aggregate_basis() -> None:
    """Two three-cent lines produce one cent VAT, matching the visible fixed-rate invoice."""
    documents = generate_invoice_documents(
        InvoiceSnapshot.model_validate(_aggregate_rounding_snapshot()),
        _visible_pdf(),
    )

    assert b"<ram:BasisAmount>0.06</ram:BasisAmount>" in documents.xml
    assert b"<ram:CalculatedAmount>0.01</ram:CalculatedAmount>" in documents.xml
    assert xml_check_schematron(documents.xml, flavor="factur-x", level="en16931") is True


@pytest.mark.parametrize("payment_code", ["10", "20"])
def test_non_transfer_payment_methods_do_not_require_bank_details(payment_code: str) -> None:
    """Cash and cheque invoices carry their actual code without invented bank data."""
    payload = _snapshot()
    payload["payment_means_type_code"] = payment_code
    payload["payee_iban"] = None
    payload["payee_bic"] = None

    documents = generate_invoice_documents(InvoiceSnapshot.model_validate(payload), _visible_pdf())

    assert f"<ram:TypeCode>{payment_code}</ram:TypeCode>".encode() in documents.xml
    assert xml_check_schematron(documents.xml, flavor="factur-x", level="en16931") is True


def test_transfer_payment_requires_iban_and_bic() -> None:
    """A transfer cannot silently omit its payee account details."""
    payload = _snapshot()
    payload["payee_iban"] = None
    payload["payee_bic"] = None

    with pytest.raises(InvoiceSnapshotError) as captured:
        validate_invoice_snapshot(payload)

    assert captured.value.fields == ["payee_bic", "payee_iban"]


def test_inconsistent_totals_fail_with_object_id_and_field_names_only() -> None:
    """A mismatched snapshot fails closed without exposing party, payment, or address values."""
    payload = _snapshot()
    totals = dict(payload["totals"])
    totals["grand_total"] = "999.00"
    payload["totals"] = totals

    try:
        validate_invoice_snapshot(payload)
    except InvoiceSnapshotError as exc:
        diagnostic = str(exc)
    else:
        raise AssertionError("Expected InvoiceSnapshotError")

    assert "84001" in diagnostic
    assert "totals.grand_total" in diagnostic
    assert "Example Buyer" not in diagnostic
    assert "Buyer Street" not in diagnostic
    assert "DE021203" not in diagnostic

def test_service_health_and_documents_fail_closed_without_token_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured process is not ready and cannot parse invoice payloads."""
    monkeypatch.delenv("ZUGFERD_AUTH_TOKEN_FILE", raising=False)
    client = TestClient(app)
    payload = _snapshot()
    payload["buyer"] = {**dict(payload["buyer"]), "name": "Sensitive Buyer"}

    health_response = client.get("/health")
    document_response = client.post(
        "/v1/zugferd/documents",
        json={"snapshot": payload, "visible_pdf_base64": "Sensitive payload"},
    )

    assert health_response.status_code == 503
    assert health_response.json() == {"status": "unconfigured"}
    assert document_response.status_code == 503
    assert "Sensitive" not in document_response.text


def test_service_rejects_empty_token_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty configured secret is treated as missing configuration."""
    token_file = tmp_path / "zugferd-token"
    token_file.write_text("\n", encoding="utf-8")
    monkeypatch.setenv("ZUGFERD_AUTH_TOKEN_FILE", str(token_file))
    client = TestClient(app)

    assert client.get("/health").status_code == 503
    assert client.post("/v1/zugferd/documents", json={}).status_code == 503


def test_service_rejects_missing_and_invalid_bearer_credentials(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """Only the configured Bearer credential can reach document validation."""
    client, _ = configured_service
    payload = {"snapshot": _snapshot(), "visible_pdf_base64": "Sensitive payload"}

    missing_response = client.post("/v1/zugferd/documents", json=payload)
    invalid_response = client.post(
        "/v1/zugferd/documents",
        headers={"Authorization": "Bearer invalid-test-value"},
        json=payload,
    )

    assert missing_response.status_code == 401
    assert invalid_response.status_code == 401
    assert missing_response.json() == invalid_response.json()
    assert "Sensitive" not in missing_response.text


def test_service_returns_generated_document_pair(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """An authenticated valid request receives a coherent PDF/XML pair."""
    client, headers = configured_service
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={
            "snapshot": _snapshot(),
            "visible_pdf_base64": base64.b64encode(_visible_pdf()).decode("ascii"),
        },
    )

    assert response.status_code == 200
    response_body = response.json()
    pdf = base64.b64decode(response_body["pdf_base64"], validate=True)
    xml = base64.b64decode(response_body["xml_base64"], validate=True)
    assert _embedded_xml(pdf) == xml


def test_service_sanitizes_snapshot_validation_errors(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """Authenticated validation errors contain only object IDs and field names."""
    client, headers = configured_service
    invalid = _snapshot()
    invalid["buyer"] = {**dict(invalid["buyer"]), "street": ""}
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={
            "snapshot": invalid,
            "visible_pdf_base64": base64.b64encode(_visible_pdf()).decode("ascii"),
        },
    )

    assert response.status_code == 422
    diagnostic = response.text
    assert "84001" in diagnostic
    assert "buyer.street" in diagnostic
    assert "Example Buyer" not in diagnostic
    assert "Buyer Street" not in diagnostic
    assert "DE021203" not in diagnostic


def test_service_reports_inconsistent_totals_by_field(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """Cross-field validation keeps its field-level diagnostic through HTTP."""
    client, headers = configured_service
    invalid_totals = _snapshot()
    invalid_totals["totals"] = {**dict(invalid_totals["totals"]), "grand_total": "999.00"}
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={
            "snapshot": invalid_totals,
            "visible_pdf_base64": base64.b64encode(_visible_pdf()).decode("ascii"),
        },
    )

    assert response.status_code == 422
    assert "totals.grand_total" in response.text


def test_service_rejects_malformed_base64_without_reflection(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """Malformed transport data is rejected without reflecting the supplied bytes."""
    client, headers = configured_service
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={"snapshot": _snapshot(), "visible_pdf_base64": "Sensitive payload"},
    )

    assert response.status_code == 422
    assert "visible_pdf_base64" in response.text
    assert "Sensitive" not in response.text


def test_service_redacts_generator_failures(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """Generator failures never expose decoded PDF contents or invoice values."""
    client, headers = configured_service
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={
            "snapshot": _snapshot(),
            "visible_pdf_base64": base64.b64encode(b"Sensitive invalid PDF").decode("ascii"),
        },
    )

    assert response.status_code == 422
    assert "document_generation" in response.text
    assert "Sensitive" not in response.text


def test_service_redacts_invalid_object_identifier(
    configured_service: tuple[TestClient, dict[str, str]],
) -> None:
    """An invalid raw identifier cannot become part of a validation response."""
    client, headers = configured_service
    invalid_object_id = _snapshot()
    invalid_object_id["object_id"] = "Sensitive Buyer"
    response = client.post(
        "/v1/zugferd/documents",
        headers=headers,
        json={
            "snapshot": invalid_object_id,
            "visible_pdf_base64": base64.b64encode(_visible_pdf()).decode("ascii"),
        },
    )

    assert response.status_code == 422
    assert "Sensitive Buyer" not in response.text
