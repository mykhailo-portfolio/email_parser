"""
Input validation utilities.
"""

from __future__ import annotations
from typing import List, Dict, Any
from app.logging import logger


def validate_email_brief(email: Dict[str, Any]) -> bool:
    """
    Validate email brief structure.

    Args:
        email: Email brief dictionary

    Returns:
        True if valid, False otherwise
    """
    required_fields = ["id", "from", "subject", "text_full", "head", "internalDate"]
    
    if not isinstance(email, dict):
        logger.warning(f"Email brief is not a dictionary: {type(email)}")
        return False
    
    for field in required_fields:
        if field not in email:
            logger.warning(f"Email brief missing required field: {field}")
            return False
    
    if not isinstance(email["id"], str) or not email["id"]:
        logger.warning(f"Invalid email ID: {email.get('id')}")
        return False
    
    return True


def validate_company_name(company: str) -> bool:
    """
    Validate company name.

    Args:
        company: Company name string

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(company, str):
        logger.warning(f"Company name is not a string: {type(company)}")
        return False
    
    company_trimmed = company.strip()
    if not company_trimmed:
        logger.warning("Company name is empty")
        return False
    
    if len(company_trimmed) > 200:
        logger.warning(f"Company name too long: {len(company_trimmed)} characters")
        return False
    
    return True


def validate_message_ids(ids: List[str]) -> bool:
    """
    Validate list of Gmail message IDs.

    Args:
        ids: List of message ID strings

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(ids, list):
        logger.warning(f"Message IDs is not a list: {type(ids)}")
        return False
    
    if len(ids) == 0:
        return True  # Empty list is valid
    
    for msg_id in ids:
        if not isinstance(msg_id, str) or not msg_id.strip():
            logger.warning(f"Invalid message ID: {msg_id}")
            return False
    
    return True


def validate_sheet_id(sheet_id: str) -> bool:
    """
    Validate Google Sheet ID.

    Args:
        sheet_id: Google Sheet ID string

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(sheet_id, str):
        logger.warning(f"Sheet ID is not a string: {type(sheet_id)}")
        return False
    
    sheet_id_trimmed = sheet_id.strip()
    if not sheet_id_trimmed:
        logger.warning("Sheet ID is empty")
        return False
    
    # Google Sheet IDs are typically 44 characters long
    if len(sheet_id_trimmed) < 20 or len(sheet_id_trimmed) > 100:
        logger.warning(f"Sheet ID length seems invalid: {len(sheet_id_trimmed)} characters")
        return False
    
    return True


def validate_row_number(row: int, min_row: int = 1) -> bool:
    """
    Validate row number for Google Sheets.

    Args:
        row: Row number (1-based)
        min_row: Minimum valid row number (default: 1)

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(row, int):
        logger.warning(f"Row number is not an integer: {type(row)}")
        return False
    
    if row < min_row:
        logger.warning(f"Row number {row} is less than minimum {min_row}")
        return False
    
    if row > 1000000:  # Reasonable upper limit for Google Sheets
        logger.warning(f"Row number {row} exceeds maximum")
        return False
    
    return True

