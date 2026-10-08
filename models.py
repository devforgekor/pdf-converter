from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    conversions = relationship("Conversion", back_populates="user")
    legal_educations = relationship("LegalEducation", back_populates="user")
    safety_educations = relationship("SafetyEducation", back_populates="user")
    school_educations = relationship("SchoolEducation", back_populates="user")


class Conversion(Base):
    __tablename__ = "conversions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    object_name = Column(String(500))  # OCI Object Storage key
    output_object_name = Column(String(500))  # OCI Object Storage key for output
    file_size = Column(Integer)
    pdf_type = Column(String(50))  # roster, receipt, certificate
    output_format = Column(String(20), default="excel")  # excel, sheets
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    output_filename = Column(String(255))
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="conversions")


class LegalEducation(Base):
    """법정의무교육 이수 내역"""
    __tablename__ = "legal_educations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    education_type = Column(String(50), nullable=False)  # 성희롱예방, 장애인인식개선, 개인정보보호, 장애인차별금지
    year = Column(Integer, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True))
    certificate_filename = Column(String(255))
    certificate_object_name = Column(String(500))
    conversion_id = Column(Integer, ForeignKey("conversions.id"), nullable=True)
    hours = Column(Float, default=1.0)
    organization = Column(String(200))
    memo = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="legal_educations")
    conversion = relationship("Conversion")


class SafetyEducation(Base):
    """학교안전교육 이수 내역"""
    __tablename__ = "safety_educations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    year = Column(Integer, nullable=False)
    education_name = Column(String(200), nullable=False)
    hours = Column(Float, nullable=False)
    education_date = Column(DateTime(timezone=True), nullable=False)
    method = Column(String(20), nullable=False)  # 대면, 비대면, 혼합
    certificate_filename = Column(String(255))
    certificate_object_name = Column(String(500))
    conversion_id = Column(Integer, ForeignKey("conversions.id"), nullable=True)
    organization = Column(String(200))
    memo = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="safety_educations")
    conversion = relationship("Conversion")


class SchoolEducation(Base):
    """학생 학적 정보 관리"""
    __tablename__ = "school_educations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    year = Column(Integer, nullable=False)
    education_name = Column(String(200), nullable=False)
    hours = Column(Float, nullable=False)
    education_date = Column(DateTime(timezone=True), nullable=False)
    method = Column(String(20), nullable=False)  # 대면, 비대면, 혼합
    certificate_filename = Column(String(255))
    certificate_object_name = Column(String(500))
    conversion_id = Column(Integer, ForeignKey("conversions.id"), nullable=True)
    organization = Column(String(200))
    memo = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="school_educations")
    conversion = relationship("Conversion")


class CertificateTemplate(Base):
    """이수증 템플릿 (파싱 패턴 + 연결 양식)"""
    __tablename__ = "certificate_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # 템플릿명 (예: 학교안전교육 이수증)
    issuer = Column(String(200))  # 발급기관 (예: 서울특별시교육청)
    description = Column(Text)  # 설명
    
    # 문서 유형 (레지스트리 기반)
    doc_type = Column(String(50), default="이수증")  # "이수증", "학적", etc.
    
    # 파싱 패턴 (JSON) - 예: {"성명": r"성명\s*:\s*(.+)", "생년월일": r"생년월일\s*:\s*(.+)"}
    parsing_patterns = Column(Text)
    
    # 연결된 입력 양식 (Excel)
    linked_form_object_name = Column(String(500))  # OCI 경로
    linked_form_original_name = Column(String(255))  # 원본 파일명
    
    # 매핑 정보 (JSON) - 파싱된 데이터를 Excel의 어떤 셀에 넣을지
    # 예: {"성명": "D", "생년월일": "E", "이수시간": "J"}
    field_mapping = Column(Text)
    
    # 출력 설정
    output_sheet_name = Column(String(100))  # 출력 시트명
    output_start_row = Column(Integer, default=2)  # 데이터 시작 행
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CertificateRecord(Base):
    """이수증 기록 (파싱된 데이터 저장)"""
    __tablename__ = "certificate_records"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("certificate_templates.id"))
    
    # 원본 이수증
    original_pdf_object_name = Column(String(500))  # OCI 경로
    original_pdf_filename = Column(String(255))
    
    # 파싱된 데이터 (JSON)
    parsed_data = Column(Text)  # {"성명": "윤지훈", "생년월일": "19800425", ...}
    
    # 추출된 정보
    holder_name = Column(String(100))  # 성명
    holder_birth = Column(String(20))  # 생년월일
    course_name = Column(String(200))  # 과정명
    completion_date = Column(String(20))  # 수료일
    hours = Column(Integer)  # 이수시간
    certificate_number = Column(String(100))  # 이수번호
    
    # 상태
    status = Column(String(20), default="parsed")  # parsed, exported, verified
    verification_code = Column(String(50), unique=True)  # 검증용 고유코드
    
    # 출력 파일
    exported_object_name = Column(String(500))  # Excel 출력 파일 OCI 경로
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    template = relationship("CertificateTemplate")


class ExampleFile(Base):
    """예시 파일 (템플릿, 가이드 등)"""
    __tablename__ = "example_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # excel, pdf, word, image
    file_size = Column(Integer)
    object_name = Column(String(500))
    description = Column(Text)
    download_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
