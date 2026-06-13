"""
Dependency Inferrer

Automatically infer mod dependencies from code analysis.
This is a key improvement over upstream DoL-Commit2Mod.
"""

import re
from typing import List, Set
from .git_diff_parser import FileChange


class DependencyInferrer:
    """
    Infer mod dependencies by analyzing code content.
    
    Key innovation: Automatically detects framework dependencies
    that upstream DoL-Commit2Mod misses.
    
    Example usage:
        inferrer = DependencyInferrer()
        deps = inferrer.infer_dependencies(file_changes)
        # Returns: ["Simple Framework", "ModLoader"]
    """
    
    # Framework detection patterns
    MAPLEBIRCH_PATTERNS = [
        re.compile(r'maplebirchFrameworks'),
        re.compile(r'window\.maplebirchFrameworks'),
        re.compile(r'MaplebirchFrameworks'),
        re.compile(r'frameworks\.register'),
    ]
    
    SIMPLE_FRAMEWORK_PATTERNS = [
        re.compile(r'SimpleFramework'),
        re.compile(r'window\.SimpleFramework'),
        re.compile(r'simpleFrameworks'),
    ]
    
    MODLOADER_PATTERNS = [
        re.compile(r'window\.modUtils'),
        re.compile(r'window\.modSC2DataManager'),
        re.compile(r'SC2_ModLoader'),
    ]
    
    def infer_dependencies(self, file_changes: List[FileChange]) -> List[str]:
        """
        Infer mod dependencies from file changes.
        
        Args:
            file_changes: List of FileChange objects from Git diff
            
        Returns:
            List of dependency mod names (e.g., ["Simple Framework"])
        """
        dependencies = set()
        
        for change in file_changes:
            # Only analyze new/modified content
            content = change.new_content
            if not content:
                continue
            
            # Check for framework usage
            if self._uses_maplebirch_framework(content):
                dependencies.add("Simple Framework")
            
            if self._uses_simple_framework(content):
                dependencies.add("Simple Framework")
            
            if self._uses_modloader_api(content):
                # ModLoader is always required, but we note explicit usage
                dependencies.add("ModLoader")
        
        # Convert to sorted list for consistency
        return sorted(list(dependencies))
    
    def _uses_maplebirch_framework(self, content: str) -> bool:
        """Check if code uses maplebirch framework"""
        return any(pattern.search(content) for pattern in self.MAPLEBIRCH_PATTERNS)
    
    def _uses_simple_framework(self, content: str) -> bool:
        """Check if code uses Simple Framework"""
        return any(pattern.search(content) for pattern in self.SIMPLE_FRAMEWORK_PATTERNS)
    
    def _uses_modloader_api(self, content: str) -> bool:
        """Check if code uses ModLoader API directly"""
        return any(pattern.search(content) for pattern in self.MODLOADER_PATTERNS)
    
    def analyze_content(self, content: str) -> dict:
        """
        Deep analysis of code content.
        
        Args:
            content: Code content (Twee, JS, or CSS)
            
        Returns:
            Analysis results with detected patterns
        """
        analysis = {
            'uses_maplebirch': self._uses_maplebirch_framework(content),
            'uses_simple_framework': self._uses_simple_framework(content),
            'uses_modloader': self._uses_modloader_api(content),
            'framework_calls': self._extract_framework_calls(content),
        }
        
        return analysis
    
    def _extract_framework_calls(self, content: str) -> List[str]:
        """Extract specific framework API calls for debugging"""
        calls = []
        
        # Look for common framework patterns
        patterns = [
            r'maplebirchFrameworks\.[a-zA-Z_]+',
            r'SimpleFramework\.[a-zA-Z_]+',
            r'window\.modUtils\.[a-zA-Z_]+',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            calls.extend(matches)
        
        return calls
