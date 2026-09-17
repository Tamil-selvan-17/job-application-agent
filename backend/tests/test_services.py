"""
Unit tests for Core Services (ATS calculation, Contact Finder, Resume Customizer, Browser Agent logic).
"""
import unittest
from unittest.mock import MagicMock, patch
import os

from app.services import resume_customizer_service
from app.services import contact_finder_service
from app.services import browser_agent_service


class TestServices(unittest.TestCase):

    def test_ats_score_calculation(self):
        candidate_skills = ["Python", "FastAPI", "MongoDB", "Docker", "Git"]
        jd_analysis = {
            "required_skills": ["Python", "FastAPI", "MongoDB", "Docker", "Kubernetes"],
            "nice_to_have_skills": ["Git", "AWS"],
            "title": "Backend Developer",
            "experience_level": "Senior"
        }
        
        score, detailed = resume_customizer_service._calculate_ats_score(candidate_skills, jd_analysis)
        self.assertGreaterEqual(score, 60)
        self.assertLessEqual(score, 100)
        self.assertIn("matched_skills", detailed)
        self.assertIn("missing_skills", detailed)
        self.assertIn("Python", detailed["matched_skills"])

    def test_contact_finder_heuristics(self):
        html_content = """
        <html>
            <body>
                <p>Contact our recruiter at recruiter@acme.com or hr.team@acme.com for careers.</p>
                <a href="mailto:careers@acme.com">Join Us</a>
            </body>
        </html>
        """
        contacts = contact_finder_service._extract_contacts_from_html(html_content, "acme.com")
        self.assertGreaterEqual(len(contacts), 2)
        emails = [c["email"] for c in contacts]
        self.assertIn("recruiter@acme.com", emails)
        self.assertIn("hr.team@acme.com", emails)

    def test_contact_finder_domain_generator(self):
        domain_contacts = contact_finder_service._generate_domain_contacts("TechCorp", "techcorp.io")
        self.assertGreaterEqual(len(domain_contacts), 3)
        emails = [c["email"] for c in domain_contacts]
        self.assertIn("hr@techcorp.io", emails)
        self.assertIn("careers@techcorp.io", emails)

    def test_browser_agent_field_classification(self):
        input_data = [
            {"type": "text", "name": "first_name", "id": "fname", "placeholder": "First Name"},
            {"type": "email", "name": "email_address", "id": "email", "placeholder": "Enter email"},
            {"type": "file", "name": "resume", "id": "resume_file", "placeholder": "Upload resume"}
        ]
        
        classified = browser_agent_service.GenericAdapter._classify_fields(input_data)
        self.assertEqual(len(classified), 3)
        field_types = [c["classified_type"] for c in classified]
        self.assertIn("first_name", field_types)
        self.assertIn("email", field_types)
        self.assertIn("resume", field_types)


if __name__ == "__main__":
    unittest.main()
