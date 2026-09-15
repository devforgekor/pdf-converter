from typing import Optional
import re
import pdfplumber


class PDFTypeDetector:
    """PDF 유형 감지기"""
    
    # 키워드 기반 유형 감지
    KEYWORDS = {
        'roster': ['명단', '참석', '출석', '부서', '소속', '직급', '연락처', '전화번호'],
        'receipt': ['영수증', '매출전표', '결제', '금액', '합계', '부가세', '카드', '현금'],
        'certificate': ['이수증', '수료증', '수료', '이수', '교육명', '발급기관', '자격번호'],
    }
    
    def detect(self, file_path: str) -> str:
        """PDF 유형 감지"""
        text = self._extract_text(file_path)
        return self._detect_from_text(text)
    
    def _extract_text(self, file_path: str) -> str:
        """PDF에서 텍스트 추출"""
        text = ""
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print(f"텍스트 추출 오류: {e}")
        return text
    
    def _detect_from_text(self, text: str) -> str:
        """텍스트에서 유형 감지"""
        text_lower = text.lower()
        
        scores = {}
        for pdf_type, keywords in self.KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            scores[pdf_type] = score
        
        # 가장 높은 점수의 유형 반환
        if scores:
            max_type = max(scores, key=scores.get)
            if scores[max_type] > 0:
                return max_type
        
        # 기본값: 명단
        return 'roster'
