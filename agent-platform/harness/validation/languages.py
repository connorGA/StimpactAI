from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Protocol

from harness.schemas.editing import ValidationResult


REPO_ROOT = Path(__file__).resolve().parents[3]
CLIENT_UI_ROOT = REPO_ROOT / "client-ui"
TYPESCRIPT_COMPILER_PATH = CLIENT_UI_ROOT / "node_modules" / "typescript" / "lib" / "typescript.js"

PYTHON_SUFFIXES = {".py"}
JAVASCRIPT_SUFFIXES = {".js", ".jsx", ".cjs", ".mjs"}
TYPESCRIPT_SUFFIXES = {".ts", ".tsx"}
SUPPORTED_SUFFIXES = PYTHON_SUFFIXES | JAVASCRIPT_SUFFIXES | TYPESCRIPT_SUFFIXES


class LanguageValidator(Protocol):
    language: str
    validator_name: str

    def validate_file(self, path: Path) -> ValidationResult: ...


class PythonValidator:
    language = "python"
    validator_name = "python-compile"

    def validate_file(self, path: Path) -> ValidationResult:
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            message = exc.msg or "Python syntax validation failed."
            output = f"{path}:{exc.lineno}:{exc.offset}: {message}"
            return ValidationResult(
                ok=False,
                language=self.language,
                validator=self.validator_name,
                output=output,
                message=message,
            )
        return ValidationResult(
            ok=True,
            language=self.language,
            validator=self.validator_name,
            output="Python syntax validation passed.",
            message="Validation passed.",
        )


class ScriptSyntaxValidator:
    language = "javascript-typescript"
    validator_name = "typescript-transpile-module"

    def validate_file(self, path: Path) -> ValidationResult:
        if not TYPESCRIPT_COMPILER_PATH.exists():
            return ValidationResult(
                ok=False,
                language=self.language,
                validator=self.validator_name,
                output="TypeScript compiler was not found under client-ui/node_modules.",
                message="TypeScript compiler is unavailable.",
            )

        script = """
const fs = require("fs");
const ts = require(process.argv[1]);
const filePath = process.argv[2];
const source = fs.readFileSync(filePath, "utf8");
const lowerPath = filePath.toLowerCase();
let scriptKind = ts.ScriptKind.Unknown;
if (lowerPath.endsWith(".tsx")) scriptKind = ts.ScriptKind.TSX;
else if (lowerPath.endsWith(".ts")) scriptKind = ts.ScriptKind.TS;
else if (lowerPath.endsWith(".jsx")) scriptKind = ts.ScriptKind.JSX;
else scriptKind = ts.ScriptKind.JS;
const result = ts.transpileModule(source, {
  fileName: filePath,
  reportDiagnostics: true,
  compilerOptions: {
    allowJs: true,
    checkJs: false,
    jsx: ts.JsxEmit.ReactJSX,
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ESNext
  }
});
const diagnostics = (result.diagnostics || []).map((diagnostic) => {
  const message = ts.flattenDiagnosticMessageText(diagnostic.messageText, "\\n");
  if (!diagnostic.file || typeof diagnostic.start !== "number") {
    return message;
  }
  const position = diagnostic.file.getLineAndCharacterOfPosition(diagnostic.start);
  return `${diagnostic.file.fileName}:${position.line + 1}:${position.character + 1}: ${message}`;
});
console.log(JSON.stringify({ ok: diagnostics.length === 0, diagnostics }));
"""
        try:
            completed = subprocess.run(
                [
                    "node",
                    "-e",
                    script,
                    str(TYPESCRIPT_COMPILER_PATH),
                    str(path),
                ],
                cwd=REPO_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            output = exc.stderr.strip() or exc.stdout.strip() or "TypeScript validation execution failed."
            return ValidationResult(
                ok=False,
                language=self.language,
                validator=self.validator_name,
                output=output,
                message="TypeScript validation execution failed.",
            )

        try:
            payload = json.loads(completed.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return ValidationResult(
                ok=False,
                language=self.language,
                validator=self.validator_name,
                output=completed.stdout.strip(),
                message="TypeScript validation returned an invalid payload.",
            )

        diagnostics = payload.get("diagnostics", [])
        if payload.get("ok") is True:
            return ValidationResult(
                ok=True,
                language=self.language,
                validator=self.validator_name,
                output="Script syntax validation passed.",
                message="Validation passed.",
            )
        output = "\n".join(str(item) for item in diagnostics)
        return ValidationResult(
            ok=False,
            language=self.language,
            validator=self.validator_name,
            output=output,
            message="Script syntax validation failed.",
        )


def get_validator_for_path(path: Path) -> LanguageValidator | None:
    suffix = path.suffix.lower()
    if suffix in PYTHON_SUFFIXES:
        return PythonValidator()
    if suffix in JAVASCRIPT_SUFFIXES or suffix in TYPESCRIPT_SUFFIXES:
        return ScriptSyntaxValidator()
    return None
