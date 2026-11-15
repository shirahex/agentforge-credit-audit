"""Demo applicant files used by the interface and the tests."""
from app.schemas import LoanApplication

REFUSED = LoanApplication(
    applicant_id="DEMO-REFUSED",
    duration_months=30,
    credit_amount=5000,
    age=30,
    sex="female",
    purpose="car",
    housing="rent",
    employment_years=3,
    savings="low",
    checking_status="none",
)

APPROVED = LoanApplication(
    applicant_id="DEMO-APPROVED",
    duration_months=12,
    credit_amount=2000,
    age=45,
    sex="male",
    purpose="furniture",
    housing="own",
    employment_years=12,
    savings="high",
    checking_status="high",
)

BORDERLINE = LoanApplication(
    applicant_id="DEMO-BORDERLINE",
    duration_months=24,
    credit_amount=4200,
    age=33,
    sex="male",
    purpose="education",
    housing="rent",
    employment_years=3,
    savings="low",
    checking_status="none",
)

SAMPLES = [REFUSED, APPROVED, BORDERLINE]
