"""Azure Document Intelligence 파서"""
import os
import re
from typing import List, Optional
from .base import BaseParser
from .ir import DocumentIR
from .registry import parser_registry


@parser_registry.register("azure_di")
class AzureDIParser(BaseParser):
    """Azure Document Intelligence 기반 파서
    
    Azure DI를 사용하여 PDF에서 텍스트, 테이블, 키-값 쌍을 추출합니다.
    스캔 PDF, 복잡한 레이아웃에 적합합니다.
    """
    
    doc_type = "azure_di"
    fields = []  # Azure DI는 범용적이므로 필드를 하드코딩하지 않음
    
    def __init__(self):
        super().__init__()
        self._client = None
        self._enabled = False
        
        # Azure 설정 확인
        self.endpoint = os.getenv("DOCUMENTINTELLIGENCE_ENDPOINT")
        self.api_key = os.getenv("DOCUMENTINTELLIGENCE_API_KEY")
        
        if self.endpoint and self.api_key:
            self._enabled = True
    
    def _get_client(self):
        """Azure DI 클라이언트 가져오기 (지연 초기화)"""
        if self._client is None:
            if not self._enabled:
                raise ValueError(
                    "Azure Document Intelligence가 설정되지 않았습니다. "
                    "DOCUMENTINTELLIGENCE_ENDPOINT와 DOCUMENTINTELLIGENCE_API_KEY를 설정하세요."
                )
            
            from azure.core.credentials import AzureKeyCredential
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            
            self._client = DocumentIntelligenceClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key)
            )
        
        return self._client
    
    def detect(self, text: str) -> bool:
        """Azure DI는 모든 문서 유형에 사용 가능"""
        return False  # 자동 감지에서는 사용하지 않음 (수동 선택용)
    
    def parse(self, text: str = None, **kwargs) -> DocumentIR:
        """Azure DI를 사용하여 PDF 파싱
        
        Args:
            text: 사용하지 않음 (PDF 바이트 사용)
            **kwargs:
                pdf_bytes: PDF 바이트 데이터 (필수)
                model: Azure DI 모델 (기본값: "prebuilt-read")
        
        Returns:
            DocumentIR: 파싱 결과
        """
        pdf_bytes = kwargs.get("pdf_bytes")
        if pdf_bytes is None:
            raise ValueError("pdf_bytes 인자가 필요합니다.")
        
        model = kwargs.get("model", "prebuilt-read")
        
        client = self._get_client()
        
        # Azure DI 분석 실행
        try:
            poller = client.begin_analyze_document(
                model_id=model,
                body=pdf_bytes
            )
            result = poller.result()
        except Exception as e:
            raise RuntimeError(f"Azure DI 분석 실패: {str(e)}")
        
        # 결과를 DocumentIR로 변환
        return self._convert_result(result, text)
    
    def parse_file(self, file_path: str, model: str = "prebuilt-read") -> DocumentIR:
        """파일 경로에서 직접 파싱
        
        Args:
            file_path: PDF 파일 경로
            model: Azure DI 모델
        
        Returns:
            DocumentIR: 파싱 결과
        """
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
        
        return self.parse(pdf_bytes=pdf_bytes, model=model)
    
    def _convert_result(self, result, raw_text: str = None) -> DocumentIR:
        """Azure DI 결과를 DocumentIR로 변환"""
        fields = {}
        warnings = []
        
        # 전체 텍스트 추출
        full_text = result.content if hasattr(result, 'content') else ""
        
        # 페이지별 텍스트
        pages_text = []
        if result.pages:
            for page in result.pages:
                page_lines = []
                if page.lines:
                    for line in page.lines:
                        page_lines.append(line.content)
                pages_text.append("\n".join(page_lines))
        
        # 테이블 추출
        tables = []
        if result.tables:
            for table in result.tables:
                table_data = []
                for cell in table.cells:
                    table_data.append({
                        "row": cell.row_index,
                        "col": cell.column_index,
                        "text": cell.content
                    })
                tables.append(table_data)
        
        # 키-값 쌍 추출 (prebuilt-model 사용 시)
        if result.documents:
            for doc in result.documents:
                if doc.fields:
                    for key, field in doc.fields.items():
                        if field.value:
                            fields[key] = str(field.value)
        
        # DocumentIR 생성
        ir = DocumentIR(
            doc_type="azure_di",
            fields=fields,
            raw_text=raw_text or full_text,
            metadata={
                "azure_di_model": "prebuilt-read",
                "page_count": len(result.pages) if result.pages else 0,
                "table_count": len(result.tables) if result.tables else 0,
                "full_text": full_text,
                "pages_text": pages_text,
                "tables": tables,
            }
        )
        
        return ir
    
    def parse_layout(self, pdf_bytes: bytes) -> DocumentIR:
        """레이아웃 분석 (테이블, 구조 추출)"""
        return self.parse(pdf_bytes=pdf_bytes, model="prebuilt-layout")
    
    def parse_read(self, pdf_bytes: bytes) -> DocumentIR:
        """텍스트 추출 (빠름)"""
        return self.parse(pdf_bytes=pdf_bytes, model="prebuilt-read")
    
    def is_enabled(self) -> bool:
        """Azure DI 사용 가능 여부"""
        return self._enabled
    
    def get_status(self) -> dict:
        """Azure DI 상태 정보"""
        return {
            "enabled": self._enabled,
            "endpoint": self.endpoint,
            "has_api_key": bool(self.api_key),
        }
