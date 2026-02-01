"""Repository analyzer service - detects repo type, structure, and metadata"""
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class RepositoryAnalyzer:
    """Analyzes repository structure and detects type, frameworks, entry points"""
    
    # File patterns for different repository types
    REPO_INDICATORS = {
        "python": {
            "extensions": [".py"],
            "key_files": ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile", "poetry.lock"],
            "frameworks": {
                "fastapi": ["fastapi", "starlette"],
                "django": ["django"],
                "flask": ["flask"],
                "sqlalchemy": ["sqlalchemy"],
                "asyncio": ["asyncio"],
            }
        },
        "javascript": {
            "extensions": [".js", ".jsx"],
            "key_files": ["package.json", "yarn.lock", "pnpm-lock.yaml"],
            "frameworks": {
                "react": ["react"],
                "nextjs": ["next"],
                "vue": ["vue"],
                "angular": ["@angular/core"],
                "express": ["express"],
                "nestjs": ["@nestjs/core"],
            }
        },
        "typescript": {
            "extensions": [".ts", ".tsx"],
            "key_files": ["tsconfig.json", "package.json"],
            "frameworks": {
                "nextjs": ["next"],
                "react": ["react"],
                "angular": ["@angular/core"],
                "nestjs": ["@nestjs/core"],
            }
        },
        "java": {
            "extensions": [".java"],
            "key_files": ["pom.xml", "build.gradle", "settings.gradle"],
            "frameworks": {
                "spring": ["spring-core", "spring-boot"],
                "maven": ["maven"],
            }
        },
        "go": {
            "extensions": [".go"],
            "key_files": ["go.mod", "go.sum"],
            "frameworks": {
                "gin": ["github.com/gin-gonic/gin"],
                "echo": ["github.com/labstack/echo"],
            }
        },
        "rust": {
            "extensions": [".rs"],
            "key_files": ["Cargo.toml"],
            "frameworks": {
                "actix": ["actix-web"],
                "axum": ["axum"],
            }
        },
        "csharp": {
            "extensions": [".cs"],
            "key_files": ["*.csproj", "*.sln"],
            "frameworks": {
                "aspnet": ["Microsoft.AspNetCore"],
            }
        },
        "php": {
            "extensions": [".php"],
            "key_files": ["composer.json", "composer.lock"],
            "frameworks": {
                "laravel": ["laravel/framework"],
                "symfony": ["symfony/symfony"],
            }
        },
    }
    
    # Skip patterns
    DEFAULT_SKIP_PATTERNS = {
        ".git",
        ".github",
        ".gitlab",
        ".gitignore",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        ".env",
        ".env.local",
        "dist",
        "build",
        "target",
        ".tox",
        ".pytest_cache",
        ".mypy_cache",
        ".coverage",
        "coverage",
        "htmlcov",
        ".idea",
        ".vscode",
        ".DS_Store",
        "*.egg-info",
        ".next",
        ".nuxt",
        ".cache",
        "tmp",
        "temp",
    }
    
    # Important file patterns
    IMPORTANT_FILES = {
        "entry_points": ["main.py", "index.js", "index.ts", "app.py", "server.py", "src/main.tsx", "src/index.tsx"],
        "config_files": ["pyproject.toml", "setup.py", "requirements.txt", "package.json", "tsconfig.json", "docker-compose.yml", ".env.example"],
        "documentation": ["README.md", "CONTRIBUTING.md", "docs/"],
    }
    
    def __init__(self, repo_path: str):
        """Initialize repository analyzer"""
        self.repo_path = Path(repo_path)
        self.skip_patterns = self.DEFAULT_SKIP_PATTERNS
    
    def analyze(self) -> Dict[str, Any]:
        """Analyze repository and return metadata"""
        logger.info(f"Analyzing repository: {self.repo_path}")
        
        try:
            # Detect repository type
            repo_type = self._detect_repository_type()
            
            # Count files by type
            file_stats = self._count_files_by_type()
            
            # Find entry points
            entry_points = self._find_entry_points()
            
            # Find important files
            important_files = self._find_important_files()
            
            # Detect frameworks
            frameworks = self._detect_frameworks(repo_type)
            
            # Parse dependencies
            dependencies = self._extract_dependencies(repo_type)
            
            metadata = {
                "repository_type": repo_type,
                "primary_framework": frameworks.get("primary"),
                "secondary_frameworks": frameworks.get("secondary", []),
                "total_files": file_stats["total"],
                "code_files": file_stats["code"],
                "test_files": file_stats["test"],
                "config_files": file_stats["config"],
                "documentation_files": file_stats["documentation"],
                "entry_points": entry_points,
                "config_files_list": important_files.get("config_files", []),
                "dependencies": dependencies,
            }
            
            logger.info(f"Repository analysis complete: {repo_type} - {file_stats['code']} code files")
            return metadata
            
        except Exception as e:
            logger.error(f"Error analyzing repository: {e}", exc_info=True)
            raise
    
    def _detect_repository_type(self) -> str:
        """Detect primary repository type"""
        logger.debug(f"Detecting repository type from: {self.repo_path}")
        
        file_count_by_type = {}
        
        for root, dirs, files in os.walk(self.repo_path):
            # Filter skip directories
            dirs[:] = [d for d in dirs if d not in self.skip_patterns]
            
            for file in files:
                for repo_type, indicators in self.REPO_INDICATORS.items():
                    ext = Path(file).suffix.lower()
                    if ext in indicators["extensions"]:
                        file_count_by_type[repo_type] = file_count_by_type.get(repo_type, 0) + 1
        
        if not file_count_by_type:
            logger.warning("Could not detect repository type, defaulting to unknown")
            return "unknown"
        
        detected_type = max(file_count_by_type, key=file_count_by_type.get)
        logger.debug(f"Detected repository type: {detected_type}")
        return detected_type
    
    def _count_files_by_type(self) -> Dict[str, int]:
        """Count files by type (code, test, config, documentation)"""
        logger.debug("Counting files by type")
        
        stats = {
            "total": 0,
            "code": 0,
            "test": 0,
            "config": 0,
            "documentation": 0,
        }
        
        code_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".cs", ".php",
            ".rb", ".cpp", ".c", ".h", ".swift", ".kt", ".scala", ".r", ".m",
        }
        
        test_patterns = ["test_", "_test.py", ".test.js", ".test.ts", ".test.jsx", ".test.tsx"]
        config_extensions = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml"}
        doc_extensions = {".md", ".rst", ".txt"}
        
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.skip_patterns]
            
            for file in files:
                stats["total"] += 1
                ext = Path(file).suffix.lower()
                
                # Check if test file
                is_test = any(test_pattern in file for test_pattern in test_patterns)
                if is_test:
                    stats["test"] += 1
                elif ext in code_extensions:
                    stats["code"] += 1
                elif ext in config_extensions:
                    stats["config"] += 1
                elif ext in doc_extensions:
                    stats["documentation"] += 1
        
        logger.debug(f"File counts: {stats}")
        return stats
    
    def _find_entry_points(self) -> Dict[str, str]:
        """Find main entry points (main.py, index.js, etc.)"""
        logger.debug("Finding entry points")
        
        entry_points = {}
        
        for entry_point in self.IMPORTANT_FILES["entry_points"]:
            full_path = self.repo_path / entry_point
            if full_path.exists():
                entry_points[entry_point] = str(full_path.relative_to(self.repo_path))
                logger.debug(f"Found entry point: {entry_point}")
        
        return entry_points
    
    def _find_important_files(self) -> Dict[str, List[str]]:
        """Find important configuration files"""
        logger.debug("Finding important files")
        
        important = {
            "config_files": [],
            "documentation_files": [],
        }
        
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.skip_patterns]
            
            for file in files:
                file_path = Path(root) / file
                relative_path = str(file_path.relative_to(self.repo_path))
                
                # Check if config file
                if any(cf in self.IMPORTANT_FILES["config_files"] for cf in [file, relative_path]):
                    important["config_files"].append(relative_path)
                
                # Check if documentation
                if file.endswith(".md") or file.startswith("README"):
                    important["documentation_files"].append(relative_path)
        
        return important
    
    def _detect_frameworks(self, repo_type: str) -> Dict[str, Any]:
        """Detect frameworks used in the repository"""
        logger.debug(f"Detecting frameworks for {repo_type}")
        
        frameworks = {
            "primary": None,
            "secondary": []
        }
        
        if repo_type not in self.REPO_INDICATORS:
            return frameworks
        
        indicators = self.REPO_INDICATORS[repo_type]
        detected_frameworks = {}
        
        # Check key files for framework mentions
        key_files = self._find_key_files(indicators["key_files"])
        
        for framework, patterns in indicators["frameworks"].items():
            for key_file in key_files:
                try:
                    with open(key_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if any(pattern in content for pattern in patterns):
                            detected_frameworks[framework] = True
                except Exception:
                    pass
        
        if detected_frameworks:
            frameworks["primary"] = list(detected_frameworks.keys())[0]
            frameworks["secondary"] = list(detected_frameworks.keys())[1:]
        
        logger.debug(f"Detected frameworks: {frameworks}")
        return frameworks
    
    def _find_key_files(self, key_file_patterns: List[str]) -> List[str]:
        """Find key configuration files"""
        found_files = []
        
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in self.skip_patterns]
            
            for file in files:
                if any(pattern in file for pattern in key_file_patterns):
                    found_files.append(os.path.join(root, file))
        
        return found_files
    
    def _extract_dependencies(self, repo_type: str) -> Dict[str, Any]:
        """Extract framework and library dependencies"""
        logger.debug(f"Extracting dependencies for {repo_type}")
        
        dependencies = {}
        
        if repo_type == "python":
            dependencies = self._extract_python_dependencies()
        elif repo_type in ["javascript", "typescript"]:
            dependencies = self._extract_npm_dependencies()
        elif repo_type == "java":
            dependencies = self._extract_java_dependencies()
        
        return dependencies
    
    def _extract_python_dependencies(self) -> Dict[str, Any]:
        """Extract Python dependencies from requirements.txt, setup.py, pyproject.toml"""
        dependencies = {}
        
        # Check requirements.txt
        req_file = self.repo_path / "requirements.txt"
        if req_file.exists():
            try:
                with open(req_file, "r") as f:
                    dependencies["requirements"] = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            except Exception:
                pass
        
        # Check pyproject.toml
        pyproject_file = self.repo_path / "pyproject.toml"
        if pyproject_file.exists():
            try:
                with open(pyproject_file, "r") as f:
                    content = f.read()
                    # Simple extraction - would need proper TOML parsing for production
                    if "dependencies" in content:
                        dependencies["pyproject"] = True
            except Exception:
                pass
        
        return dependencies
    
    def _extract_npm_dependencies(self) -> Dict[str, Any]:
        """Extract Node.js dependencies from package.json"""
        dependencies = {}
        
        package_file = self.repo_path / "package.json"
        if package_file.exists():
            try:
                with open(package_file, "r") as f:
                    package_data = json.load(f)
                    dependencies["dependencies"] = package_data.get("dependencies", {})
                    dependencies["devDependencies"] = package_data.get("devDependencies", {})
            except Exception:
                pass
        
        return dependencies
    
    def _extract_java_dependencies(self) -> Dict[str, Any]:
        """Extract Java dependencies from pom.xml or build.gradle"""
        dependencies = {}
        
        pom_file = self.repo_path / "pom.xml"
        if pom_file.exists():
            dependencies["maven"] = True
        
        gradle_file = self.repo_path / "build.gradle"
        if gradle_file.exists():
            dependencies["gradle"] = True
        
        return dependencies
