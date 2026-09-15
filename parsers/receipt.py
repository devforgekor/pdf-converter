from typing import List, Dict
import pandas as pd
import re
from .base import BaseParser


class ReceiptParser(BaseParser):
    """영수증 파서"""
    
    def parse(self, file_path: str) -> pd.DataFrame:
        """영수증 PDF를 파싱하여 DataFrame 반환"""
        text = self.extract_text(file_path)
        return self._parse_receipt(text)
    
    def _parse_receipt(self, text: str) -> pd.DataFrame:
        """영수증 텍스트 파싱"""
        data = {
            '항목': [],
            '수량': [],
            '단가': [],
            '금액': []
        }
        
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 금액 패턴 매칭 (원, ₩,krw 등)
            amount_pattern = r'[\d,]+[원₩]?\s*$'
            amount_match = re.search(amount_pattern, line)
            
            if amount_match:
                # 상품명과 금액 분리
                amount_str = amount_match.group(0)
                item_part = line[:amount_match.start()].strip()
                
                # 수량 추출
                qty_match = re.search(r'(\d+)\s*[개장đ份]', item_part)
                qty = qty_match.group(1) if qty_match else '1'
                
                # 상품명 정리
                item_name = re.sub(r'\d+\s*[개장đ份]\s*', '', item_part).strip()
                
                # 금액 정리
                amount = re.sub(r'[^\d]', '', amount_str)
                
                if item_name and amount:
                    data['항목'].append(item_name)
                    data['수량'].append(qty)
                    data['단가'].append('')
                    data['금액'].append(amount)
        
        if not data['항목']:
            # 파싱 실패 시 전체 텍스트 반환
            return pd.DataFrame([{'텍스트': text}])
        
        return pd.DataFrame(data)
