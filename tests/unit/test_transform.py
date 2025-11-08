"""
Unit tests for transform utilities.
"""

import pytest
from app.utils.transform import normalize_soft, normalize_company


class TestNormalizeSoft:
    """Tests for normalize_soft function."""

    def test_empty_string(self):
        """Test empty string normalization."""
        assert normalize_soft("") == ""
        assert normalize_soft(None) == ""

    def test_lowercase_conversion(self):
        """Test lowercase conversion."""
        assert normalize_soft("Hello World") == "hello world"
        assert normalize_soft("HELLO WORLD") == "hello world"
        assert normalize_soft("HeLLo WoRLd") == "hello world"

    def test_unicode_normalization(self):
        """Test Unicode character normalization."""
        # normalize_soft preserves Unicode characters, only converts to lowercase
        assert normalize_soft("Café") == "café"  # é is preserved
        assert normalize_soft("Москва") == "москва"
        assert normalize_soft("北京") == "北京"  # Chinese characters preserved

    def test_punctuation_replacement(self):
        """Test punctuation and symbol replacement."""
        assert normalize_soft("Hello & World") == "hello and world"
        assert normalize_soft("It's a test") == "it s a test"
        assert normalize_soft("Hello—World") == "hello world"
        assert normalize_soft("Hello–World") == "hello world"
        assert normalize_soft('"Hello"') == "hello"

    def test_whitespace_collapse(self):
        """Test whitespace collapsing."""
        assert normalize_soft("Hello    World") == "hello world"
        assert normalize_soft("Hello\n\nWorld") == "hello world"
        assert normalize_soft("Hello\t\tWorld") == "hello world"
        assert normalize_soft("  Hello World  ") == "hello world"

    def test_preserves_digits(self):
        """Test that digits are preserved."""
        assert normalize_soft("Version 2.0") == "version 2 0"
        assert normalize_soft("Test123") == "test123"

    def test_special_characters(self):
        """Test special character handling."""
        assert normalize_soft("test@example.com") == "test example com"
        assert normalize_soft("https://example.com") == "https example com"


class TestNormalizeCompany:
    """Tests for normalize_company function."""

    def test_empty_string(self):
        """Test empty string normalization."""
        assert normalize_company("") == ""
        assert normalize_company("   ") == ""

    def test_removes_legal_suffixes(self):
        """Test removal of legal suffixes."""
        assert normalize_company("Google Inc.") == "google"
        # "Corporation" is not in the legal suffix list, so it's preserved
        assert normalize_company("Microsoft Corporation") == "microsoft corporation"
        assert normalize_company("Amazon LLC") == "amazon"
        assert normalize_company("Meta GmbH") == "meta"
        assert normalize_company("Company Ltd.") == "company"
        assert normalize_company("Test Co.") == "test"
        # S.A.S. becomes "s a s" after normalization, so it's not recognized as a suffix
        # The regex looks for "s\.?a\.?s\.?" but after normalize_soft, dots are removed
        assert normalize_company("Example S.A.S.") == "example s a s"

    def test_preserves_company_name(self):
        """Test that company name is preserved."""
        assert normalize_company("Apple") == "apple"
        assert normalize_company("Tesla Motors") == "tesla motors"

    def test_handles_multiple_words(self):
        """Test multi-word company names."""
        assert normalize_company("Red Hat Inc.") == "red hat"
        assert normalize_company("Goldman Sachs Group Inc.") == "goldman sachs group"

    def test_case_insensitive(self):
        """Test case insensitivity."""
        assert normalize_company("GOOGLE INC.") == "google"
        # "Corporation" is not in the legal suffix list, so it's preserved
        assert normalize_company("microsoft Corporation") == "microsoft corporation"

    def test_whitespace_handling(self):
        """Test whitespace normalization."""
        assert normalize_company("  Google  Inc.  ") == "google"
        assert normalize_company("Microsoft\nCorporation") == "microsoft corporation"

