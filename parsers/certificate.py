from typing import List, Dict
import pandas as pd
import re
from .base import BaseParser


class CertificateParser(BaseParser):
    """이수증 파서"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """이수증 PDF를 파싱하여 DataFrame 반환"""
        text = self.extract_text(file_path)
        return self._parse_certificate(text)
    
    def _parse_certificate(self, text: str) -> pd.DataFrame:
        """이수증 텍스트 파싱"""
        data = {}
        
        # 필드 추출 패턴
        patterns = {
            '교육명': r'교육명?\s*[:：]\s*(.+)',
            '교육일시': r'교육일시?\s*[:：]\s*(.+)',
            '교육기간': r'교육기간\s*[:：]\s*(.+)',
            '수료자': r'수료자?\s*[:：]\s*(.+)',
            '생년월일': r'생년월일\s*[:：]\s*(.+)',
            '발급일': r'발급일?\s*[:：]\s*(.+)',
            '발급기관': r'발급기관\s*[:：]\s*(.+)',
            '자격번호': r'자격번호\s*[:：]\s*(.+)',
            '성명': r'성명\s*[:：]\s*(.+)',
            '이름': r'이름\s*[:：]\s*(.+)',
        }
        
        for field_name, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                data[field_name] = [match.group(1).strip()]
        
        if not data:
            # 패턴 매칭 실패 시 전체 텍스트 반환
            return pd.DataFrame([{'텍스트': text}])
        
        return pd.DataFrame(data)
