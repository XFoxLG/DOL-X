"""
Commit to Mod Converter

Main entry point for converting Git commits to DoL ModLoader mods.
This is DOL-X's reimplementation of upstream DoL-Commit2Mod with improvements.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from .git_diff_parser import GitDiffParser, FileChange, ChangeType
from .boot_json_builder import BootJsonBuilder
from .dependency_inferrer import DependencyInferrer


class CommitToModConverter:
    """
    Convert Git commits to DoL ModLoader mod packages.
    
    Key improvements over upstream DoL-Commit2Mod:
    1. Automatic dependency inference (maplebirch framework detection)
    2. CSS file support
    3. Better error messages and validation
    4. Cleaner code structure
    
    Example usage:
        converter = CommitToModConverter()
        mod_path = converter.convert_commit(
            commit_hash="abc123",
            output_dir="mods/",
            mod_name="MyMod",
            author="Developer"
        )
    """
    
    def __init__(self, repo_path: str = '.'):
        """
        Initialize converter.
        
        Args:
            repo_path: Path to Git repository (default: current directory)
        """
        self.repo_path = Path(repo_path)
        self.diff_parser = GitDiffParser()
        self.boot_builder = BootJsonBuilder()
        self.dep_inferrer = DependencyInferrer()
    
    def convert_commit(
        self,
        commit_hash: str,
        output_dir: str,
        mod_name: Optional[str] = None,
        author: Optional[str] = None,
        description: Optional[str] = None,
        version: str = "1.0.0"
    ) -> Path:
        """
        Convert a Git commit to a mod package.
        
        Args:
            commit_hash: Git commit hash to convert
            output_dir: Directory to create mod in
            mod_name: Mod name (default: auto-generate from commit)
            author: Mod author (default: git commit author)
            description: Mod description (default: commit message)
            version: Mod version (default: "1.0.0")
            
        Returns:
            Path to created mod directory
        """
        # Parse commit diff
        file_changes = self.diff_parser.parse_commit_diff(commit_hash, str(self.repo_path))
        
        if not file_changes:
            raise ValueError(f"No supported file changes found in commit {commit_hash}")
        
        # Get commit metadata
        commit_info = self._get_commit_info(commit_hash)
        
        # Use provided values or defaults from commit
        mod_name = mod_name or self._generate_mod_name(commit_hash)
        author = author or commit_info['author']
        description = description or commit_info['message']
        
        # Infer dependencies from code
        dependencies = self.dep_inferrer.infer_dependencies(file_changes)
        
        # Create mod directory structure
        mod_path = Path(output_dir) / mod_name
        self._create_mod_directory(mod_path)
        
        # Copy files to mod directory
        script_files, twee_files, css_files = self._copy_files(file_changes, mod_path)
        
        # Build boot.json
        boot_json = self.boot_builder.build(
            name=mod_name,
            version=version,
            author=author,
            description=description,
            script_files=script_files,
            twee_files=twee_files,
            css_files=css_files,
            dependencies=dependencies
        )
        
        # Validate boot.json
        is_valid, errors = self.boot_builder.validate(boot_json)
        if not is_valid:
            raise ValueError(f"Invalid boot.json: {', '.join(errors)}")
        
        # Save boot.json
        self.boot_builder.save(boot_json, str(mod_path / "boot.json"))
        
        return mod_path
    
    def _get_commit_info(self, commit_hash: str) -> dict:
        """Get commit metadata (author, message, etc.)"""
        try:
            # Get author
            result = subprocess.run(
                ['git', 'show', '-s', '--format=%an', commit_hash],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            author = result.stdout.strip()
            
            # Get commit message
            result = subprocess.run(
                ['git', 'show', '-s', '--format=%s', commit_hash],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            message = result.stdout.strip()
            
            return {
                'author': author,
                'message': message
            }
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to get commit info: {e.stderr}")
    
    def _generate_mod_name(self, commit_hash: str) -> str:
        """Generate mod name from commit hash"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        short_hash = commit_hash[:7]
        return f"mod_{short_hash}_{timestamp}"
    
    def _create_mod_directory(self, mod_path: Path) -> None:
        """Create mod directory structure"""
        if mod_path.exists():
            raise ValueError(f"Mod directory already exists: {mod_path}")
        
        mod_path.mkdir(parents=True, exist_ok=True)
    
    def _copy_files(self, file_changes: List[FileChange], mod_path: Path) -> tuple:
        """
        Copy changed files to mod directory.
        
        Returns:
            (script_files, twee_files, css_files) tuple
        """
        script_files = []
        twee_files = []
        css_files = []
        
        for change in file_changes:
            if change.change_type == ChangeType.DELETED:
                continue
            
            # Determine target filename
            filename = Path(change.path).name
            
            # Copy file content
            target_path = mod_path / filename
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(change.new_content)
            
            # Track file by type
            if change.file_type == 'javascript':
                script_files.append(filename)
            elif change.file_type == 'twee':
                twee_files.append(filename)
            elif change.file_type == 'css':
                css_files.append(filename)
        
        return script_files, twee_files, css_files
    
    def validate_mod(self, mod_path: Path) -> tuple[bool, List[str]]:
        """
        Validate a mod directory.
        
        Args:
            mod_path: Path to mod directory
            
        Returns:
            (is_valid, error_messages) tuple
        """
        errors = []
        
        # Check if directory exists
        if not mod_path.exists():
            errors.append(f"Mod directory does not exist: {mod_path}")
            return (False, errors)
        
        # Check for boot.json
        boot_json_path = mod_path / "boot.json"
        if not boot_json_path.exists():
            errors.append("Missing boot.json file")
            return (False, errors)
        
        # Validate boot.json
        boot_json = self.boot_builder.load(str(boot_json_path))
        is_valid, boot_errors = self.boot_builder.validate(boot_json)
        errors.extend(boot_errors)
        
        # Check that referenced files exist
        all_files = []
        all_files.extend(boot_json.get('scriptFiles', []))
        all_files.extend(boot_json.get('tweeFiles', []))
        
        if 'stylesheetFile' in boot_json:
            all_files.append(boot_json['stylesheetFile'])
        all_files.extend(boot_json.get('stylesheetFiles', []))
        
        for filename in all_files:
            file_path = mod_path / filename
            if not file_path.exists():
                errors.append(f"Referenced file does not exist: {filename}")
        
        return (len(errors) == 0, errors)
