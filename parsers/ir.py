"""Document IR - 모든 파서가 생성하는 공통 중간 포맷"""
from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class DocumentIR:
    """문서 중간 표현 (Intermediate Representation)
    
    모든 파서가 이 포맷으로 출력하고,
    ExcelExporter, 검증 API 등이 이 포맷을 입력으로 받음
    """
    doc_type: str                          # "이수증", "학적", etc.
    fields: dict = field(default_factory=dict)  # {"성명": "김동윤", ...}
    raw_text: str = ""                     # 원본 텍스트
    confidence: float = 1.0                # 파싱 신뢰도 (0~1)
    warnings: list = field(default_factory=list)  # 경고 메시지
    metadata: dict = field(default_factory=dict)  # 추가 메타데이터

    def get(self, key: str, default=None) -> Optional[str]:
        """필드 값 가져오기"""
        return self.fields.get(key, default)

    def set(self, key: str, value: str):
        """필드 값 설정"""
        self.fields[key] = value

    def has_field(self, key: str) -> bool:
        """필드 존재 여부"""
        return key in self.fields

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "doc_type": self.doc_type,
            "fields": self.fields,
            "confidence": self.confidence,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> 'DocumentIR':
        """딕셔너리에서 생성"""
        return cls(
            doc_type=data.get("doc_type", "unknown"),
            fields=data.get("fields", {}),
            confidence=data.get("confidence", 1.0),
            warnings=data.get("warnings", []),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> 'DocumentIR':
        """JSON 문자열에서 생성"""
        return cls.from_dict(json.loads(json_str))
