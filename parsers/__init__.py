"""문서 파서 모듈"""
from .base import BaseParser
from .ir import DocumentIR
from .registry import parser_registry

# 파서 자동 등록 (import 시점에 등록됨)
from . import certificate
from . import azure_di

__all__ = ['BaseParser', 'DocumentIR', 'parser_registry']
