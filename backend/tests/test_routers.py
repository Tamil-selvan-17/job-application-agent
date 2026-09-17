"""
Unit tests for FastAPI routers using mocked services.
"""
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestRouters(unittest.TestCase):

    def test_health_check(self):
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "ok")

    @patch("app.services.candidate_service.get_profile", new_callable=AsyncMock)
    def test_get_candidate_profile(self, mock_get):
        mock_get.return_value = {
            "personal": {"full_name": "John Tester", "email": "tester@example.com"},
            "skills": ["Python", "FastAPI"]
        }
        response = client.get("/api/candidate")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("personal", {}).get("full_name"), "John Tester")

    @patch("app.services.candidate_service.save_profile", new_callable=AsyncMock)
    def test_save_candidate_profile(self, mock_save):
        mock_save.return_value = {
            "personal": {"full_name": "Jane Tester", "email": "jane@example.com"},
            "skills": ["Python", "Selenium"]
        }
        payload = {
            "personal": {"full_name": "Jane Tester", "email": "jane@example.com"},
            "skills": ["Python", "Selenium"]
        }
        response = client.put("/api/candidate", json=payload)
        self.assertEqual(response.status_code, 200)

    @patch("app.services.agent_orchestrator_service.run_jd_analysis", new_callable=AsyncMock)
    def test_analyze_jd_endpoint(self, mock_workflow):
        mock_workflow.return_value = {
            "job_id": "job_101",
            "workflow_state": "JD_ANALYZED",
            "jd_analysis": {"required_skills": ["Python"]}
        }
        response = client.post("/api/jobs/job_101/analyze-jd")
        self.assertEqual(response.status_code, 200)

    @patch("app.services.contact_finder_service.discover_and_store_contacts", new_callable=AsyncMock)
    def test_find_contacts_endpoint(self, mock_contacts):
        mock_contacts.return_value = [
            {"name": "HR Recruiter", "email": "hr@company.com", "role": "Recruiter"}
        ]
        response = client.post("/api/jobs/job_101/find-contacts")
        self.assertEqual(response.status_code, 200)

    @patch("app.services.agent_orchestrator_service.run_resume_pipeline", new_callable=AsyncMock)
    def test_customize_resume_endpoint(self, mock_resume_wf):
        mock_resume_wf.return_value = {
            "job_id": "job_101",
            "ats_score": 92,
            "workflow_state": "PDF_CONVERTED"
        }
        response = client.post("/api/jobs/job_101/customize-resume")
        self.assertEqual(response.status_code, 200)

    @patch("app.services.application_tracker_service.get_dashboard_stats", new_callable=AsyncMock)
    def test_application_stats_endpoint(self, mock_stats):
        mock_stats.return_value = {
            "total_applied": 15,
            "email_sent": 10,
            "website_applied": 5
        }
        response = client.get("/api/applications/stats")
        self.assertEqual(response.status_code, 200)

    @patch("app.services.agent_orchestrator_service.run_email_application", new_callable=AsyncMock)
    def test_apply_email_personalized_endpoint(self, mock_email_app):
        mock_email_app.return_value = {"sent": True, "recipient": "hr@test.com"}
        payload = {"hr_email": "hr@test.com"}
        response = client.post("/api/jobs/job_101/apply-email-personalized", json=payload)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
