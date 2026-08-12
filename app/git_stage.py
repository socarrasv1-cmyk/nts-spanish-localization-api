import subprocess
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from app.store import store
import re


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
        if ".." in branch_name or "/" in branch_name.split("/")[0]:
            raise GitStagingError(f"Invalid branch name: {branch_name}")
        if not re.match(r'^[a-zA-Z0-9._/-]+$', branch_name):
            raise GitStagingError(f"Invalid branch name: {branch_name}")
    
    def create_branch(self, branch_name: str, base_branch: Optional[str] = None) -> Dict[str, Any]:
        """Create a staging-only translation branch."""
        self._validate_branch_name(branch_name)
        
        base = base_branch or self.default_base_branch
        self.repo_path.mkdir(parents=True, exist_ok=True)
        
        try:
            if not (self.repo_path / ".git").exists():
                subprocess.run(["git", "init"], cwd=self.repo_path, check=True, capture_output=True)
            
            subprocess.run(["git", "checkout", "-b", branch_name], cwd=self.repo_path, 
                          capture_output=True, check=False)
            
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
        
        try:
            for file_info in files:
                file_path = self.repo_path / file_info["path"]
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, 'w') as f:
                    f.write(file_info["content"])
            
            subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", commit_message], cwd=self.repo_path, 
                          capture_output=True, check=False)
            
            return {
                "branch": branch_name,
                "files_staged": len(files),
                "commit_message": commit_message,
                "status": "committed"
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
        return {
            "pr_number": None,
            "status": "draft_pr_creation_requires_github_token",
            "message": "GitHub token (NTS_GITHUB_TOKEN) required for PR creation"
        }
