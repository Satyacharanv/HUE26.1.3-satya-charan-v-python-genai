"""Code parser service - parses code files and extracts functions, classes, etc."""
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class CodeChunk:
    """Represents a parsed code chunk"""
    def __init__(
        self,
        name: str,
        chunk_type: str,
        content: str,
        start_line: int,
        end_line: int,
        language: str,
        docstring: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        parameters: Optional[Dict[str, Any]] = None,
        return_type: Optional[str] = None,
        parent: Optional[str] = None,
    ):
        self.name = name
        self.chunk_type = chunk_type
        self.content = content
        self.start_line = start_line
        self.end_line = end_line
        self.language = language
        self.docstring = docstring
        self.dependencies = dependencies or []
        self.parameters = parameters or {}
        self.return_type = return_type
        self.parent = parent
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "chunk_type": self.chunk_type,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "docstring": self.docstring,
            "dependencies": self.dependencies,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "parent": self.parent,
        }


class CodeParser:
    """Parses code files and extracts semantic chunks"""
    
    def __init__(self):
        self.parsers = {
            "python": PythonCodeParser(),
            "javascript": JavaScriptCodeParser(),
            "typescript": TypeScriptCodeParser(),
            "java": JavaCodeParser(),
            "csharp": CSharpCodeParser(),
        }
    
    def parse_file(self, file_path: str, language: str) -> List[CodeChunk]:
        """Parse a code file and extract chunks"""
        logger.debug(f"Parsing file: {file_path} ({language})")
        
        try:
            # Read file content
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Get appropriate parser
            parser = self.parsers.get(language)
            if parser:
                chunks = parser.parse(content, file_path, language)
                logger.debug(f"Extracted {len(chunks)} chunks from {file_path}")
                return chunks
            else:
                logger.warning(f"No parser available for language: {language}")
                return []
        
        except Exception as e:
            logger.error(f"Error parsing file {file_path}: {e}", exc_info=True)
            return []
    
    def detect_language(self, file_path: str) -> Optional[str]:
        """Detect language from file extension"""
        ext = Path(file_path).suffix.lower()
        
        language_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
        }
        
        return language_map.get(ext)


class PythonCodeParser:
    """Parses Python code using AST"""
    
    def parse(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Parse Python code and extract chunks"""
        chunks = []
        lines = content.split("\n")
        
        try:
            tree = ast.parse(content)
            
            # Extract module docstring
            module_docstring = ast.get_docstring(tree)
            
            # Extract top-level functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    chunk = self._parse_function(node, content, lines, language, file_path, module_docstring)
                    if chunk:
                        chunks.append(chunk)
                
                elif isinstance(node, ast.ClassDef):
                    chunk = self._parse_class(node, content, lines, language, file_path)
                    if chunk:
                        chunks.append(chunk)
        
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
        
        return chunks
    
    def _parse_function(self, node: ast.FunctionDef, content: str, lines: List[str], language: str, file_path: str, module_doc: Optional[str]) -> Optional[CodeChunk]:
        """Parse function definition"""
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        
        # Extract function content
        func_lines = lines[start_line - 1:end_line]
        func_content = "\n".join(func_lines)
        
        # Extract parameters
        parameters = {}
        for arg in node.args.args:
            parameters[arg.arg] = "str"  # Default type
        
        # Extract docstring
        docstring = ast.get_docstring(node)
        
        # Extract dependencies (imports used)
        dependencies = self._extract_dependencies_from_code(func_content)
        
        # Try to extract return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
        
        return CodeChunk(
            name=node.name,
            chunk_type="function",
            content=func_content,
            start_line=start_line,
            end_line=end_line,
            language=language,
            docstring=docstring,
            dependencies=dependencies,
            parameters=parameters,
            return_type=return_type,
        )
    
    def _parse_class(self, node: ast.ClassDef, content: str, lines: List[str], language: str, file_path: str) -> Optional[CodeChunk]:
        """Parse class definition"""
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        
        # Extract class content
        class_lines = lines[start_line - 1:end_line]
        class_content = "\n".join(class_lines)
        
        # Extract docstring
        docstring = ast.get_docstring(node)
        
        # Extract dependencies
        dependencies = self._extract_dependencies_from_code(class_content)
        
        # Count methods
        method_count = sum(1 for item in node.body if isinstance(item, ast.FunctionDef))
        
        return CodeChunk(
            name=node.name,
            chunk_type="class",
            content=class_content,
            start_line=start_line,
            end_line=end_line,
            language=language,
            docstring=docstring,
            dependencies=dependencies,
            parameters={"methods": method_count},
        )
    
    def _extract_dependencies_from_code(self, code: str) -> List[str]:
        """Extract external dependencies mentioned in code"""
        dependencies = []
        
        # Simple regex-based extraction
        import_pattern = r"from\s+(\w+)|import\s+(\w+)"
        matches = re.findall(import_pattern, code)
        
        for match in matches:
            dep = match[0] or match[1]
            if dep and dep not in ["os", "sys", "re", "json", "datetime"]:  # Skip stdlib
                dependencies.append(dep)
        
        return list(set(dependencies))[:5]  # Limit to 5


class JavaScriptCodeParser:
    """Parses JavaScript code using regex (simplified)"""
    
    def parse(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Parse JavaScript code and extract chunks"""
        chunks = []
        lines = content.split("\n")
        
        # Extract functions
        function_pattern = r"(?:async\s+)?function\s+(\w+)\s*\((.*?)\)\s*\{|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>"
        
        for match in re.finditer(function_pattern, content):
            func_name = match.group(1) or match.group(3)
            params = match.group(2) or match.group(4)
            start_pos = content[:match.start()].count("\n") + 1
            
            # Find end of function
            end_pos = start_pos + 5  # Simple approximation
            
            chunk = CodeChunk(
                name=func_name,
                chunk_type="function",
                content="\n".join(lines[start_pos - 1:end_pos]),
                start_line=start_pos,
                end_line=end_pos,
                language=language,
                parameters={"params": params},
            )
            chunks.append(chunk)
        
        # Extract classes
        class_pattern = r"class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{"
        
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            extends = match.group(2)
            start_pos = content[:match.start()].count("\n") + 1
            end_pos = start_pos + 10
            
            chunk = CodeChunk(
                name=class_name,
                chunk_type="class",
                content="\n".join(lines[start_pos - 1:end_pos]),
                start_line=start_pos,
                end_line=end_pos,
                language=language,
                parameters={"extends": extends} if extends else {},
            )
            chunks.append(chunk)
        
        return chunks


class TypeScriptCodeParser(JavaScriptCodeParser):
    """Parses TypeScript code (extends JavaScript parser)"""
    
    def parse(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Parse TypeScript code"""
        # Use JavaScript parser but note it's TypeScript
        chunks = super().parse(content, file_path, language)
        
        # Extract interfaces
        interface_pattern = r"interface\s+(\w+)\s*\{"
        for match in re.finditer(interface_pattern, content):
            interface_name = match.group(1)
            start_pos = content[:match.start()].count("\n") + 1
            end_pos = start_pos + 5
            lines = content.split("\n")
            
            chunk = CodeChunk(
                name=interface_name,
                chunk_type="interface",
                content="\n".join(lines[start_pos - 1:end_pos]),
                start_line=start_pos,
                end_line=end_pos,
                language=language,
            )
            chunks.append(chunk)
        
        return chunks


class JavaCodeParser:
    """Parses Java code using regex (simplified)"""
    
    def parse(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Parse Java code and extract chunks"""
        chunks = []
        lines = content.split("\n")
        
        # Extract classes
        class_pattern = r"(?:public|private|protected)?\s*class\s+(\w+)(?:\s+extends\s+(\w+))?"
        
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            extends = match.group(2)
            start_pos = content[:match.start()].count("\n") + 1
            
            chunk = CodeChunk(
                name=class_name,
                chunk_type="class",
                content="\n".join(lines[start_pos - 1:min(start_pos + 15, len(lines))]),
                start_line=start_pos,
                end_line=min(start_pos + 15, len(lines)),
                language=language,
                parameters={"extends": extends} if extends else {},
            )
            chunks.append(chunk)
        
        return chunks


class CSharpCodeParser:
    """Parses C# code using regex (simplified)"""
    
    def parse(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Parse C# code and extract chunks"""
        chunks = []
        lines = content.split("\n")
        
        # Extract classes
        class_pattern = r"(?:public|private|internal)?\s*class\s+(\w+)(?:\s*:\s*(\w+))?"
        
        for match in re.finditer(class_pattern, content):
            class_name = match.group(1)
            inherits = match.group(2)
            start_pos = content[:match.start()].count("\n") + 1
            
            chunk = CodeChunk(
                name=class_name,
                chunk_type="class",
                content="\n".join(lines[start_pos - 1:min(start_pos + 15, len(lines))]),
                start_line=start_pos,
                end_line=min(start_pos + 15, len(lines)),
                language=language,
                parameters={"inherits": inherits} if inherits else {},
            )
            chunks.append(chunk)
        
        return chunks
