"""
Boot.json Builder

Build boot.json files for DoL ModLoader mods.
Supports automatic dependency detection and metadata generation.
"""

import json
from typing import List, Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class BootJsonMetadata:
    """Metadata for boot.json file"""
    name: str
    version: str
    author: str
    description: str
    stylesheetFile: Optional[str] = None
    scriptFiles: Optional[List[str]] = None
    tweeFiles: Optional[List[str]] = None
    additionFile: Optional[str] = None
    dependenceInfo: Optional[List[Dict[str, str]]] = None


class BootJsonBuilder:
    """
    Build boot.json files for DoL ModLoader mods.
    
    Key improvements over upstream:
    - Automatic dependency field generation
    - CSS file support
    - Better error messages
    
    Example usage:
        builder = BootJsonBuilder()
        boot_json = builder.build(
            name="MyMod",
            version="1.0.0",
            author="Developer",
            description="A test mod",
            script_files=["script.js"],
            twee_files=["content.twee"],
            dependencies=["Simple Framework"]
        )
        builder.save(boot_json, "boot.json")
    """
    
    def build(
        self,
        name: str,
        version: str,
        author: str,
        description: str,
        script_files: Optional[List[str]] = None,
        twee_files: Optional[List[str]] = None,
        css_files: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
    ) -> dict:
        """
        Build boot.json structure.
        
        Args:
            name: Mod name
            version: Mod version (e.g., "1.0.0")
            author: Mod author
            description: Mod description
            script_files: List of JavaScript files
            twee_files: List of Twee files
            css_files: List of CSS files
            dependencies: List of dependency mod names
            
        Returns:
            boot.json as dict
        """
        boot_json = {
            "name": name,
            "version": version,
            "author": author,
            "description": description,
        }
        
        # Add file lists
        if script_files:
            boot_json["scriptFiles"] = script_files
        
        if twee_files:
            boot_json["tweeFiles"] = twee_files
        
        # CSS support (new feature!)
        if css_files:
            # ModLoader uses "stylesheetFile" for single CSS
            # or "stylesheetFiles" for multiple
            if len(css_files) == 1:
                boot_json["stylesheetFile"] = css_files[0]
            else:
                boot_json["stylesheetFiles"] = css_files
        
        # Dependency support (key improvement!)
        if dependencies:
            boot_json["dependenceInfo"] = self._build_dependencies(dependencies)
        
        return boot_json
    
    def _build_dependencies(self, dependencies: List[str]) -> List[Dict[str, str]]:
        """
        Build dependenceInfo structure for boot.json.
        
        Args:
            dependencies: List of dependency mod names
            
        Returns:
            List of dependency objects for boot.json
        """
        dep_info = []
        
        for dep_name in dependencies:
            dep_info.append({
                "modName": dep_name,
                "version": "^1.0.0"  # Accept any 1.x version
            })
        
        return dep_info
    
    def save(self, boot_json: dict, output_path: str) -> None:
        """
        Save boot.json to file.
        
        Args:
            boot_json: boot.json dict from build()
            output_path: Path to save boot.json
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(boot_json, f, indent=2, ensure_ascii=False)
    
    def load(self, input_path: str) -> dict:
        """
        Load existing boot.json file.
        
        Args:
            input_path: Path to existing boot.json
            
        Returns:
            boot.json as dict
        """
        with open(input_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def validate(self, boot_json: dict) -> tuple[bool, List[str]]:
        """
        Validate boot.json structure.
        
        Args:
            boot_json: boot.json dict to validate
            
        Returns:
            (is_valid, error_messages) tuple
        """
        errors = []
        
        # Required fields
        required_fields = ['name', 'version', 'author']
        for field in required_fields:
            if field not in boot_json:
                errors.append(f"Missing required field: {field}")
        
        # At least one content file
        has_content = any([
            boot_json.get('scriptFiles'),
            boot_json.get('tweeFiles'),
            boot_json.get('stylesheetFile'),
            boot_json.get('stylesheetFiles'),
        ])
        
        if not has_content:
            errors.append("No content files specified (scriptFiles, tweeFiles, or stylesheetFile)")
        
        # Validate version format
        version = boot_json.get('version', '')
        if version and not self._is_valid_version(version):
            errors.append(f"Invalid version format: {version} (expected X.Y.Z)")
        
        return (len(errors) == 0, errors)
    
    def _is_valid_version(self, version: str) -> bool:
        """Check if version string is valid semver"""
        import re
        pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$'
        return bool(re.match(pattern, version))
    
    def merge(self, base_boot_json: dict, updates: dict) -> dict:
        """
        Merge updates into existing boot.json.
        
        Useful for updating existing mods.
        
        Args:
            base_boot_json: Existing boot.json
            updates: Updates to apply
            
        Returns:
            Merged boot.json
        """
        merged = base_boot_json.copy()
        
        # Merge file lists
        for field in ['scriptFiles', 'tweeFiles', 'stylesheetFiles']:
            if field in updates:
                existing = set(merged.get(field, []))
                new_files = set(updates[field])
                merged[field] = sorted(list(existing | new_files))
        
        # Merge dependencies
        if 'dependenceInfo' in updates:
            existing_deps = {d['modName']: d for d in merged.get('dependenceInfo', [])}
            new_deps = {d['modName']: d for d in updates['dependenceInfo']}
            existing_deps.update(new_deps)
            merged['dependenceInfo'] = list(existing_deps.values())
        
        # Update metadata
        for field in ['name', 'version', 'author', 'description']:
            if field in updates:
                merged[field] = updates[field]
        
        return merged
