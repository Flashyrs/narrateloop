import os
import sys
import unittest
from unittest.mock import MagicMock
from fastapi import HTTPException

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.main import validate_date_str, validate_story_index, safe_path_join, mask_sensitive_log_data
from telegram_bot import is_authorized as bot_is_authorized

class TestSecurityControls(unittest.TestCase):

    def test_path_traversal_validation(self):
        # Valid date
        self.assertEqual(validate_date_str("20260916"), "20260916")
        
        # Path traversal / invalid date formats
        with self.assertRaises(HTTPException):
            validate_date_str("../../2026")
        with self.assertRaises(HTTPException):
            validate_date_str("2026-09-16")
        with self.assertRaises(HTTPException):
            validate_date_str("invalid_date")

    def test_story_index_validation(self):
        self.assertEqual(validate_story_index(1), 1)
        self.assertEqual(validate_story_index(3), 3)
        with self.assertRaises(HTTPException):
            validate_story_index(0)
        with self.assertRaises(HTTPException):
            validate_story_index(-5)
        with self.assertRaises(HTTPException):
            validate_story_index(999)

    def test_safe_path_containment(self):
        base_dir = os.path.join(PROJECT_ROOT, "output")
        safe_path = safe_path_join(base_dir, "20260916", "final_1.mp4")
        self.assertTrue(safe_path.startswith(os.path.abspath(base_dir)))
        
        # Attempt traversal outside base
        with self.assertRaises(HTTPException):
            safe_path_join(base_dir, "..", "..", "windows", "win.ini")

    def test_log_token_masking(self):
        raw_log = "Error connecting to bot123456789:ABCdefGHIJklmnoPQRstuvWXyz_12345 with key=AIzaSyD_SecretKey12345"
        masked = mask_sensitive_log_data(raw_log)
        self.assertNotIn("123456789:ABCdefGHIJklmnoPQRstuvWXyz_12345", masked)
        self.assertNotIn("AIzaSyD_SecretKey12345", masked)
        self.assertIn("[REDACTED", masked)

    def test_telegram_auth_verification(self):
        os.environ["TELEGRAM_CHAT_ID"] = "12345678"
        
        # Authorized update mock
        valid_update = MagicMock()
        valid_update.effective_chat.id = 12345678
        valid_update.effective_user.id = 12345678
        self.assertTrue(bot_is_authorized(valid_update))
        
        # Unauthorized update mock
        unauth_update = MagicMock()
        unauth_update.effective_chat.id = 99999999
        unauth_update.effective_user.id = 99999999
        self.assertFalse(bot_is_authorized(unauth_update))


if __name__ == "__main__":
    unittest.main()
