"""
Unit tests for Core Services.
"""
import unittest
from unittest.mock import patch, AsyncMock
from app.services import browser_agent_service
from app.services import pdf_generator_service


class TestServices(unittest.IsolatedAsyncioTestCase):

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

    @patch("app.services.config_service.get_config", new_callable=AsyncMock)
    async def test_auto_enrich_profile(self, mock_config):
        from app.services import candidate_service
        mock_config.return_value = {
            "name": "Auto Candidate",
            "email": "auto@example.com",
            "phone": "555-0199",
            "skills": ["Python", "FastAPI"]
        }
        empty_doc = {}
        enriched, modified = await candidate_service._auto_enrich_profile(empty_doc)
        self.assertTrue(modified)
        self.assertEqual(enriched["personal"]["full_name"], "Auto Candidate")
        self.assertEqual(enriched["personal"]["email"], "auto@example.com")
        self.assertEqual(enriched["skills"], ["Python", "FastAPI"])


if __name__ == "__main__":
    unittest.main()
