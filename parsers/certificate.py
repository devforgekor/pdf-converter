"""이수증 파서 - 레지스트리 기반"""
import re
from typing import List
from .base import BaseParser
from .ir import DocumentIR
from .registry import parser_registry
from text_normalizer import normalizer


@parser_registry.register("이수증")
class CertificateParser(BaseParser):
    """이수증 파서 - pdftotext -layout 기반"""
    
    doc_type = "이수증"
    fields = [
        "성명", "생년월일", "직급", "근무기관", "과정명",
        "연수기간", "연수종류", "이수시간", "이수번호", "수료일"
    ]
    
    # 기관 패턴
    INSTITUTION_PATTERNS = {
        "서울교육연수원": [r"서울교육연수원", r"서울.*교육연수원"],
        "한국교원단체총연합회": [r"교원단체총연합회", r"교총"],
        "서울특별시교육청": [r"서울특별시교육청", r"서울시교육청"],
        "경기도교육청": [r"경기도교육청"],
        "한국장애인단체총연합회": [r"장애인단체총연합회", r"한국장애인단체"],
    }
    
    # 필드별 값 검증 규칙
    FIELD_VALIDATORS = {
        "성명": lambda v: bool(re.match(r'^[가-힣]{2,4}$', v)) if v else False,
        "생년월일": lambda v: bool(re.match(r'\d{2}\.\d{2}\.\d{2}', v)) if v else False,
        "직급": lambda v: any(k in v for k in ["교사", "교수", "원장", "과장", "주임", "부장"]) if v else False,
        "근무기관": lambda v: any(k in v for k in ["학교", "교육청", "기관", "단체"]) if v else False,
    }
    
    def __init__(self):
        super().__init__()
        self.field_validators = self.FIELD_VALIDATORS
    
    def detect(self, text: str) -> bool:
        """이수증 여부 감지"""
        # 이수증 관련 키워드 확인
        keywords = ["이수증", "수료증", "교육훈련"]
        return any(kw in text for kw in keywords)
    
    def detect_institution(self, text: str) -> str:
        """기관 감지"""
        for institution, patterns in self.INSTITUTION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    return institution
        return "기타"
    
    def parse(self, text: str, **kwargs) -> DocumentIR:
        """텍스트 파싱"""
        # 1단계: 기관 감지 (정규화 전)
        institution = self.detect_institution(text)
        
        # 2단계: 텍스트 정규화
        normalized = normalizer.normalize(text, institution)
        
        # 3단계: 라벨:값 쌍 추출
        pairs = normalizer.parse_label_value_pairs(normalized)
        
        # 4단계: 이수번호 추출 (제목 라인에서)
        lines = normalized.split('\n')
        for line in lines:
            match = re.search(r'제\s+(\S+)\s*호', line)
            if match:
                pairs["이수번호"] = match.group(1)
                break
        
        # 5단계: 필드 매핑
        field_map = {
            "성명": "성명",
            "생년월일": "생년월일",
            "직급": "직급",
            "근무기관": "근무기관",
            "연수기간": "연수기간",
            "연수종류": "연수종류",
            "이수시간": "이수시간",
            "이수번호": "이수번호",
        }
        
        result = {}
        for key, pair_key in field_map.items():
            if pair_key in pairs:
                value = pairs[pair_key]
                # 값 정리
                if key == "이수시간":
                    match = re.search(r'(\d+)', value)
                    if match:
                        value = match.group(1)
                elif key == "근무기관":
                    value = value.replace(' ', '')
                elif key == "연수종류":
                    value = value.replace(' ', '')
                result[key] = value
        
        # 과정명 추출 (라벨 다음 줄 포함)
        for i, line in enumerate(lines):
            if '과정명:' in line:
                parts = line.split('과정명:', 1)
                if len(parts) == 2:
                    course_name = parts[1].strip()
                    # 다음 줄이 있으면 합치기
                    if i + 1 < len(lines) and lines[i + 1].strip():
                        next_line = lines[i + 1].strip()
                        if not any(kw in next_line for kw in ['성명:', '생년월일:', '직급:', '근무기관:']):
                            course_name += next_line
                    result["과정명"] = course_name
                break
        
        # 수료일 추출 (날짜 형식: YYYY년 M월 D일)
        for line in lines:
            match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', line)
            if match:
                year = match.group(1)
                month = match.group(2).zfill(2)
                day = match.group(3).zfill(2)
                result["수료일"] = f"{year}.{month}.{day}."
                break
        
        # 기관 설정
        result["기관"] = institution
        
        # DocumentIR 생성
        ir = DocumentIR(
            doc_type=self.doc_type,
            fields=result,
            raw_text=text,
            metadata={"institution": institution}
        )
        
        # 검증
        warnings = self.validate(ir)
        ir.warnings = warnings
        
        return ir
    
    def get_fields(self) -> List[str]:
        """이수증 필드 목록 반환"""
        return self.fields.copy()
