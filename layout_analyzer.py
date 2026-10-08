"""PDF 레이아웃 분석기 - 예시 PDF에서 파싱 규칙 자동 학습"""
import re
import json
from typing import List, Dict, Tuple, Optional


class LayoutAnalyzer:
    """PDF 레이아웃을 분석하여 파싱 규칙을 자동 생성"""

    # 감지할 라벨 키워드
    FIELD_LABELS = {
        "성명": ["성명", "성 명", "명"],
        "생년월일": ["생년월일", "생 년월일", "생년월일", "월일", "생년"],
        "직급": ["직급", "직 급", "급"],
        "근무기관": ["근무기관", "근 무 기관", "기관"],
        "과정명": ["과정명", "과 정 명"],
        "연수기간": ["연수기간", "연 수 기간", "기간"],
        "이수시간": ["이수시간", "이 수 시 간", "시간"],
        "이수번호": ["이수번호", "이 수 번호", "번호"],
        "수료일": ["수료일", "수 료 일"],
    }

    # 값 패턴
    VALUE_PATTERNS = {
        "이름": re.compile(r'^[가-힣]{2,4}$'),
        "날짜": re.compile(r'\d{2}\.\d{2}\.\d{2}'),
        "기간": re.compile(r'\d{4}\.\d{2}\.\d{2}\.?\s*~\s*\d{4}\.\d{2}\.\d{2}'),
        "번호": re.compile(r'\d{4}-\d+-\d+'),
        "시간": re.compile(r'\d+시간'),
        "기관": re.compile(r'(학교|교육청|단체|기관|연수원)'),
    }

    def __init__(self):
        self.lines: List[str] = []
        self.non_empty: List[Tuple[int, str]] = []

    def analyze(self, text: str) -> Dict:
        """텍스트를 분석하여 파싱 규칙 생성"""
        self.lines = [l.strip() for l in text.split('\n')]
        self.non_empty = [(i, l) for i, l in enumerate(self.lines) if l]

        # 1단계: 라벨 감지
        labels_found = self._detect_labels()

        # 2단계: 값 블록 감지
        value_block = self._detect_value_block(labels_found)

        # 3단계: 패턴 생성
        patterns = self._generate_patterns(labels_found, value_block)

        return {
            "labels": labels_found,
            "value_block": value_block,
            "patterns": patterns,
        }

    def _detect_labels(self) -> Dict[str, Dict]:
        """텍스트에서 라벨 위치 감지"""
        found = {}

        for idx, line in self.non_empty:
            clean = line.replace(" ", "").replace("\t", "")

            for field_name, keywords in self.FIELD_LABELS.items():
                for kw in keywords:
                    kw_clean = kw.replace(" ", "")
                    if clean.startswith(kw_clean) and (clean.endswith(":") or clean.endswith("：")):
                        # 이미 같은 필드가 감지되었으면 건너뛰기 (첫 번째 것만 사용)
                        if field_name not in found:
                            found[field_name] = {
                                "line_idx": idx,
                                "line_text": line,
                                "keyword": kw,
                            }
                        break

        return found

    def _detect_value_block(self, labels: Dict) -> Dict:
        """값 블록 위치 감지"""
        if not labels:
            return {"start": 0, "end": 0, "values": []}

        # 라벨 중 가장 마지막 줄 찾기
        last_label_idx = max(l["line_idx"] for l in labels.values())

        # 값 블록: 라벨 다음부터 시작
        values = []
        for idx, line in self.non_empty:
            if idx > last_label_idx:
                val = line.strip()
                if val and not self._is_metadata(val):
                    values.append({"line_idx": idx, "value": val})

        return {
            "start": last_label_idx + 1,
            "end": values[-1]["line_idx"] if values else last_label_idx + 1,
            "values": values,
        }

    def _is_metadata(self, text: str) -> bool:
        """메타데이터 텍스트인지 확인"""
        metadata_keywords = [
            "이 수 증", "연 수", "이 수", "과", "위와 같이",
            "년", "월", "일", "증명합니다"
        ]
        return any(kw in text for kw in metadata_keywords)

    def _generate_patterns(self, labels: Dict, value_block: Dict) -> Dict:
        """감지된 정보로 파싱 규칙 생성"""
        patterns = {}

        # 각 필드별 규칙 생성
        for field_name, label_info in labels.items():
            line_idx = label_info["line_idx"]
            keyword = label_info["keyword"]

            # 값 위치 찾기 (라벨과 같은 줄에 있거나 다음 줄)
            value = self._find_value_near_label(line_idx, keyword)

            if value:
                patterns[field_name] = {
                    "type": "line_based",
                    "label_keyword": keyword,
                    "label_line": line_idx,
                    "value": value["value"],
                    "value_line": value["line_idx"],
                }

        # 값 블록에서 필드 매핑
        if value_block["values"]:
            patterns["_value_block"] = {
                "start_line": value_block["start"],
                "values": [v["value"] for v in value_block["values"]],
            }

        return patterns

    def _find_value_near_label(self, label_line: int, keyword: str) -> Optional[Dict]:
        """라벨 근처에서 값 찾기"""
        # 같은 줄에서 라벨 다음 값 찾기
        for idx, line in self.non_empty:
            if idx == label_line:
                # "라벨 : 값" 형태
                m = re.search(r'[:：]\s*(.+)', line)
                if m and m.group(1).strip():
                    return {"line_idx": idx, "value": m.group(1).strip()}

        # 다음 줄에서 값 찾기
        for idx, line in self.non_empty:
            if idx > label_line and idx <= label_line + 3:
                val = line.strip()
                if val and not self._is_metadata(val):
                    return {"line_idx": idx, "value": val}

        return None

    def to_parsing_config(self, analysis: Dict) -> str:
        """분석 결과를 파싱 설정 JSON으로 변환"""
        config = {
            "version": 2,
            "method": "layout_based",
            "labels": {},
            "value_block": analysis["value_block"],
            "field_rules": {},
        }

        # 라벨 정보
        for field, info in analysis["labels"].items():
            config["labels"][field] = {
                "keyword": info["keyword"],
                "line": info["line_idx"],
            }

        # 필드 규칙
        for field, rule in analysis["patterns"].items():
            if field.startswith("_"):
                continue
            config["field_rules"][field] = {
                "type": "content_based",
                "keyword": rule.get("label_keyword", ""),
                "line_offset": rule.get("value_line", 0) - rule.get("label_line", 0),
            }

        # 값 블록 규칙
        if "_value_block" in analysis["patterns"]:
            vb = analysis["patterns"]["_value_block"]
            config["value_block"]["extraction"] = {
                "method": "sequential",
                "field_order": list(analysis["labels"].keys()),
            }

        return json.dumps(config, ensure_ascii=False, indent=2)


analyzer = LayoutAnalyzer()
