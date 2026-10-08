"""기본 정규화기 - pdftotext -layout용"""
import re
import unicodedata


class TextNormalizer:
    """pdftotext -layout 추출 텍스트를 파싱에 적합하도록 정규화"""

    LABEL_KEYWORDS = [
        "성명", "생년월일", "직급", "근무기관", "과정명",
        "연수기간", "연수종류", "이수시간", "이수번호", "수료일",
        "기관", "기간", "종류", "시간",
    ]

    def normalize(self, text: str, institution: str = None) -> str:
        text = unicodedata.normalize('NFC', text)
        return self._normalize_layout_text(text)

    def _normalize_layout_text(self, text: str) -> str:
        lines = text.split('\n')
        normalized = []

        for line in lines:
            line = line.strip()
            if not line:
                normalized.append('')
                continue

            if ':' in line or '：' in line:
                parts = re.split(r'[:：]', line, maxsplit=1)
                if len(parts) == 2:
                    label = parts[0].replace(' ', '').replace('\t', '')
                    value = parts[1].strip()
                    normalized.append(f"{label}:{value}")
                else:
                    normalized.append(line.replace(' ', ''))
            else:
                normalized.append(line)

        return '\n'.join(normalized)

    def parse_label_value_pairs(self, text: str) -> dict:
        result = {}
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line or ':' not in line:
                continue

            parts = re.split(r'[:：]', line, maxsplit=1)
            if len(parts) != 2:
                continue

            label = parts[0].replace(' ', '').replace('\t', '')
            value = parts[1].strip()

            for kw in self.LABEL_KEYWORDS:
                if label == kw:
                    result[kw] = value
                    break

        return result
