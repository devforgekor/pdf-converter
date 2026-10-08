import os
import uuid
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading


class BatchJob:
    """배치 작업 단위"""
    
    def __init__(self, job_id: str, files: List[Dict[str, Any]]):
        self.job_id = job_id
        self.files = files
        self.status = "pending"  # pending, processing, completed, failed
        self.created_at = datetime.now()
        self.completed_at: Optional[datetime] = None
        self.results: List[Dict[str, Any]] = []
        self.progress = 0
        self.total = len(files)
        self.error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "total": self.total,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "results": self.results,
            "error_message": self.error_message
        }


class BatchProcessor:
    """배치 처리 관리자"""
    
    def __init__(self, max_concurrent: int = 3):
        self.max_concurrent = max_concurrent
        self.jobs: Dict[str, BatchJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent)
    
    def create_job(self, files: List[Dict[str, Any]]) -> str:
        """새 배치 작업 생성"""
        job_id = f"batch_{uuid.uuid4().hex[:12]}"
        
        with self._lock:
            self.jobs[job_id] = BatchJob(job_id, files)
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """작업 조회"""
        return self.jobs.get(job_id)
    
    def get_all_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """모든 작업 목록 조회"""
        jobs = sorted(
            self.jobs.values(),
            key=lambda x: x.created_at,
            reverse=True
        )[:limit]
        return [job.to_dict() for job in jobs]
    
    async def process_job(self, job_id: str, process_func, db_session_factory):
        """배치 작업 처리"""
        job = self.get_job(job_id)
        if not job:
            return
        
        job.status = "processing"
        
        try:
            # 동시성 제한
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def process_file_with_semaphore(file_info: Dict[str, Any]):
                async with semaphore:
                    return await process_file(file_info)
            
            async def process_file(file_info: Dict[str, Any]) -> Dict[str, Any]:
                """단일 파일 처리"""
                try:
                    # DB 세션 생성
                    db = db_session_factory()
                    try:
                        # 변환 레코드 생성
                        from models import Conversion
                        conversion = Conversion(
                            user_id=0,
                            original_filename=file_info['filename'],
                            stored_filename=file_info.get('stored_filename', ''),
                            object_name=file_info.get('object_name', ''),
                            file_size=file_info.get('file_size', 0),
                            status="processing"
                        )
                        db.add(conversion)
                        db.commit()
                        db.refresh(conversion)
                        
                        # 변환 처리
                        result = await process_func(file_info, conversion.id, db)
                        
                        # 결과 저장
                        job.results.append({
                            "filename": file_info['filename'],
                            "conversion_id": conversion.id,
                            "status": "completed",
                            "output_filename": result.get("output_filename"),
                            "output_object_name": result.get("output_object_name")
                        })
                        
                        return result
                    finally:
                        db.close()
                except Exception as e:
                    job.results.append({
                        "filename": file_info['filename'],
                        "status": "failed",
                        "error": str(e)
                    })
                    return {"error": str(e)}
            
            # 모든 파일 처리
            tasks = [process_file_with_semaphore(f) for f in job.files]
            await asyncio.gather(*tasks)
            
            job.status = "completed"
            job.completed_at = datetime.now()
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now()
    
    def cancel_job(self, job_id: str) -> bool:
        """작업 취소"""
        job = self.get_job(job_id)
        if job and job.status in ["pending", "processing"]:
            job.status = "cancelled"
            job.completed_at = datetime.now()
            return True
        return False
    
    def delete_job(self, job_id: str) -> bool:
        """작업 삭제"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            return True
        return False


class BatchUploadManager:
    """배치 업로드 관리자"""
    
    def __init__(self):
        self.pending_files: Dict[str, List[Dict[str, Any]]] = {}
    
    def add_file(self, session_id: str, file_info: Dict[str, Any]) -> int:
        """파일 추가"""
        if session_id not in self.pending_files:
            self.pending_files[session_id] = []
        
        self.pending_files[session_id].append(file_info)
        return len(self.pending_files[session_id])
    
    def get_files(self, session_id: str) -> List[Dict[str, Any]]:
        """대기 중인 파일 목록"""
        return self.pending_files.get(session_id, [])
    
    def remove_file(self, session_id: str, file_index: int) -> bool:
        """파일 제거"""
        if session_id in self.pending_files:
            if 0 <= file_index < len(self.pending_files[session_id]):
                del self.pending_files[session_id][file_index]
                return True
        return False
    
    def clear_files(self, session_id: str):
        """대기 중인 파일 전체 삭제"""
        if session_id in self.pending_files:
            del self.pending_files[session_id]
    
    def get_file_count(self, session_id: str) -> int:
        """파일 수 반환"""
        return len(self.pending_files.get(session_id, []))


# 전역 인스턴스
batch_processor = BatchProcessor(max_concurrent=3)
batch_upload_manager = BatchUploadManager()
