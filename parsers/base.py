"""BaseParser - 모든 파서의 추상 기반 클래스"""
from abc import ABC, abstractmethod
from typing import List, Optional
import pdfplumber
from .ir import DocumentIR


class BaseParser(ABC):
    """문서 파서 추상 기반 클래스
    
    모든 문서 유형 파서는 이 클래스를 상속해야 합니다.
    
    사용 예:
        @register_parser("이수증")
        class CertificateParser(BaseParser):
            doc_type = "이수증"
            fields = ["성명", "생년월일", "직급", ...]
            
            def parse(self, text: str, **kwargs) -> DocumentIR:
                # 파싱 로직 구현
                ...
    """
    
    # 파서 식별자 (하위 클래스에서 오버라이드)
    doc_type: str = "unknown"
    
    # 이 문서 유형의 필드 목록 (하위 클래스에서 오버라이드)
    fields: List[str] = []
    
    # 필드별 검증 규칙 (선택사항)
    field_validators: dict = {}
    
    def __init__(self):
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
                tables.extend(page.extract_tables())
        return tables
    
    def get_page_count(self, file_path: str) -> int:
        """PDF 페이지 수 반환"""
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    
    @abstractmethod
    def parse(self, text: str, **kwargs) -> DocumentIR:
        """텍스트를 파싱하여 DocumentIR 반환
        
        Args:
            text: PDF에서 추출한 텍스트 (-layout 모드)
            **kwargs: 추가 파라미터 (institution 등)
        
        Returns:
            DocumentIR: 파싱 결과
        """
        pass
    
    def detect(self, text: str) -> bool:
        """텍스트가 이 문서 유형인지 감지
        
        Args:
            text: PDF에서 추출한 텍스트
        
        Returns:
            bool: 이 유형이면 True
        """
        return True
    
    def validate(self, ir: DocumentIR) -> List[str]:
        """파싱 결과 검증
        
        Args:
            ir: 파싱된 DocumentIR
        
        Returns:
            List[str]: 경고 메시지 목록
        """
        warnings = []
        
        # 필수 필드 확인
        for field in self.fields:
            if not ir.has_field(field):
                warnings.append(f"필수 필드 누락: {field}")
        
        # 필드별 검증
        for field, validator in self.field_validators.items():
            if ir.has_field(field):
                value = ir.get(field)
                if not validator(value):
                    warnings.append(f"필드 검증 실패: {field} = {value}")
        
        return warnings
    
    def get_fields(self) -> List[str]:
        """이 문서 유형의 필드 목록 반환"""
        return self.fields.copy()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} doc_type='{self.doc_type}'>"
