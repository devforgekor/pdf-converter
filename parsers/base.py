from abc import ABC, abstractmethod
from typing import Any, Dict, List
import pdfplumber
import pandas as pd


class BaseParser(ABC):
    """베이스 파서 클래스"""
    
    @abstractmethod
    def parse(self, file_path: str) -> pd.DataFrame:
        """PDF를 파싱하여 DataFrame 반환"""
        pass
    
    def extract_text(self, file_path: str) -> str:
        """PDF에서 텍스트 추출"""
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text
    
    def extract_tables(self, file_path: str) -> List[List[List[str]]]:
        """PDF에서 테이블 추출"""
        tables = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                tables.extend(page_tables)
        return tables
    
    def get_page_count(self, file_path: str) -> int:
        """PDF 페이지 수 반환"""
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
