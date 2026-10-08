from typing import List, Dict
import pandas as pd
import re
from .base import BaseParser


class RosterParser(BaseParser):
    """명단 파서"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """명단 PDF를 파싱하여 DataFrame 반환"""
        tables = self.extract_tables(file_path)
        
        if not tables:
            # 테이블이 없으면 텍스트에서 추출
            text = self.extract_text(file_path)
            return self._parse_from_text(text)
        
        # 첫 번째 테이블 사용
        data = tables[0]
        if not data:
            return pd.DataFrame()
        
        # 헤더 추출 시도
        headers = data[0] if data else []
        rows = data[1:] if len(data) > 1 else []
        
        # 빈 헤더 처리
        headers = [str(h).strip() if h else f"컬럼_{i+1}" for i, h in enumerate(headers)]
        
        return pd.DataFrame(rows, columns=headers)
    
    def _parse_from_text(self, text: str) -> pd.DataFrame:
        """텍스트에서 명단 데이터 추출"""
        lines = text.split('\n')
        data = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 이름 패턴 매칭 (한글 이름)
            name_match = re.search(r'[가-힣]{2,4}', line)
            if name_match:
                # 전화번호 추출
                phone_match = re.search(r'(\d{3}-\d{3,4}-\d{4}|\d{11})', line)
                phone = phone_match.group(1) if phone_match else ""
                
                # 이메일 추출
                email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', line)
                email = email_match.group(0) if email_match else ""
                
                data.append({
                    '이름': name_match.group(0),
                    '전화번호': phone,
                    '이메일': email,
                    '원문': line
                })
        
        if not data:
            # 패턴 매칭 실패 시 전체 텍스트를 단일 레코드로
            return pd.DataFrame([{'텍스트': text}])
        
        return pd.DataFrame(data)
