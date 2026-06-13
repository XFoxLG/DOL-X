"""
Git Diff Parser

Parses Git diff output to extract file changes for mod creation.
Supports Twee, JavaScript, and CSS files.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Optional


class ChangeType(Enum):
    """Type of file change"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


@dataclass
class FileChange:
    """Represents a single file change from Git diff"""
    path: str
    change_type: ChangeType
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    
    @property
    def file_type(self) -> str:
        """Detect file type from path"""
        if self.path.endswith('.twee'):
            return 'twee'
        elif self.path.endswith('.js'):
            return 'javascript'
        elif self.path.endswith('.css'):
            return 'css'
        return 'unknown'
    
    @property
    def is_supported(self) -> bool:
        """Check if file type is supported for mod creation"""
        return self.file_type in ('twee', 'javascript', 'css')


class GitDiffParser:
    """
    Parse Git diff output to extract file changes.
    
    Example usage:
        parser = GitDiffParser()
        changes = parser.parse_diff(diff_output)
        for change in changes:
            print(f"{change.path}: {change.change_type}")
    """
    
    # Regex patterns for parsing diff
    DIFF_HEADER_PATTERN = re.compile(r'^diff --git a/(.*) b/(.*)$', re.MULTILINE)
    FILE_MODE_PATTERN = re.compile(r'^(new|deleted) file mode \d+$', re.MULTILINE)
    HUNK_HEADER_PATTERN = re.compile(r'^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', re.MULTILINE)
    
    def parse_diff(self, diff_output: str) -> List[FileChange]:
        """
        Parse Git diff output and return list of file changes.
        
        Args:
            diff_output: Raw output from `git diff` command
            
        Returns:
            List of FileChange objects
        """
        changes = []
        
        # Split diff into individual file sections
        file_sections = self._split_diff_by_file(diff_output)
        
        for section in file_sections:
            change = self._parse_file_section(section)
            if change and change.is_supported:
                changes.append(change)
        
        return changes
    
    def _split_diff_by_file(self, diff_output: str) -> List[str]:
        """Split diff output into sections for each file"""
        sections = []
        current_section = []
        
        for line in diff_output.split('\n'):
            if line.startswith('diff --git'):
                if current_section:
                    sections.append('\n'.join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        
        if current_section:
            sections.append('\n'.join(current_section))
        
        return sections
    
    def _parse_file_section(self, section: str) -> Optional[FileChange]:
        """Parse a single file section from diff"""
        lines = section.split('\n')
        
        # Extract file path from diff header
        header_match = self.DIFF_HEADER_PATTERN.search(section)
        if not header_match:
            return None
        
        file_path = header_match.group(2)
        
        # Detect change type
        change_type = self._detect_change_type(section)
        
        # Extract content
        old_content, new_content = self._extract_content(section, change_type)
        
        return FileChange(
            path=file_path,
            change_type=change_type,
            old_content=old_content,
            new_content=new_content
        )
    
    def _detect_change_type(self, section: str) -> ChangeType:
        """Detect if file was added, modified, or deleted"""
        if 'new file mode' in section:
            return ChangeType.ADDED
        elif 'deleted file mode' in section:
            return ChangeType.DELETED
        else:
            return ChangeType.MODIFIED
    
    def _extract_content(self, section: str, change_type: ChangeType) -> tuple:
        """
        Extract old and new file content from diff.
        
        Returns:
            (old_content, new_content) tuple
        """
        old_lines = []
        new_lines = []
        
        in_hunk = False
        for line in section.split('\n'):
            # Start of hunk
            if self.HUNK_HEADER_PATTERN.match(line):
                in_hunk = True
                continue
            
            if not in_hunk:
                continue
            
            # Context line (unchanged)
            if line.startswith(' '):
                content = line[1:]
                old_lines.append(content)
                new_lines.append(content)
            # Removed line
            elif line.startswith('-') and not line.startswith('---'):
                old_lines.append(line[1:])
            # Added line
            elif line.startswith('+') and not line.startswith('+++'):
                new_lines.append(line[1:])
        
        old_content = '\n'.join(old_lines) if old_lines else None
        new_content = '\n'.join(new_lines) if new_lines else None
        
        # For deleted files, only old_content exists
        if change_type == ChangeType.DELETED:
            new_content = None
        # For new files, only new_content exists
        elif change_type == ChangeType.ADDED:
            old_content = None
        
        return old_content, new_content
    
    def parse_commit_diff(self, commit_hash: str, repo_path: str = '.') -> List[FileChange]:
        """
        Parse diff for a specific commit.
        
        Args:
            commit_hash: Git commit hash
            repo_path: Path to Git repository (default: current directory)
            
        Returns:
            List of FileChange objects
        """
        import subprocess
        
        try:
            result = subprocess.run(
                ['git', 'show', '--pretty=', '--no-color', commit_hash],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return self.parse_diff(result.stdout)
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to get diff for commit {commit_hash}: {e.stderr}")
