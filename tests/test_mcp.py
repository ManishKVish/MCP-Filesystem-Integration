"""
Unit & Integration Tests for MCP Filesystem & Multi-Server Agent
Module: tests/test_mcp.py
"""
import os
import unittest
import tempfile
import shutil
from pathlib import Path

import filesystem_mcp_server
import candidate_db_mcp_server
from mcp_client_manager import MCPClientManager
from matching_agent import MCPMatchingAgent


class TestMCPFilesystemServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = tempfile.mkdtemp()
        cls.sample_txt = Path(cls.test_dir) / "sample_resume.txt"
        with open(cls.sample_txt, "w", encoding="utf-8") as f:
            f.write(
                "NAME: John Doe\n"
                "TITLE: Senior Backend Engineer\n"
                "EXPERIENCE: 6 years\n"
                "SKILLS: Python, FastAPI, Docker, PostgreSQL\n"
                "PROFESSIONAL SUMMARY: Experienced in designing microservices.\n"
            )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.test_dir, ignore_errors=True)

    def test_read_file_success(self):
        res = filesystem_mcp_server.read_file(str(self.sample_txt))
        self.assertEqual(res["status"], "success")
        self.assertIn("John Doe", res["content"])
        self.assertEqual(res["extension"], ".txt")
        self.assertIn("line_count", res["metadata"])

    def test_read_file_not_found(self):
        res = filesystem_mcp_server.read_file("non_existent_file.txt")
        self.assertEqual(res["status"], "error")
        self.assertEqual(res["error_code"], "FILE_NOT_FOUND")

    def test_list_files(self):
        files = filesystem_mcp_server.list_files(self.test_dir, extension=".txt")
        self.assertTrue(len(files) >= 1)
        self.assertEqual(files[0]["filename"], "sample_resume.txt")

    def test_write_file(self):
        dest = Path(self.test_dir) / "subdir" / "output.txt"
        res = filesystem_mcp_server.write_file(str(dest), "Testing MCP Write")
        self.assertEqual(res["status"], "success")
        self.assertTrue(dest.exists())

    def test_search_in_file(self):
        res = filesystem_mcp_server.search_in_file(str(self.sample_txt), "FastAPI")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["match_count"], 1)
        self.assertIn("FastAPI", res["matches"][0]["snippet"])

    def test_watch_directory(self):
        res = filesystem_mcp_server.watch_directory(self.test_dir)
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["monitoring_active"])
        self.assertGreaterEqual(res["total_files"], 1)

    def test_batch_process_indexing(self):
        res = filesystem_mcp_server.batch_process(self.test_dir, target_extension=".txt", operation="index")
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["files_processed_count"], 1)
        self.assertEqual(res["results"][0]["name"], "John Doe")


class TestCandidateDatabaseMCPServer(unittest.TestCase):
    def test_get_candidate_hr_record_existing(self):
        res = candidate_db_mcp_server.get_candidate_hr_record("Aarav Sharma")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["found"])
        self.assertEqual(res["record"]["current_company"], "CloudScale Systems")
        self.assertEqual(res["record"]["notice_period_days"], 30)

    def test_get_candidate_hr_record_fallback(self):
        res = candidate_db_mcp_server.get_candidate_hr_record("NonExistent Candidate")
        self.assertEqual(res["status"], "success")
        self.assertFalse(res["found"])
        self.assertIn("candidate_id", res["record"])

    def test_query_candidates_by_notice_period(self):
        res = candidate_db_mcp_server.query_candidates_by_max_notice_period(20)
        self.assertTrue(len(res) >= 1)
        # Aditi Patel has 15 days notice
        names = [r["candidate_name"] for r in res]
        self.assertIn("Aditi Patel", names)

    def test_record_interview_decision(self):
        res = candidate_db_mcp_server.record_interview_decision(
            "Aarav Sharma", "HIRE", "Outstanding systems knowledge."
        )
        self.assertEqual(res["status"], "success")
        self.assertIn("Aarav Sharma", res["message"])


class TestMCPClientManager(unittest.TestCase):
    def setUp(self):
        self.client = MCPClientManager(enable_fallback=True)

    def test_tool_routing(self):
        # Route to Filesystem Server
        r1 = self.client.call_tool("list_files", {"directory": str(Path(__file__).parent.parent / "data" / "resumes")})
        self.assertEqual(r1["jsonrpc"], "2.0")
        self.assertIsNone(r1["error"])
        self.assertEqual(r1["metadata"]["server_id"], "filesystem_server")

        # Route to Candidate DB Server
        r2 = self.client.call_tool("get_candidate_hr_record", {"candidate_name": "Aditi Patel"})
        self.assertEqual(r2["jsonrpc"], "2.0")
        self.assertIsNone(r2["error"])
        self.assertEqual(r2["metadata"]["server_id"], "candidate_db_server")

    def test_fallback_on_failure(self):
        res = self.client.call_tool("read_file", {"filepath": "failing_path.txt"}, simulate_failure=True)
        self.assertTrue(res["metadata"]["fallback_applied"])
        self.assertEqual(res["result"]["status"], "degraded_fallback")

    def test_performance_tracking(self):
        self.client.call_tool("list_files", {"directory": "."})
        summary = self.client.get_performance_summary()
        self.assertGreaterEqual(summary["total_calls"], 1)
        self.assertGreater(summary["total_time_ms"], 0.0)


class TestMCPMatchingAgentIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = MCPMatchingAgent(enable_fallback=True)

    def test_screening_workflow_execution(self):
        jd = """
        Looking for a Senior Python & Machine Learning Engineer with 4+ years of experience.
        Must have strong skills in Python, PyTorch, Docker, and AWS.
        """
        result = self.agent.run_screening(jd)

        # Verification of pipeline stages
        self.assertIn("parse_requirements", result["step_history"])
        self.assertIn("scan_and_read_resumes_mcp", result["step_history"])
        self.assertIn("rank_candidates", result["step_history"])
        self.assertIn("enrich_candidates_mcp", result["step_history"])
        self.assertIn("generate_report", result["step_history"])

        # Verification of state contents
        self.assertGreaterEqual(len(result["shortlist"]), 1)
        self.assertGreaterEqual(len(result["enriched_shortlist"]), 1)
        self.assertIn("final_report", result)
        self.assertIn("Candidate Screening & Matching Report", result["final_report"])

    def test_recruiter_feedback_handling(self):
        jd = "Senior Python Engineer with 3+ years experience in Python and Docker."
        state = self.agent.run_screening(jd)

        # Feedback 1: Notice period filtering
        fb1 = self.agent.process_feedback(state, "Filter candidates with 30 days notice")
        self.assertEqual(fb1["action"], "filter_notice_period")
        self.assertTrue(isinstance(fb1["filtered_candidates"], list))

        # Feedback 2: Interview decision
        fb2 = self.agent.process_feedback(state, "Shortlist and hire Aarav Sharma")
        self.assertEqual(fb2["action"], "record_decision")
        self.assertIn("Successfully updated Candidate DB via MCP", fb2["response"])


if __name__ == "__main__":
    unittest.main()
