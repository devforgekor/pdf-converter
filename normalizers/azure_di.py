"""Azure DI 정규화기"""
import re
import unicodedata
from .base import TextNormalizer


class AzureDINormalizer(TextNormalizer):
    """Azure Document Intelligence 출력 정규화"""

    AZURE_DI_LABEL_MAP = {
        "성": "성명",
        "명": "성명",
        "년 월 일": "생년월일",
        "생 년 월 일": "생년월일",
        "직 급": "직급",
        "근무 기관": "근무기관",
        "과 정 명": "과정명",
        "연 수 기 간": "연수기간",
        "연 수 종 류": "연수종류",
        "이 수 시 간": "이수시간",
        "이 수 번 호": "이수번호",
    }

    def normalize(self, text: str, institution: str = None) -> str:
        text = unicodedata.normalize('NFC', text)
        lines = text.split('\n')
        normalized = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                normalized.append('')
                i += 1
                continue
            
            mapped = False
            for azure_label, standard_label in self.AZURE_DI_LABEL_MAP.items():
                if line.startswith(azure_label):
                    parts = re.split(r'[:：]', line, maxsplit=1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        normalized.append(f"{standard_label}:{value}")
                        mapped = True
                        break
            
            if not mapped:
                # "성" 다음 줄이 "명 : 김동윤"인 경우 처리
                if line == "성" and i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line.startswith("명"):
                        parts = next_line.split(':', 1)
                        if len(parts) == 2:
                            normalized.append(f"성명:{parts[1].strip()}")
                            i += 2
                            continue
                
                # "직 급 : ... 근무 기관 : ..." 처리 (라인이 두 개의 콜론을 포함)
                if '직 급' in line or '근무 기관' in line:
                    # 콜론 기준으로 분리: ['직 급 ', ' 특수학교교사 근무 기관 ', ' 서울특별시교육청 한국구화학교']
                    parts = re.split(r'[:：]', line)
                    if len(parts) >= 3:
                        # 라벨:값 쌍으로 재구성
                        # parts[0] = "직 급 " → label1
                        # parts[1] = " 특수학교교사 근무 기관 " → value1에 "근무 기관"이 섞여있음
                        # parts[2] = " 서울특별시교육청 한국구화학교" → value2
                        
                        label1 = parts[0].replace(' ', '')
                        
                        # value1에서 "근무 기관" 부분을 찾아 분리
                        value1_raw = parts[1].strip()
                        if '근무 기관' in value1_raw:
                            value1 = value1_raw.split('근무 기관')[0].strip()
                        else:
                            value1 = value1_raw
                        
                        normalized.append(f"{label1}:{value1}")
                        
                        # 근무기관: value는 parts[2]
                        value2 = parts[2].strip()
                        normalized.append(f"근무기관:{value2}")
                        i += 1
                        continue
                
                # "연연이 수수수" 같은 깨진 라벨 처리
                if re.match(r'^연연이\s*수수수$', line):
                    # 다음 줄들에서 "기간:", "류:", "간:" 추출
                    i += 1
                    while i < len(lines):
                        sub_line = lines[i].strip()
                        if sub_line.startswith('기간'):
                            parts = sub_line.split(':', 1)
                            if len(parts) == 2:
                                normalized.append(f"연수기간:{parts[1].strip()}")
                        elif sub_line.startswith('류'):
                            parts = sub_line.split(':', 1)
                            if len(parts) == 2:
                                normalized.append(f"연수종류:{parts[1].strip()}")
                        elif sub_line.startswith('간'):
                            parts = sub_line.split(':', 1)
                            if len(parts) == 2:
                                normalized.append(f"이수시간:{parts[1].strip()}")
                        i += 1
                    continue
                
                if ':' in line:
                    parts = re.split(r'[:：]', line, maxsplit=1)
                    if len(parts) == 2:
                        label = parts[0].replace(' ', '').replace('\t', '')
                        value = parts[1].strip()
                        normalized.append(f"{label}:{value}")
                    else:
                        normalized.append(line.replace(' ', ''))
                else:
                    normalized.append(line)
            
            i += 1
        
        return '\n'.join(normalized)
