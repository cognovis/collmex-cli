"""Behavior tests for locating and running the bundled EN 16931 Schematron."""

from __future__ import annotations

from pathlib import Path

import pytest

from collmex_cli.zugferd import EN16931ValidatorMissingError, find_en16931_stylesheet


def test_factur_x_7_layout_resolves_the_xslt_stylesheet(tmp_path: Path) -> None:
    """factur-x 7 ships the compiled Schematron as FACTUR-X_EN16931.xslt."""
    stylesheet = tmp_path / "FACTUR-X_EN16931.xslt"
    stylesheet.write_text("<xsl:stylesheet/>", encoding="utf-8")

    assert find_en16931_stylesheet(tmp_path) == stylesheet


def test_earlier_factur_x_layout_resolves_the_xsl_stylesheet(tmp_path: Path) -> None:
    """factur-x releases before 7 ship the compiled Schematron as Factur-X_1.09_EN16931.xsl."""
    stylesheet = tmp_path / "Factur-X_1.09_EN16931.xsl"
    stylesheet.write_text("<xsl:stylesheet/>", encoding="utf-8")

    assert find_en16931_stylesheet(tmp_path) == stylesheet


def test_factur_x_7_stylesheet_wins_when_both_layouts_are_present(tmp_path: Path) -> None:
    """A directory holding both file names uses the current factur-x 7 stylesheet."""
    current = tmp_path / "FACTUR-X_EN16931.xslt"
    current.write_text("<xsl:stylesheet/>", encoding="utf-8")
    (tmp_path / "Factur-X_1.09_EN16931.xsl").write_text("<xsl:stylesheet/>", encoding="utf-8")

    assert find_en16931_stylesheet(tmp_path) == current


def test_missing_stylesheet_names_the_expected_paths_and_blames_no_invoice(tmp_path: Path) -> None:
    """Without a stylesheet the validator is unavailable; the invoice is not reported as invalid."""
    with pytest.raises(EN16931ValidatorMissingError) as captured:
        find_en16931_stylesheet(tmp_path)

    message = str(captured.value)
    assert str(tmp_path / "FACTUR-X_EN16931.xslt") in message
    assert str(tmp_path / "Factur-X_1.09_EN16931.xsl") in message
    assert "invalid fields" not in message
    assert not isinstance(captured.value, ValueError)
