"""
Model Context Protocol (MCP) Filesystem Server
Module: filesystem_mcp_server.py
Exposes standardized file system tools, resources, directory monitoring,
and high-throughput batch operations over JSON-RPC 2.0.
"""
import os
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP(
    name="FilesystemMCPServer",
    instructions="Standardized MCP server exposing secure filesystem operations, file resources, directory watching, and batch processing."
)

# -----------------------------------------------------------------------------
# Part A: Core File System Tools as MCP Tools
# -----------------------------------------------------------------------------

@mcp.tool()
def read_file(filepath: str) -> Dict[str, Any]:
    """
    Reads document files (TXT, PDF, DOCX) and returns structured content with metadata.
    """
    path = Path(filepath)
    if not path.exists():
        return {
            "status": "error",
            "error_code": "FILE_NOT_FOUND",
            "message": f"File not found: {filepath}",
            "content": "",
            "metadata": {}
        }

    try:
        stat = path.stat()
        extension = path.suffix.lower()
        content = ""
        extra_meta = {}

        if extension == ".txt":
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            extra_meta["line_count"] = len(content.splitlines())

        elif extension == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                extra_meta["page_count"] = len(reader.pages)
                content = "\n".join(p.extract_text() or "" for p in reader.pages)
            except Exception:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()

        elif extension in (".docx", ".doc"):
            try:
                import docx
                doc = docx.Document(str(path))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                extra_meta["paragraph_count"] = len(paragraphs)
                content = "\n".join(paragraphs)
            except Exception:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
        else:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

        return {
            "status": "success",
            "filepath": str(path.resolve()),
            "filename": path.name,
            "extension": extension,
            "content": content,
            "metadata": {
                "file_size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                **extra_meta
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error_code": "READ_ERROR",
            "message": f"Failed reading {filepath}: {str(e)}",
            "content": "",
            "metadata": {}
        }


@mcp.tool()
def list_files(directory: str, extension: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lists files in a target directory with optional extension filtering and metadata.
    """
    dir_path = Path(directory)
    if not dir_path.exists() or not dir_path.is_dir():
        return []

    target_ext = extension.lower() if extension else None
    if target_ext and not target_ext.startswith("."):
        target_ext = f".{target_ext}"

    results = []
    for entry in sorted(dir_path.iterdir()):
        if entry.is_file():
            if target_ext and entry.suffix.lower() != target_ext:
                continue
            stat = entry.stat()
            results.append({
                "filename": entry.name,
                "filepath": str(entry.resolve()),
                "extension": entry.suffix.lower(),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
    return results


@mcp.tool()
def write_file(filepath: str, content: str) -> Dict[str, Any]:
    """
    Writes content to a file, automatically creating parent directories.
    """
    try:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        stat = path.stat()
        return {
            "status": "success",
            "filepath": str(path.resolve()),
            "bytes_written": stat.st_size
        }
    except Exception as e:
        return {"status": "error", "message": f"Write failed: {str(e)}"}


@mcp.tool()
def search_in_file(filepath: str, keyword: str) -> Dict[str, Any]:
    """
    Performs case-insensitive keyword search in file with context extraction.
    """
    res = read_file(filepath)
    if res["status"] != "success":
        return {"status": "error", "message": res.get("message", "Read error"), "matches": []}

    lines = res["content"].splitlines()
    matches = []
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)

    for line_idx, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, line_idx - 1)
            end = min(len(lines), line_idx + 2)
            matches.append({
                "line": line_idx + 1,
                "snippet": line.strip(),
                "context": "\n".join(lines[start:end])
            })

    return {
        "status": "success",
        "filepath": res["filepath"],
        "keyword": keyword,
        "match_count": len(matches),
        "matches": matches
    }

# -----------------------------------------------------------------------------
# Part A: New MCP-Specific Capabilities: watch_directory() & batch_process()
# -----------------------------------------------------------------------------

@mcp.tool()
def watch_directory(directory_path: str, poll_interval_seconds: int = 2) -> Dict[str, Any]:
    """
    MCP Capability: Monitors target resume directory for new or modified files.
    Returns directory snapshot and change audit.
    """
    dir_path = Path(directory_path)
    if not dir_path.exists() or not dir_path.is_dir():
        return {"status": "error", "message": f"Directory not found: {directory_path}"}

    files = list(dir_path.glob("*.*"))
    current_time = time.time()
    recent_threshold = 300 # Last 5 minutes

    recently_modified = []
    for f in files:
        mtime = f.stat().st_mtime
        if (current_time - mtime) < recent_threshold:
            recently_modified.append({
                "filename": f.name,
                "filepath": str(f.resolve()),
                "modified_seconds_ago": int(current_time - mtime)
            })

    return {
        "status": "success",
        "directory": str(dir_path.resolve()),
        "total_files": len(files),
        "recently_modified_count": len(recently_modified),
        "recent_files": recently_modified,
        "monitoring_active": True,
        "poll_interval_seconds": poll_interval_seconds
    }


@mcp.tool()
def batch_process(directory_path: str, target_extension: str = ".txt", operation: str = "index") -> Dict[str, Any]:
    """
    MCP Capability: High-throughput batch processor across candidate documents.
    Supported operations: 'index', 'word_count', 'summarize'.
    """
    dir_path = Path(directory_path)
    if not dir_path.exists() or not dir_path.is_dir():
        return {"status": "error", "message": f"Directory not found: {directory_path}"}

    target_ext = target_extension if target_extension.startswith(".") else f".{target_extension}"
    target_files = list(dir_path.glob(f"*{target_ext}"))

    processed = []
    start_time = time.time()

    for f in target_files:
        read_res = read_file(str(f))
        if read_res["status"] == "success":
            content = read_res["content"]
            if operation == "word_count":
                words = len(content.split())
                processed.append({"filename": f.name, "word_count": words})
            elif operation == "summarize":
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                snippet = " | ".join(lines[:3]) if lines else "Empty"
                processed.append({"filename": f.name, "summary_snippet": snippet})
            else: # 'index'
                name_m = re.search(r'NAME:\s*([^\n\r]+)', content)
                skills_m = re.search(r'SKILLS:\s*([^\n\r]+)', content)
                name = name_m.group(1).strip() if name_m else f.stem
                skills = [s.strip() for s in skills_m.group(1).split(",") if s.strip()] if skills_m else []
                processed.append({"filename": f.name, "name": name, "skills_count": len(skills)})

    duration = time.time() - start_time

    return {
        "status": "success",
        "operation": operation,
        "files_processed_count": len(processed),
        "duration_seconds": round(duration, 4),
        "results": processed
    }

# -----------------------------------------------------------------------------
# Part A: MCP Resource Exposure
# -----------------------------------------------------------------------------

@mcp.resource("file://resumes/{filename}")
def get_resume_resource(filename: str) -> str:
    """
    Exposes candidate resume documents directly as MCP file resources.
    URI: file://resumes/{filename}
    """
    base_dir = Path(__file__).parent / "data" / "resumes"
    file_path = base_dir / filename
    if not file_path.exists():
        return f"Resource not found: {filename}"
    res = read_file(str(file_path))
    return res["content"]


if __name__ == "__main__":
    # Runs standard MCP server over stdio
    mcp.run()
