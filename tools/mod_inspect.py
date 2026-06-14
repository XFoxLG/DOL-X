#!/usr/bin/env python3
"""
Mod Inspector - 深度检查 Mod 结构和依赖

用法:
    python tools/mod_inspect.py mod.mod.zip
    python tools/mod_inspect.py mod.mod.zip --verbose
    python tools/mod_inspect.py mod.mod.zip --output report.json
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Dict, List, Set, Optional


class ModInspector:
    def __init__(self, mod_path: str, verbose: bool = False):
        self.mod_path = Path(mod_path)
        self.verbose = verbose
        self.findings = {
            "structure": {},
            "boot_json": {},
            "api_usage": {},
            "inferred_deps": [],
            "warnings": [],
            "recommendations": []
        }
    
    def inspect(self) -> Dict:
        """执行完整检查"""
        if not self.mod_path.exists():
            raise FileNotFoundError(f"Mod 文件不存在: {self.mod_path}")
        
        with zipfile.ZipFile(self.mod_path, 'r') as zf:
            self._check_structure(zf)
            self._check_boot_json(zf)
            self._scan_api_usage(zf)
            self._infer_dependencies()
            self._generate_recommendations()
        
        return self.findings
    
    def _check_structure(self, zf: zipfile.ZipFile):
        """检查 ZIP 结构"""
        files = zf.namelist()
        
        # 检查 boot.json
        boot_at_root = 'boot.json' in files
        self.findings["structure"]["boot_json_at_root"] = boot_at_root
        
        if not boot_at_root:
            self.findings["warnings"].append("boot.json 不在根目录")
        
        # 检查加密特征
        encrypted = any('.crypt' in f or '.enc' in f for f in files)
        self.findings["structure"]["encrypted"] = encrypted
        
        if encrypted:
            self.findings["structure"]["encryption_files"] = [
                f for f in files if any(ext in f for ext in ['.crypt', '.salt', '.nonce'])
            ]
        
        # 检查大文件
        large_files = []
        for info in zf.infolist():
            if info.file_size > 5 * 1024 * 1024:  # > 5MB
                large_files.append(f"{info.filename} ({info.file_size // (1024*1024)}MB)")
        
        if large_files:
            self.findings["warnings"].append(f"发现大文件: {', '.join(large_files)}")
        
        self.findings["structure"]["file_count"] = len(files)
    
    def _check_boot_json(self, zf: zipfile.ZipFile):
        """检查 boot.json"""
        try:
            boot_data = zf.read('boot.json').decode('utf-8')
            boot = json.loads(boot_data)
            
            self.findings["boot_json"] = {
                "name": boot.get("name", "UNKNOWN"),
                "version": boot.get("version", "UNKNOWN"),
                "dependencies": boot.get("dependenceInfo", [])
            }
            
            # 检查别名
            if "alias" in boot:
                self.findings["boot_json"]["alias"] = boot["alias"]
        
        except KeyError:
            self.findings["warnings"].append("boot.json 不存在")
        except json.JSONDecodeError as e:
            self.findings["warnings"].append(f"boot.json 格式错误: {e}")
    
    def _scan_api_usage(self, zf: zipfile.ZipFile):
        """扫描 API 使用情况"""
        api_calls = {
            "getMod": [],
            "maplebirchFrameworks": [],
            "simpleFrameworks": [],
            "Swal": [],
            "modSC2DataManager": [],
            "AddonPluginManager": []
        }
        
        for filename in zf.namelist():
            if filename.endswith('.js'):
                try:
                    content = zf.read(filename).decode('utf-8', errors='ignore')
                    
                    # getMod 调用
                    for match in re.finditer(r'getMod\([\'"]([^\'"]+)[\'"]\)', content):
                        api_calls["getMod"].append(match.group(1))
                    
                    # 框架 API
                    if 'maplebirchFrameworks' in content:
                        api_calls["maplebirchFrameworks"].append(filename)
                    if 'simpleFrameworks' in content:
                        api_calls["simpleFrameworks"].append(filename)
                    if 'Swal.' in content or 'Swal.fire' in content:
                        api_calls["Swal"].append(filename)
                    if 'modSC2DataManager' in content:
                        api_calls["modSC2DataManager"].append(filename)
                    if 'AddonPluginManager' in content:
                        api_calls["AddonPluginManager"].append(filename)
                
                except Exception as e:
                    if self.verbose:
                        print(f"警告: 无法读取 {filename}: {e}")
        
        # 去重
        for key in api_calls:
            if isinstance(api_calls[key], list):
                api_calls[key] = list(set(api_calls[key]))
        
        self.findings["api_usage"] = api_calls
    
    def _infer_dependencies(self):
        """推断实际依赖"""
        api = self.findings["api_usage"]
        declared = {dep["modName"] for dep in self.findings["boot_json"].get("dependencies", [])}
        inferred = set()
        
        # 基于 getMod 调用
        for mod_name in api.get("getMod", []):
            if mod_name not in declared:
                inferred.add(mod_name)
        
        # 基于框架 API
        if api.get("maplebirchFrameworks"):
            if "maplebirch" not in declared:
                inferred.add("maplebirch")
        
        if api.get("simpleFrameworks"):
            if "Simple Frameworks" not in declared:
                inferred.add("Simple Frameworks")
        
        if api.get("Swal"):
            if "SweetAlert2Mod" not in declared:
                inferred.add("SweetAlert2Mod")
        
        self.findings["inferred_deps"] = sorted(list(inferred))
    
    def _generate_recommendations(self):
        """生成建议"""
        recs = []
        
        # 依赖建议
        if self.findings["inferred_deps"]:
            recs.append({
                "type": "missing_dependencies",
                "message": "发现未声明的依赖",
                "dependencies": self.findings["inferred_deps"]
            })
        
        # 加密警告
        if self.findings["structure"].get("encrypted"):
            recs.append({
                "type": "encryption",
                "message": "此 Mod 使用加密，需要密码才能完整分析"
            })
        
        self.findings["recommendations"] = recs
    
    def print_report(self):
        """打印报告"""
        print("=" * 60)
        print(f"Mod Inspector - {self.mod_path.name}")
        print("=" * 60)
        
        # 结构
        print("\n[结构]")
        if self.findings["structure"]["boot_json_at_root"]:
            print("✓ boot.json 在根目录")
        else:
            print("✗ boot.json 不在根目录")
        
        if self.findings["structure"].get("encrypted"):
            print("⚠ 检测到加密文件")
            if self.verbose:
                for f in self.findings["structure"]["encryption_files"]:
                    print(f"  - {f}")
        else:
            print("✓ 未检测到加密")
        
        print(f"  文件数量: {self.findings['structure']['file_count']}")
        
        # boot.json
        print("\n[boot.json]")
        boot = self.findings["boot_json"]
        print(f"名称: {boot.get('name', 'N/A')}")
        print(f"版本: {boot.get('version', 'N/A')}")
        
        deps = boot.get("dependencies", [])
        if deps:
            print("声明的依赖:")
            for dep in deps:
                print(f"  - {dep['modName']} {dep.get('version', '*')}")
        else:
            print("声明的依赖: (无)")
        
        # API 使用
        print("\n[API 使用]")
        api = self.findings["api_usage"]
        
        get_mod_calls = api.get("getMod", [])
        if get_mod_calls:
            print(f"getMod 调用 ({len(get_mod_calls)}):")
            for mod in get_mod_calls[:10]:  # 只显示前10个
                print(f"  - {mod}")
            if len(get_mod_calls) > 10:
                print(f"  ... 还有 {len(get_mod_calls) - 10} 个")
        
        if api.get("maplebirchFrameworks"):
            print(f"✓ 使用 maplebirchFrameworks API ({len(api['maplebirchFrameworks'])} 文件)")
        if api.get("simpleFrameworks"):
            print(f"✓ 使用 simpleFrameworks API ({len(api['simpleFrameworks'])} 文件)")
        if api.get("Swal"):
            print(f"✓ 使用 SweetAlert2 API ({len(api['Swal'])} 文件)")
        
        # 推断的依赖
        print("\n[推断的依赖]")
        inferred = self.findings["inferred_deps"]
        if inferred:
            print("⚠ 以下依赖未在 boot.json 中声明:")
            for dep in inferred:
                print(f"  - {dep}")
        else:
            print("✓ 所有依赖已正确声明")
        
        # 警告
        if self.findings["warnings"]:
            print("\n[警告]")
            for warning in self.findings["warnings"]:
                print(f"⚠ {warning}")
        
        # 建议
        if self.findings["recommendations"]:
            print("\n[建议]")
            for rec in self.findings["recommendations"]:
                if rec["type"] == "missing_dependencies":
                    print("建议在 boot.json 中添加:")
                    print('  "dependenceInfo": [')
                    for dep in rec["dependencies"]:
                        # 推荐版本
                        version = "^2.0.0" if dep == "ModLoader" else "*"
                        print(f'    {{"modName": "{dep}", "version": "{version}"}},')
                    print('  ]')
                else:
                    print(f"• {rec['message']}")
        
        print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="深度检查 Mod 结构和依赖",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python tools/mod_inspect.py mod.mod.zip
  python tools/mod_inspect.py mod.mod.zip --verbose
  python tools/mod_inspect.py mod.mod.zip --output report.json
        """
    )
    parser.add_argument("mod_path", help="Mod ZIP 文件路径")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("-o", "--output", help="输出 JSON 报告到文件")
    
    args = parser.parse_args()
    
    try:
        inspector = ModInspector(args.mod_path, verbose=args.verbose)
        findings = inspector.inspect()
        
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(findings, f, indent=2, ensure_ascii=False)
            print(f"报告已保存到: {args.output}")
        else:
            inspector.print_report()
        
        # 返回错误码
        if findings["inferred_deps"] or findings["warnings"]:
            return 1
        return 0
    
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
