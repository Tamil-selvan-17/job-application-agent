"""
Unit tests for Interview Prep, Skills Gap, and Batch Resume services & endpoints.
"""
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestAgentEnhancements(unittest.TestCase):

    @patch("app.services.interview_prep_service.generate_interview_prep", new_callable=AsyncMock)
    def test_interview_prep_endpoint(self, mock_prep):
        mock_prep.return_value = {
            "job_id": "job_123",
            "job_title": ".NET Developer",
            "company": "Tech Corp",
            "summary": "Prep package ready.",
            "questions": [
                {
                    "category": "Behavioral STAR",
                    "question": "Tell me about a backend project.",
                    "why_asked": "Testing experience",
                    "star_answer": {
                        "situation": "Building API",
                        "task": "Optimize queries",
                        "action": "Added indexes",
                        "result": "50% faster"
                    },
                    "pro_tip": "Focus on metrics"
                }
            ]
        }
        response = client.post("/api/jobs/job_123/interview-prep")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("job_id"), "job_123")
        self.assertEqual(len(data.get("questions", [])), 1)

    @patch("app.services.skills_gap_service.analyze_skills_gap", new_callable=AsyncMock)
    def test_skills_gap_endpoint(self, mock_gap):
        mock_gap.return_value = {
            "job_id": "job_123",
            "match_percentage": 85,
            "matching_skills": ["C#", "SQL"],
            "missing_skills": ["AWS"],
            "resume_bullet_suggestions": ["Designed scalable services."]
        }
        response = client.post("/api/jobs/job_123/skills-gap")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("match_percentage"), 85)

    @patch("app.services.agent_orchestrator_service.run_batch_resume_generation", new_callable=AsyncMock)
    def test_batch_generate_resumes_endpoint(self, mock_batch):
        mock_batch.return_value = {
            "processed": 2,
            "successful": 2,
            "details": [{"job_id": "job_1", "status": "success"}]
        }
        response = client.post("/api/jobs/batch-generate-resumes")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("processed"), 2)


if __name__ == "__main__":
    unittest.main()
