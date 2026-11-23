"""
Model Context Protocol (MCP) Powered LangGraph Matching Agent
Module: matching_agent.py
Refactored multi-round candidate screening agent that utilizes standardized MCP tool calls
across multiple servers (Filesystem MCP & Candidate DB MCP).
"""
import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, TypedDict

from langgraph.graph import StateGraph, START, END

from mcp_client_manager import MCPClientManager

logger = logging.getLogger("MCPMatchingAgent")

# -----------------------------------------------------------------------------
# 1. Agent State Definition
# -----------------------------------------------------------------------------
class MCPMatchingAgentState(TypedDict):
    conversation_history: List[Dict[str, str]]
    job_description: str
    must_have_skills: List[str]
    nice_to_have_skills: List[str]
    min_experience_years: int
    candidate_profiles: List[Dict[str, Any]]
    shortlist: List[Dict[str, Any]]
    enriched_shortlist: List[Dict[str, Any]]
    final_report: str
    feedback: str
    step_history: List[str]
    mcp_call_count: int


# -----------------------------------------------------------------------------
# 2. Agent Graph Construction
# -----------------------------------------------------------------------------
class MCPMatchingAgent:
    """
    LangGraph Agent using MCP Client Manager for standard protocol communications.
    """

    def __init__(self, resumes_dir: Optional[str] = None, enable_fallback: bool = True):
        self.mcp_client = MCPClientManager(enable_fallback=enable_fallback)
        if resumes_dir:
            self.resumes_dir = str(Path(resumes_dir).resolve())
        else:
            self.resumes_dir = str((Path(__file__).parent / "data" / "resumes").resolve())

        self.workflow = self._build_graph()

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(MCPMatchingAgentState)

        builder.add_node("parse_requirements", self._parse_requirements_node)
        builder.add_node("scan_and_read_resumes_mcp", self._scan_and_read_resumes_mcp_node)
        builder.add_node("rank_candidates", self._rank_candidates_node)
        builder.add_node("enrich_candidates_mcp", self._enrich_candidates_mcp_node)
        builder.add_node("generate_report", self._generate_report_node)

        builder.add_edge(START, "parse_requirements")
        builder.add_edge("parse_requirements", "scan_and_read_resumes_mcp")
        builder.add_edge("scan_and_read_resumes_mcp", "rank_candidates")
        builder.add_edge("rank_candidates", "enrich_candidates_mcp")
        builder.add_edge("enrich_candidates_mcp", "generate_report")
        builder.add_edge("generate_report", END)

        return builder.compile()

    # -------------------------------------------------------------------------
    # Graph Nodes
    # -------------------------------------------------------------------------
    def _parse_requirements_node(self, state: MCPMatchingAgentState) -> Dict[str, Any]:
        """Node 1: Parses Job Description into must-haves, nice-to-haves, and min experience."""
        jd = state.get("job_description", "").lower()
        must_haves = []
        nice_to_haves = []
        min_exp = 0

        # Extract Experience
        exp_m = re.search(r'(\d+)\+?\s*years?', jd)
        if exp_m:
            min_exp = int(exp_m.group(1))

        # Skill catalog
        tech_catalog = [
            "python", "pytorch", "tensorflow", "docker", "kubernetes", "aws", "terraform",
            "react", "typescript", "node.js", "go", "kafka", "postgresql", "java", "spring boot",
            "sql", "ci/cd", "microservices", "redis", "celery", "graphql", "next.js"
        ]

        matched_skills = [s for s in tech_catalog if s in jd]
        if matched_skills:
            must_haves = matched_skills[:3]
            nice_to_haves = matched_skills[3:]

        step_history = state.get("step_history", []) + ["parse_requirements"]

        return {
            "must_have_skills": must_haves,
            "nice_to_have_skills": nice_to_haves,
            "min_experience_years": min_exp,
            "step_history": step_history
        }

    def _scan_and_read_resumes_mcp_node(self, state: MCPMatchingAgentState) -> Dict[str, Any]:
        """Node 2: Discovers and parses resumes via Filesystem MCP Server."""
        # 1. MCP Tool Call: list_files
        list_resp = self.mcp_client.call_tool("list_files", {
            "directory": self.resumes_dir,
            "extension": ".txt"
        })
        files = list_resp.get("result", [])

        candidate_profiles = []
        for file_info in files:
            filepath = file_info["filepath"]
            # 2. MCP Tool Call: read_file
            read_resp = self.mcp_client.call_tool("read_file", {"filepath": filepath})
            if read_resp.get("result", {}).get("status") in ("success", "degraded_fallback"):
                content = read_resp["result"]["content"]

                name_m = re.search(r'NAME:\s*([^\n\r]+)', content)
                title_m = re.search(r'TITLE:\s*([^\n\r]+)', content)
                exp_m = re.search(r'EXPERIENCE:\s*(\d+)', content)
                skills_m = re.search(r'SKILLS:\s*([^\n\r]+)', content)

                name = name_m.group(1).strip() if name_m else file_info["filename"]
                title = title_m.group(1).strip() if title_m else "Software Engineer"
                exp = int(exp_m.group(1)) if exp_m else 0
                skills = [s.strip().lower() for s in skills_m.group(1).split(",") if s.strip()] if skills_m else []

                candidate_profiles.append({
                    "name": name,
                    "title": title,
                    "experience_years": exp,
                    "skills": skills,
                    "content": content,
                    "filepath": filepath
                })

        step_history = state.get("step_history", []) + ["scan_and_read_resumes_mcp"]

        return {
            "candidate_profiles": candidate_profiles,
            "step_history": step_history
        }

    def _rank_candidates_node(self, state: MCPMatchingAgentState) -> Dict[str, Any]:
        """Node 3: Evaluates candidate fitness and produces Top-K shortlist."""
        profiles = state.get("candidate_profiles", [])
        must_haves = [s.lower() for s in state.get("must_have_skills", [])]
        nice_to_haves = [s.lower() for s in state.get("nice_to_have_skills", [])]
        min_exp = state.get("min_experience_years", 0)

        scored = []
        for c in profiles:
            c_skills = c["skills"]
            matched_must = [s for s in must_haves if any(s in cs for cs in c_skills)]
            matched_nice = [s for s in nice_to_haves if any(s in cs for cs in c_skills)]

            # Scoring algorithm (0-100)
            score = 0
            if must_haves:
                score += int((len(matched_must) / len(must_haves)) * 50)
            else:
                score += 30

            if nice_to_haves:
                score += int((len(matched_nice) / len(nice_to_haves)) * 20)
            else:
                score += 10

            exp = c["experience_years"]
            if exp >= min_exp:
                score += 20
                if exp > min_exp:
                    score += min(10, (exp - min_exp) * 2)
            else:
                score += max(0, int((exp / max(1, min_exp)) * 15))

            scored.append({
                **c,
                "score": min(100, score),
                "matched_must_have": matched_must,
                "matched_nice_to_have": matched_nice
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        shortlist = scored[:5]

        step_history = state.get("step_history", []) + ["rank_candidates"]

        return {
            "shortlist": shortlist,
            "step_history": step_history
        }

    def _enrich_candidates_mcp_node(self, state: MCPMatchingAgentState) -> Dict[str, Any]:
        """Node 4: Enriches Top-K candidates using Candidate Database MCP Server (Server 2)."""
        shortlist = state.get("shortlist", [])
        enriched_list = []

        for cand in shortlist:
            # MCP Tool Call: get_candidate_hr_record on candidate_db_server
            db_resp = self.mcp_client.call_tool("get_candidate_hr_record", {
                "candidate_name": cand["name"]
            })
            hr_record = db_resp.get("result", {}).get("record", {})

            enriched_cand = {
                **cand,
                "hr_data": hr_record,
                "notice_period_days": hr_record.get("notice_period_days", 30),
                "background_status": hr_record.get("background_check_status", "UNKNOWN"),
                "hr_tags": hr_record.get("tags", [])
            }
            enriched_list.append(enriched_cand)

        step_history = state.get("step_history", []) + ["enrich_candidates_mcp"]

        return {
            "enriched_shortlist": enriched_list,
            "step_history": step_history
        }

    def _generate_report_node(self, state: MCPMatchingAgentState) -> Dict[str, Any]:
        """Node 5: Generates comprehensive Markdown summary with MCP metadata."""
        shortlist = state.get("enriched_shortlist", [])
        must_haves = state.get("must_have_skills", [])
        nice_to_haves = state.get("nice_to_have_skills", [])
        min_exp = state.get("min_experience_years", 0)
        perf = self.mcp_client.get_performance_summary()

        report_lines = [
            "# Candidate Screening & Matching Report (MCP Multi-Server Powered)",
            "",
            "## 1. Job Requirements Extracted",
            f"- **Minimum Experience**: {min_exp} years",
            f"- **Must-Have Skills**: {', '.join(must_haves) if must_haves else 'None specified'}",
            f"- **Nice-to-Have Skills**: {', '.join(nice_to_haves) if nice_to_haves else 'None specified'}",
            "",
            "## 2. Top-Ranked Shortlisted Candidates (Enriched via MCP)",
            "| Rank | Candidate | Title | Exp | Score | Notice Period | BG Check | Matched Must-Haves |",
            "|---|---|---|---|---|---|---|---|"
        ]

        for i, c in enumerate(shortlist, 1):
            hr = c.get("hr_data", {})
            report_lines.append(
                f"| #{i} | **{c['name']}** | {c['title']} | {c['experience_years']} yrs | **{c['score']}/100** | {c.get('notice_period_days', 'N/A')} days | {c.get('background_status', 'N/A')} | {', '.join(c.get('matched_must_have', []))} |"
            )

        report_lines.extend([
            "",
            "## 3. Protocol Performance & Audit Telemetry",
            f"- **Total MCP Tool Calls**: {perf['total_calls']}",
            f"- **Average MCP Latency**: {perf['avg_latency_ms']} ms",
            f"- **Total Execution Time**: {perf['total_time_ms']} ms",
            "- **Connected MCP Servers**: `FilesystemMCPServer`, `CandidateDatabaseMCPServer`",
            ""
        ])

        final_report = "\n".join(report_lines)
        step_history = state.get("step_history", []) + ["generate_report"]

        return {
            "final_report": final_report,
            "step_history": step_history,
            "mcp_call_count": perf["total_calls"]
        }

    # -------------------------------------------------------------------------
    # Public Execution APIs
    # -------------------------------------------------------------------------
    def run_screening(self, job_description: str) -> Dict[str, Any]:
        """Executes full end-to-end agent workflow for a given JD."""
        initial_state: MCPMatchingAgentState = {
            "conversation_history": [],
            "job_description": job_description,
            "must_have_skills": [],
            "nice_to_have_skills": [],
            "min_experience_years": 0,
            "candidate_profiles": [],
            "shortlist": [],
            "enriched_shortlist": [],
            "final_report": "",
            "feedback": "",
            "step_history": [],
            "mcp_call_count": 0
        }
        return self.workflow.invoke(initial_state)

    def process_feedback(self, state: Dict[str, Any], feedback: str) -> Dict[str, Any]:
        """
        Processes human-in-the-loop recruiter feedback:
        - Notice period filtering
        - Candidate comparison
        - Hiring decision recording via Candidate DB MCP
        """
        feedback_lower = feedback.lower()
        enriched = list(state.get("enriched_shortlist", []))

        # Feedback Action 1: Filter by notice period
        if "immediate" in feedback_lower or "notice" in feedback_lower or "days" in feedback_lower:
            max_days = 30
            days_m = re.search(r'(\d+)\s*days?', feedback_lower)
            if days_m:
                max_days = int(days_m.group(1))

            filtered = [c for c in enriched if c.get("notice_period_days", 999) <= max_days]
            reply = f"Applied filter: Candidates with notice period <= {max_days} days. Found {len(filtered)} matching candidates."
            return {
                "response": reply,
                "filtered_candidates": filtered,
                "action": "filter_notice_period"
            }

        # Feedback Action 2: Record hiring decision via Candidate DB MCP
        if "hire" in feedback_lower or "interview" in feedback_lower or "decision" in feedback_lower:
            target_name = None
            for c in enriched:
                if c["name"].lower() in feedback_lower:
                    target_name = c["name"]
                    break

            if not target_name and enriched:
                target_name = enriched[0]["name"]

            decision = "SHORTLIST_FOR_ONSITE" if "hire" in feedback_lower or "shortlist" in feedback_lower else "REVIEW"
            mcp_res = self.mcp_client.call_tool("record_interview_decision", {
                "candidate_name": target_name,
                "decision": decision,
                "interviewer_notes": feedback
            })
            return {
                "response": f"Successfully updated Candidate DB via MCP: Recorded decision '{decision}' for {target_name}.",
                "mcp_result": mcp_res,
                "action": "record_decision"
            }

        # Feedback Action 3: General query / explanation
        return {
            "response": f"Recruiter feedback acknowledged: '{feedback}'. State maintained across session.",
            "action": "general_feedback"
        }
