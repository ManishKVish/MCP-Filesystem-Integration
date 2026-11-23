"""
Candidate Database / HRIS MCP Server (Secondary MCP Server)
Module: candidate_db_mcp_server.py
Exposes candidate enrichment, background verification status, interview notes,
and HR database operations over standard MCP protocol.
"""
from typing import Dict, List, Any, Optional
from fastmcp import FastMCP

# Initialize FastMCP Server for HR Database
db_mcp = FastMCP(
    name="CandidateDatabaseMCPServer",
    instructions="MCP server providing candidate enrichment, HR database queries, and interview history recording."
)

# Mock HRIS Database
CANDIDATE_HR_RECORDS: Dict[str, Dict[str, Any]] = {
    "Aarav Sharma": {
        "candidate_id": "CAND-001",
        "email": "aarav.sharma@example.com",
        "current_company": "CloudScale Systems",
        "current_ctc_lpa": 32,
        "expected_ctc_lpa": 40,
        "notice_period_days": 30,
        "background_check_status": "VERIFIED",
        "previous_interview_score": 92,
        "tags": ["top-tier", "high-retention", "cloud-architect"]
    },
    "Aditi Patel": {
        "candidate_id": "CAND-002",
        "email": "aditi.patel@example.com",
        "current_company": "DataPulse AI",
        "current_ctc_lpa": 28,
        "expected_ctc_lpa": 35,
        "notice_period_days": 15,
        "background_check_status": "VERIFIED",
        "previous_interview_score": 88,
        "tags": ["ml-expert", "fast-joiner"]
    },
    "Rohan Verma": {
        "candidate_id": "CAND-003",
        "email": "rohan.verma@example.com",
        "current_company": "FinTech Prime",
        "current_ctc_lpa": 24,
        "expected_ctc_lpa": 30,
        "notice_period_days": 45,
        "background_check_status": "VERIFIED",
        "previous_interview_score": 85,
        "tags": ["backend-core", "fintech"]
    },
    "Priya Nair": {
        "candidate_id": "CAND-004",
        "email": "priya.nair@example.com",
        "current_company": "NextGen Web",
        "current_ctc_lpa": 22,
        "expected_ctc_lpa": 28,
        "notice_period_days": 30,
        "background_check_status": "VERIFIED",
        "previous_interview_score": 90,
        "tags": ["frontend-lead", "ui-ux"]
    },
    "Vikram Malhotra": {
        "candidate_id": "CAND-005",
        "email": "vikram.malhotra@example.com",
        "current_company": "SecureNet Global",
        "current_ctc_lpa": 35,
        "expected_ctc_lpa": 45,
        "notice_period_days": 60,
        "background_check_status": "VERIFIED",
        "previous_interview_score": 94,
        "tags": ["devops-guru", "security-cleared"]
    }
}

INTERVIEW_DECISIONS_STORE: List[Dict[str, Any]] = []


@db_mcp.tool()
def get_candidate_hr_record(candidate_name: str) -> Dict[str, Any]:
    """
    Retrieves HR metadata (compensation, notice period, background check, past interview scores).
    """
    record = CANDIDATE_HR_RECORDS.get(candidate_name)
    if record:
        return {
            "status": "success",
            "found": True,
            "candidate_name": candidate_name,
            "record": record
        }
    return {
        "status": "success",
        "found": False,
        "candidate_name": candidate_name,
        "record": {
            "candidate_id": f"CAND-TEMP-{abs(hash(candidate_name)) % 1000:03d}",
            "email": f"{candidate_name.lower().replace(' ', '.')}@example.com",
            "notice_period_days": 30,
            "background_check_status": "PENDING",
            "previous_interview_score": None,
            "tags": ["new-applicant"]
        }
    }


@db_mcp.tool()
def query_candidates_by_max_notice_period(max_days: int) -> List[Dict[str, Any]]:
    """
    Queries HR database for candidates available within a maximum notice period (e.g., immediate joiners).
    """
    matches = []
    for name, rec in CANDIDATE_HR_RECORDS.items():
        if rec["notice_period_days"] <= max_days:
            matches.append({
                "candidate_name": name,
                "notice_period_days": rec["notice_period_days"],
                "current_company": rec["current_company"],
                "tags": rec["tags"]
            })
    return matches


@db_mcp.tool()
def record_interview_decision(candidate_name: str, decision: str, interviewer_notes: str) -> Dict[str, Any]:
    """
    Persists interview screening feedback and hiring decisions into the HR database.
    """
    decision_entry = {
        "candidate_name": candidate_name,
        "decision": decision,
        "notes": interviewer_notes,
        "timestamp": "2026-11-23T16:00:00Z"
    }
    INTERVIEW_DECISIONS_STORE.append(decision_entry)
    return {
        "status": "success",
        "message": f"Decision recorded for {candidate_name}",
        "decision_record": decision_entry
    }


@db_mcp.resource("db://candidates/{candidate_name}")
def get_candidate_db_resource(candidate_name: str) -> str:
    """
    MCP Resource exposing candidate database profile in JSON representation.
    """
    rec = CANDIDATE_HR_RECORDS.get(candidate_name)
    if not rec:
        return f"HR Record not found for candidate: {candidate_name}"
    import json
    return json.dumps(rec, indent=2)


if __name__ == "__main__":
    db_mcp.run()
