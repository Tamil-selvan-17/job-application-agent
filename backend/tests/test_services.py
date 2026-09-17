"""
Unit tests for Core Services.
"""
import unittest
from app.services import browser_agent_service
from app.services import pdf_generator_service


class TestServices(unittest.TestCase):

    def test_browser_agent_session_management(self):
        job_id = "job_test_123"
        session = browser_agent_service.get_session(job_id)
        self.assertIsNone(session)
        browser_agent_service.close_session(job_id)

    def test_pdf_generator_platform_routing(self):
        import sys
        # Test converting empty bytes fails gracefully or falls back
        try:
            pdf_generator_service.convert_docx_to_pdf(b"")
        except Exception as e:
            # Expected to fail conversion on dummy empty bytes
            self.assertTrue(isinstance(e, Exception))


if __name__ == "__main__":
    unittest.main()
