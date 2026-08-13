import subprocess
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from app.store import store
import re
import json
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError


class GitStagingError(Exception):
    pass


class GitStaging:
    """
    Git staging for translation branches.
    Staging-only: no auto-merge, no production deployment.
    Branch push disabled by default (NTS_GIT_PUSH_ENABLED=false).
    """
    
    def __init__(self):
        self.repo_path = Path(os.getenv("NTS_GIT_REPO_PATH", "./data/git-repo"))
        self.remote_name = os.getenv("NTS_GIT_REMOTE_NAME", "origin")
        self.default_base_branch = os.getenv("NTS_GIT_DEFAULT_BASE_BRANCH", "main")
        self.push_enabled = os.getenv("NTS_GIT_PUSH_ENABLED", "false").lower() == "true"
        self.store_key = "git_staging"
    
    def get_status(self) -> Dict[str, Any]:
        """Get Git staging repository status."""
        return {
            "repo_path": str(self.repo_path),
            "remote_name": self.remote_name,
            "default_base_branch": self.default_base_branch,
            "push_enabled": self.push_enabled,
            "initialized": self.repo_path.exists()
        }
    
    def _validate_branch_name(self, branch_name: str) -> None:
        """Validate branch name for safety."""
        if not branch_name or branch_name.startswith(("/", "-")):
            raise GitStagingError(f"Invalid branch name: {branch_name}")
        if any(token in branch_name for token in ("..", "//", "@{", "\\")) or branch_name.endswith(("/", ".", ".lock")):
            raise GitStagingError(f"Invalid branch name: {branch_name}")
        if not re.fullmatch(r'[a-zA-Z0-9._/-]+', branch_name):
            raise GitStagingError(f"Invalid branch name: {branch_name}")

    def _safe_file_path(self, relative_path: str) -> Path:
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise GitStagingError(f"Unsafe staging path: {relative_path}")
        root = self.repo_path.resolve()
        candidate = (root / relative_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise GitStagingError(f"Staging path escapes repository: {relative_path}")
        return candidate
    
    def create_branch(self, branch_name: str, base_branch: Optional[str] = None) -> Dict[str, Any]:
        """Create a staging-only translation branch."""
        self._validate_branch_name(branch_name)
        base = base_branch or self.default_base_branch
        self._validate_branch_name(base)
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if not (self.repo_path / ".git").exists():
                subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
            base_exists = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{base}"],
                cwd=self.repo_path, check=False,
            ).returncode == 0
            if base_exists:
                subprocess.run(["git", "checkout", base], cwd=self.repo_path,
                               capture_output=True, text=True, check=True)
            proc = subprocess.run(["git", "checkout", "-b", branch_name], cwd=self.repo_path,
                                  capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise GitStagingError((proc.stderr or proc.stdout).strip())
            
            return {
                "branch": branch_name,
                "status": "created",
                "base_branch": base
            }
        except Exception as e:
            raise GitStagingError(f"Failed to create branch: {e}")
    
    def stage_files(self, branch_name: str, files: List[Dict[str, str]], commit_message: str) -> Dict[str, Any]:
        """Write READY translation files to staging repo and commit."""
        self._validate_branch_name(branch_name)
        if not commit_message or not commit_message.strip():
            raise GitStagingError("commit_message is required")
        try:
            current_branch = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"], cwd=self.repo_path,
                capture_output=True, text=True, check=False,
            ).stdout.strip()
            if current_branch != branch_name:
                checkout = subprocess.run(
                    ["git", "checkout", branch_name], cwd=self.repo_path,
                    capture_output=True, text=True, check=False,
                )
                if checkout.returncode != 0:
                    raise GitStagingError((checkout.stderr or checkout.stdout).strip())
            for file_info in files:
                if not isinstance(file_info, dict) or "path" not in file_info or "content" not in file_info:
                    raise GitStagingError("Each file requires path and content")
                file_path = self._safe_file_path(file_info["path"])
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w', encoding="utf-8") as f:
                    f.write(file_info["content"])
            
            subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True, capture_output=True)
            author_name = os.getenv("NTS_GIT_AUTHOR_NAME", "NTS Spanish Translator")
            author_email = os.getenv("NTS_GIT_AUTHOR_EMAIL", "localization@nationwidetransportservices.com")
            proc = subprocess.run([
                "git", "-c", f"user.name={author_name}", "-c", f"user.email={author_email}",
                "commit", "-m", commit_message,
            ], cwd=self.repo_path, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                raise GitStagingError((proc.stderr or proc.stdout).strip())
            commit_sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.repo_path,
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            
            return {
                "branch": branch_name,
                "files_staged": len(files),
                "commit_message": commit_message,
                "status": "committed",
                "commit_sha": commit_sha,
            }
        except Exception as e:
            raise GitStagingError(f"Failed to stage files: {e}")
    
    def push(self, branch_name: str) -> Dict[str, Any]:
        """Push an existing translation branch when push is explicitly enabled."""
        if not self.push_enabled:
            raise GitStagingError("Git push is disabled (NTS_GIT_PUSH_ENABLED=false)")
        
        self._validate_branch_name(branch_name)
        
        try:
            subprocess.run(["git", "push", self.remote_name, branch_name], 
                          cwd=self.repo_path, check=True, capture_output=True)
            return {
                "branch": branch_name,
                "remote": self.remote_name,
                "status": "pushed"
            }
        except Exception as e:
            raise GitStagingError(f"Failed to push branch: {e}")
    
    def create_draft_pr(self, branch_name: str, base_branch: str, title: str, body: str) -> Dict[str, Any]:
        """Create a draft GitHub pull request for human review."""
        self._validate_branch_name(branch_name)
        self._validate_branch_name(base_branch)
        token = os.getenv("NTS_GITHUB_TOKEN")
        repository = os.getenv("NTS_GITHUB_REPOSITORY")
        if not token or not repository or "/" not in repository:
            raise GitStagingError("NTS_GITHUB_TOKEN and NTS_GITHUB_REPOSITORY (owner/repo) are required")
        endpoint = f"https://api.github.com/repos/{repository}/pulls"
        payload = json.dumps({
            "title": title, "head": branch_name, "base": base_branch,
            "body": body, "draft": True,
        }).encode("utf-8")
        req = urlrequest.Request(endpoint, data=payload, method="POST", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json",
            "User-Agent": "nts-localization-api",
        })
        try:
            with urlrequest.urlopen(req, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise GitStagingError(f"GitHub rejected draft PR creation ({exc.code}): {detail}") from exc
        except URLError as exc:
            raise GitStagingError(f"GitHub draft PR request failed: {exc.reason}") from exc
        return {"pr_number": result.get("number"), "url": result.get("html_url"), "status": "draft"}
