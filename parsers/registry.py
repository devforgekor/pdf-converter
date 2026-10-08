"""
Parser Registry - 문서 유형별 파서 등록/관리

참조 소스:
- 플러그인/레지스트리 패턴: Flask Blueprints, py-pdf-parser (https://github.com/jstockwin/py-pdf-parser)
- DocumentIR (중간 표현) 패턴: Apache Tika, 문서 처리 프레임워크의 일반적 아키텍처
"""
from typing import Dict, List, Optional, Type
from .base import BaseParser


class ParserRegistry:
    """파서 레지스트리 - 문서 유형별 파서 관리
    
    사용 예:
        # 파서 등록
        @parser_registry.register("이수증")
        class CertificateParser(BaseParser):
            ...
        
        # 파서 가져오기
        parser = parser_registry.get("이수증")
        
        # 모든 문서 유형 목록
        types = parser_registry.list_types()
    """
    
    def __init__(self):
        self._parsers: Dict[str, BaseParser] = {}
        self._parser_classes: Dict[str, Type[BaseParser]] = {}
    
    def register(self, doc_type: str):
        """파서 등록 데코레이터
        
        Args:
            doc_type: 문서 유형 식별자 ("이수증", "학적", etc.)
        
        Usage:
            @parser_registry.register("이수증")
            class CertificateParser(BaseParser):
                ...
        """
        def decorator(parser_class: Type[BaseParser]):
            if doc_type in self._parser_classes:
                raise ValueError(f"문서 유형 '{doc_type}'이(가) 이미 등록되어 있습니다.")
            
            # 클래스에 doc_type 설정
            parser_class.doc_type = doc_type
            
            # 인스턴스 생성 및 등록
            parser_instance = parser_class()
            self._parsers[doc_type] = parser_instance
            self._parser_classes[doc_type] = parser_class
            
            return parser_class
        
        return decorator
    
    def get(self, doc_type: str) -> Optional[BaseParser]:
        """문서 유형에 해당하는 파서 반환
        
        Args:
            doc_type: 문서 유형 식별자
        
        Returns:
            BaseParser: 파서 인스턴스 (없으면 None)
        """
        return self._parsers.get(doc_type)
    
    def get_class(self, doc_type: str) -> Optional[Type[BaseParser]]:
        """문서 유형에 해당하는 파서 클래스 반환
        
        Args:
            doc_type: 문서 유형 식별자
        
        Returns:
            Type[BaseParser]: 파서 클래스 (없으면 None)
        """
        return self._parser_classes.get(doc_type)
    
    def list_types(self) -> List[str]:
        """등록된 문서 유형 목록 반환"""
        return list(self._parsers.keys())
    
    def list_parsers(self) -> Dict[str, BaseParser]:
        """등록된 모든 파서 반환"""
        return self._parsers.copy()
    
    def detect(self, text: str) -> Optional[str]:
        """텍스트에서 문서 유형 자동 감지
        
        Args:
            text: PDF에서 추출한 텍스트
        
        Returns:
            Optional[str]: 감지된 문서 유형 (없으면 None)
        """
        for doc_type, parser in self._parsers.items():
            if parser.detect(text):
                return doc_type
        return None
    
    def parse(self, doc_type: str, text: str, **kwargs):
        """지정된 문서 유형으로 파싱
        
        Args:
            doc_type: 문서 유형 식별자
            text: PDF에서 추출한 텍스트
            **kwargs: 추가 파라미터
        
        Returns:
            DocumentIR: 파싱 결과
        
        Raises:
            ValueError: 문서 유형이 등록되지 않은 경우
        """
        parser = self.get(doc_type)
        if parser is None:
            raise ValueError(f"문서 유형 '{doc_type}'이(가) 등록되지 않았습니다.")
        
        return parser.parse(text, **kwargs)
    
    def __contains__(self, doc_type: str) -> bool:
        return doc_type in self._parsers
    
    def __len__(self) -> int:
        return len(self._parsers)
    
    def __repr__(self) -> str:
        types = ", ".join(self._parsers.keys())
        return f"<ParserRegistry types=[{types}]>"


# 전역 레지스트리 인스턴스
parser_registry = ParserRegistry()
