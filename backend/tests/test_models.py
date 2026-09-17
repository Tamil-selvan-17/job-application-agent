"""
Unit tests for Pydantic Models and Data Structures.
"""
import unittest
from app.models.candidate_model import (
    CandidateProfile,
    PersonalInfo,
    CareerInfo,
    ExperienceEntry,
    Education,
    ProjectEntry,
    Certification
)
from app.models.application_model import ApplicationRecord, ApplicationMethod, ApplicationStatus
from app.models.job_model import WorkflowState


class TestModels(unittest.TestCase):

    def test_candidate_profile_defaults(self):
        profile = CandidateProfile(
            personal=PersonalInfo(
                full_name="John Doe",
                email="john@example.com",
                phone="1234567890",
                location="New York"
            ),
            skills=["Python", "FastAPI"]
        )
        self.assertEqual(profile.personal.full_name, "John Doe")
        self.assertEqual(profile.personal.email, "john@example.com")
        self.assertEqual(len(profile.skills), 2)
        self.assertEqual(profile.experience, [])

    def test_candidate_profile_full(self):
        exp = ExperienceEntry(
            company="Tech Corp",
            title="Senior Engineer",
            start_date="2020",
            end_date="Present",
            responsibilities=["Led backend architecture."]
        )
        edu = Education(degree="BS CS", institution="MIT", start_year="2015", end_year="2019")
        proj = ProjectEntry(name="AI Agent", description="Job agent", technologies=["Python"])
        cert = Certification(name="AWS Certified Developer", issuer="AWS", date="2022")

        profile = CandidateProfile(
            personal=PersonalInfo(full_name="Jane Smith", email="jane@example.com"),
            career=CareerInfo(current_title="Lead Architect", total_experience="5 years"),
            skills=["Python", "AWS", "Docker"],
            experience=[exp],
            education=[edu],
            projects=[proj],
            certifications=[cert]
        )
        self.assertEqual(len(profile.experience), 1)
        self.assertEqual(profile.experience[0].company, "Tech Corp")
        self.assertEqual(len(profile.education), 1)
        self.assertEqual(len(profile.projects), 1)
        self.assertEqual(len(profile.certifications), 1)

    def test_application_record(self):
        app = ApplicationRecord(
            job_id="job_123",
            company="Acme Inc",
            job_title="Full Stack Developer",
            method=ApplicationMethod.EMAIL,
            status=ApplicationStatus.SENT,
            recipient_email="hr@acme.com"
        )
        self.assertEqual(app.job_id, "job_123")
        self.assertEqual(app.method, ApplicationMethod.EMAIL)
        self.assertEqual(app.status, ApplicationStatus.SENT)

    def test_workflow_state_enum(self):
        self.assertEqual(WorkflowState.JOB_CREATED.value, "JOB_CREATED")
        self.assertEqual(WorkflowState.JD_ANALYZED.value, "JD_ANALYZED")
        self.assertEqual(WorkflowState.RESUME_CUSTOMIZED.value, "RESUME_CUSTOMIZED")
        self.assertEqual(WorkflowState.DOCX_GENERATED.value, "DOCX_GENERATED")
        self.assertEqual(WorkflowState.PDF_CONVERTED.value, "PDF_CONVERTED")
        self.assertEqual(WorkflowState.APPLIED.value, "APPLIED")
        self.assertEqual(WorkflowState.FAILED.value, "FAILED")


if __name__ == "__main__":
    unittest.main()
