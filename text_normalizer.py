"""텍스트 정규화 모듈 - 통합 진입점"""
from normalizers.base import TextNormalizer
from normalizers.azure_di import AzureDINormalizer

# 기본 인스턴스 (pdftotext용)
normalizer = TextNormalizer()

# Azure DI용 인스턴스
azure_di_normalizer = AzureDINormalizer()
