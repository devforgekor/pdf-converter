import os
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Any, List, Optional
from functools import lru_cache
import threading


class ProcessingCache:
    """PDF 처리 캐시 관리"""
    
    def __init__(self, cache_dir: str = "/tmp/pdf_cache", max_size_mb: int = 500):
        self.cache_dir = cache_dir
        self.max_size_mb = max_size_mb
        self._lock = threading.Lock()
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_key(self, file_path: str, operation: str) -> str:
        """파일 해시 기반 캐시 키 생성"""
        with open(file_path, "rb") as f:
            content = f.read()
        file_hash = hashlib.md5(content).hexdigest()
        return f"{file_hash}_{operation}"
    
    def get(self, file_path: str, operation: str) -> Optional[Any]:
        """캐시에서 결과 조회"""
        key = self._get_key(file_path, operation)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        
        with self._lock:
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r") as f:
                        data = json.load(f)
                    # 캐시 유효 시간: 1시간
                    if time.time() - data.get("timestamp", 0) < 3600:
                        return data.get("result")
                except Exception:
                    pass
        return None
    
    def set(self, file_path: str, operation: str, result: Any):
        """캐시에 결과 저장"""
        key = self._get_key(file_path, operation)
        cache_path = os.path.join(self.cache_dir, f"{key}.json")
        
        with self._lock:
            try:
                with open(cache_path, "w") as f:
                    json.dump({
                        "result": result,
                        "timestamp": time.time()
                    }, f, ensure_ascii=False)
                self._cleanup_old_cache()
            except Exception:
                pass
    
    def _cleanup_old_cache(self):
        """오래된 캐시 정리"""
        try:
            files = os.listdir(self.cache_dir)
            if len(files) > 100:  # 최대 100개 캐시 유지
                files.sort(key=lambda x: os.path.getmtime(os.path.join(self.cache_dir, x)))
                for old_file in files[:50]:
                    os.remove(os.path.join(self.cache_dir, old_file))
        except Exception:
            pass
    
    def clear(self):
        """캐시 전체 삭제"""
        with self._lock:
            for file in os.listdir(self.cache_dir):
                os.remove(os.path.join(self.cache_dir, file))


class ParallelProcessor:
    """병렬 처리기"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.cache = ProcessingCache()
    
    def process_batch(self, items: List[Any], process_func: Callable, 
                     use_cache: bool = True) -> List[Any]:
        """배치 병렬 처리"""
        results = [None] * len(items)
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {}
            
            for idx, item in enumerate(items):
                # 캐시 확인
                if use_cache and isinstance(item, dict) and "file_path" in item:
                    cached = self.cache.get(item["file_path"], process_func.__name__)
                    if cached is not None:
                        results[idx] = cached
                        continue
                
                future = executor.submit(process_func, item)
                future_to_idx[future] = idx
            
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    results[idx] = result
                    
                    # 캐시 저장
                    if use_cache and isinstance(items[idx], dict) and "file_path" in items[idx]:
                        self.cache.set(items[idx]["file_path"], process_func.__name__, result)
                except Exception as e:
                    results[idx] = {"error": str(e)}
        
        return results
    
    def process_single(self, item: Any, process_func: Callable, 
                      use_cache: bool = True) -> Any:
        """단일 항목 처리 (캐시 지원)"""
        if use_cache and isinstance(item, dict) and "file_path" in item:
            cached = self.cache.get(item["file_path"], process_func.__name__)
            if cached is not None:
                return cached
        
        result = process_func(item)
        
        if use_cache and isinstance(item, dict) and "file_path" in item:
            self.cache.set(item["file_path"], process_func.__name__, result)
        
        return result


class SpeedOptimizer:
    """속도 최적화 유틸리티"""
    
    @staticmethod
    @lru_cache(maxsize=32)
    def get_pdf_page_count(file_path: str) -> int:
        """PDF 페이지 수 캐싱"""
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    
    @staticmethod
    def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
        """리스트를 청크로 분할"""
        return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]
    
    @staticmethod
    def estimate_processing_time(file_size_mb: float, page_count: int) -> float:
        """예상 처리 시간 계산 (초)"""
        # 대략적 공식: 파일 크기 * 0.1 + 페이지 수 * 0.5
        return (file_size_mb * 0.1) + (page_count * 0.5)


# 전역 인스턴스
parallel_processor = ParallelProcessor(max_workers=4)
speed_optimizer = SpeedOptimizer()
