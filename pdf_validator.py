import subprocess
import os
import uuid
from typing import Optional


class PDFValidationError(Exception):
    pass


class PDFValidator:
    def __init__(self, max_size_mb: int = 100, max_pages: int = 50):
        self.max_size_mb = max_size_mb
        self.max_pages = max_pages
        self.env = {**os.environ, "LC_ALL": "C"}

    def _run_cmd(self, cmd: list, timeout: int = 10) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self.env,
            )
        except FileNotFoundError:
            raise PDFValidationError(f"'{cmd[0]}'가 설치되어 있지 않습니다.")
        except subprocess.TimeoutExpired:
            raise PDFValidationError(f"'{cmd[0]}' 실행 시간 초과")

    def is_encrypted(self, file_path: str) -> bool:
        result = self._run_cmd(["qpdf", "--is-encrypted", file_path])
        return result.returncode == 0

    def decrypt(self, input_path: str, password: str, output_path: str) -> bool:
        result = self._run_cmd([
            "qpdf",
            f"--password={password}",
            "--decrypt",
            input_path,
            output_path,
        ])
        return result.returncode == 0 and os.path.exists(output_path)

    def check_magic_number(self, file_path: str):
        with open(file_path, "rb") as f:
            header = f.read(16)
        if b"%PDF-" not in header[:10]:
            raise PDFValidationError(
                f"유효하지 않은 PDF 헤더 (hex: {header.hex()})"
            )

    def check_file_size(self, file_path: str):
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > self.max_size_mb:
            raise PDFValidationError(
                f"파일 크기 제한 초과: {size_mb:.1f}MB (최대 {self.max_size_mb}MB)"
            )

    def check_page_count(self, file_path: str) -> int:
        result = self._run_cmd(["pdfinfo", file_path])
        if result.returncode != 0:
            raise PDFValidationError(
                f"pdfinfo 실행 실패: {result.stderr.strip()}"
            )

        pages = None
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                try:
                    pages = int(line.split(":")[1].strip())
                except (ValueError, IndexError):
                    raise PDFValidationError(f"페이지 수 파싱 실패: {line!r}")
                break

        if pages is None:
            raise PDFValidationError("페이지 수를 확인할 수 없습니다.")
        if pages < 1:
            raise PDFValidationError("페이지가 없는 PDF입니다.")
        if pages > self.max_pages:
            raise PDFValidationError(
                f"페이지 수 제한 초과: {pages} (최대 {self.max_pages})"
            )

        return pages

    def check_structure(self, file_path: str):
        result = self._run_cmd(["qpdf", "--check", file_path])
        if result.returncode not in (0, 3):
            raise PDFValidationError(
                f"구조 오류 (code={result.returncode}): "
                f"{result.stderr.strip()[:200]}"
            )

    def validate(self, file_path: str, password: Optional[str] = None) -> int:
        self.check_magic_number(file_path)
        self.check_file_size(file_path)

        if self.is_encrypted(file_path):
            if not password:
                raise PDFValidationError("암호화된 PDF입니다. 비밀번호를 입력하세요.")
            temp_path = f"/tmp/decrypted_{uuid.uuid4().hex}.pdf"
            try:
                if not self.decrypt(file_path, password, temp_path):
                    raise PDFValidationError("비밀번호가 올바르지 않습니다.")
                file_path = temp_path
            except PDFValidationError:
                raise
            except Exception as e:
                raise PDFValidationError(f"복호화 실패: {str(e)}")

        try:
            pages = self.check_page_count(file_path)
            self.check_structure(file_path)
            return pages
        finally:
            if password and os.path.exists(temp_path):
                os.remove(temp_path)


validator = PDFValidator()
