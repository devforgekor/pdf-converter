"""
KUHWA Portal - 메인 애플리케이션

참조 소스:
- FastAPI 공식 문서 (Templates): https://fastapi.tiangolo.com/advanced/templates
- Authlib FastAPI Google Login: https://github.com/authlib/demo-oauth-client/tree/master/fastapi-google-login
- FastAPI + SQLAlchemy 패턴: https://fastapi.tiangolo.com/tutorial/sql-databases/
- Flash 메시지: Flask 패턴을 FastAPI/Starlette로 포팅
- CSRF 토큰: Flask-WTF 패턴을 FastAPI로 포팅
- Vercel 배포: https://vercel.com/docs/frameworks/backend/fastapi
"""
import os
import uuid
import asyncio
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, File, UploadFile, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth
import httpx

from database import engine, get_db, Base
from models import User, Conversion, LegalEducation, SafetyEducation, IntegrityEducation, ExampleFile, CertificateTemplate, CertificateRecord
from flash import flash, get_flashed_messages
from csrf import generate_csrf_token, validate_csrf_token
from storage import storage
from pdf_validator import validator, PDFValidationError
from processor import parallel_processor, speed_optimizer
from batch import batch_processor, batch_upload_manager
from sheets_integration import google_sheets_manager

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PDF to Spreadsheet")

from template_routes import router as template_router
app.include_router(template_router)

oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # CSRF 검증을 라우트 핸들러에서 처리
        return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
    session_cookie="session_id",
    max_age=86400,
    same_site="lax",
    https_only=False,
)
app.add_middleware(CSRFMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals["csrf_token"] = generate_csrf_token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_google_user(request: Request, db: Session):
    user_id = request.session.get("user_id")
    if user_id:
        return db.query(User).filter(User.id == user_id).first()
    return None


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# === 관리자 페이지 ===
@app.api_route("/admin", methods=["GET","HEAD"], response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    
    # 통계 데이터
    stats = {
        "total_users": db.query(User).count(),
        "total_conversions": db.query(Conversion).count(),
        "completed_conversions": db.query(Conversion).filter(Conversion.status == "completed").count(),
        "total_legal": db.query(LegalEducation).count(),
        "total_safety": db.query(SafetyEducation).count(),
        "total_integrity": db.query(IntegrityEducation).count(),
    }
    
    # 최근 변환 이력
    recent_conversions = db.query(Conversion).order_by(Conversion.created_at.desc()).limit(10).all()
    
    # 사용자 목록
    users = db.query(User).all()
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "stats": stats,
        "recent_conversions": recent_conversions,
        "users": users,
    })


@app.post("/admin/user/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    
    # 중복 확인
    existing = db.query(User).filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        flash(request, "이미 존재하는 사용자명 또는 이메일입니다.", "danger")
        return RedirectResponse("/admin", status_code=303)
    
    hashed_password = pwd_context.hash(password)
    user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
    )
    db.add(user)
    db.commit()
    
    flash(request, f"사용자 {username}이(가) 추가되었습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/user/delete/{user_id}")
async def delete_user(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
):
    
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
        flash(request, f"사용자 {user.username}이(가) 삭제되었습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.post("/admin/conversion/delete/{conversion_id}")
async def delete_conversion(
    request: Request,
    conversion_id: int,
    db: Session = Depends(get_db),
):
    
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if conversion:
        # OCI에서 파일 삭제
        try:
            if conversion.object_name:
                storage.delete_file(conversion.object_name)
            if conversion.output_object_name:
                storage.delete_file(conversion.output_object_name)
        except Exception:
            pass
        
        db.delete(conversion)
        db.commit()
        flash(request, "변환 기록이 삭제되었습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


# === 예시 파일 관리 ===
@app.post("/admin/example/upload")
async def upload_example_file(
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
):

    # 파일 유형 결정
    filename_lower = file.filename.lower()
    if filename_lower.endswith(('.xlsx', '.xls', '.csv')):
        file_type = "excel"
    elif filename_lower.endswith('.pdf'):
        file_type = "pdf"
    elif filename_lower.endswith(('.doc', '.docx')):
        file_type = "word"
    elif filename_lower.endswith(('.jpg', '.jpeg', '.png', '.gif')):
        file_type = "image"
    else:
        file_type = "other"

    content = await file.read()
    
    # OCI에 업로드
    stored_filename = f"examples/{uuid.uuid4().hex}_{file.filename}"
    try:
        storage.upload_file(stored_filename, content, "application/octet-stream")
    except Exception as e:
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/admin", status_code=303)

    # DB 저장
    example = ExampleFile(
        filename=stored_filename,
        original_filename=file.filename,
        file_type=file_type,
        file_size=len(content),
        object_name=stored_filename,
        description=description,
    )
    db.add(example)
    db.commit()

    flash(request, f"예시 파일 '{file.filename}'이(가) 업로드되었습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.api_route("/examples/download/{file_id}", methods=["GET","HEAD"])
async def download_example_file_public(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
):

    example = db.query(ExampleFile).filter(ExampleFile.id == file_id).first()
    if not example:
        flash(request, "파일을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/examples", status_code=303)

    example.download_count += 1
    db.commit()

    try:
        par_url = storage.get_par_url(example.object_name, expires_in_hours=1)
        return RedirectResponse(par_url, status_code=302)
    except Exception as e:
        flash(request, f"파일 다운로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/examples", status_code=303)


@app.api_route("/admin/example/download/{file_id}", methods=["GET","HEAD"])
async def download_example_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
):

    example = db.query(ExampleFile).filter(ExampleFile.id == file_id).first()
    if not example:
        flash(request, "파일을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/admin", status_code=303)

    # 다운로드 수 증가
    example.download_count += 1
    db.commit()

    # OCI에서 파일 다운로드
    try:
        file_content = storage.download_file(example.object_name)
        return Response(
            content=file_content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{example.original_filename}"'}
        )
    except Exception as e:
        flash(request, f"파일 다운로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/admin", status_code=303)


@app.post("/admin/example/delete/{file_id}")
async def delete_example_file(
    request: Request,
    file_id: int,
    db: Session = Depends(get_db),
):

    example = db.query(ExampleFile).filter(ExampleFile.id == file_id).first()
    if example:
        # OCI에서 파일 삭제
        try:
            storage.delete_file(example.object_name)
        except Exception:
            pass
        
        db.delete(example)
        db.commit()
        flash(request, "예시 파일이 삭제되었습니다.", "success")
    return RedirectResponse("/admin", status_code=303)


@app.api_route("/examples", methods=["GET","HEAD"], response_class=HTMLResponse)
async def examples_page(request: Request, db: Session = Depends(get_db)):

    examples = db.query(ExampleFile).order_by(ExampleFile.created_at.desc()).all()
    
    return templates.TemplateResponse("examples.html", {
        "request": request,
        "examples": examples,
    })


# === Google OAuth (Drive/Sheets 연동용 - 선택) ===
@app.api_route("/auth/google", methods=["GET","HEAD"])
async def google_login(request: Request):
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.api_route("/auth/google/callback", methods=["GET","HEAD"])
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if not user_info:
        flash(request, "Google 인증에 실패했습니다.", "danger")
        return RedirectResponse("/", status_code=303)
    email = user_info.get('email', '')
    if not email.endswith("@kuhwa.sen.sc.kr"):
        flash(request, "@kuhwa.sen.sc.kr 이메일만 사용 가능합니다.", "danger")
        return RedirectResponse("/", status_code=303)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            username=email.split('@')[0],
            email=email,
            hashed_password=pwd_context.hash(uuid.uuid4().hex),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    request.session["user_id"] = user.id
    flash(request, f"Google 계정 연결 완료: {user.username}", "success")
    return RedirectResponse("/", status_code=303)


# === 앱 루트 — 이수증으로 안내 (구 대시보드/홈페이지는 삭제) ===
@app.api_route("/", methods=["GET","HEAD"], response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse("/certificate", status_code=303)


# === 이수증 ===
@app.api_route("/certificate", methods=["GET","HEAD"], response_class=HTMLResponse)
async def certificate_page(request: Request, db: Session = Depends(get_db)):

    # 각 교육별 이수 현황 집계
    legal_stats = {}
    for edu_type in ["성희롱예방", "장애인인식개선", "개인정보보호", "장애인차별금지"]:
        completed = db.query(LegalEducation).filter(
            LegalEducation.education_type == edu_type,
            LegalEducation.year == datetime.now().year,
            LegalEducation.is_completed == True
        ).count()
        legal_stats[edu_type] = completed > 0

    # 안전교육 연도별 시간 합계
    current_year = datetime.now().year
    safety_hours = {}
    for year in range(current_year - 2, current_year + 1):
        total = db.query(func.sum(SafetyEducation.hours)).filter(
            SafetyEducation.year == year
        ).scalar() or 0
        safety_hours[year] = total

    return templates.TemplateResponse("certificate.html", {
        "request": request,
        "legal_stats": legal_stats,
        "safety_hours": safety_hours,
        "current_year": current_year,
    })


@app.api_route("/certificate/legal", methods=["GET","HEAD"], response_class=HTMLResponse)
async def legal_education_page(request: Request, db: Session = Depends(get_db)):

    current_year = datetime.now().year
    educations = db.query(LegalEducation).filter(
        LegalEducation.year == current_year
    ).all()

    # 연도별 이수 현황
    yearly_stats = {}
    for year in range(2022, current_year + 1):
        yearly_stats[year] = db.query(LegalEducation).filter(
            LegalEducation.year == year,
            LegalEducation.is_completed == True
        ).count()

    return templates.TemplateResponse("legal_education.html", {
        "request": request,
        "educations": educations,
        "current_year": current_year,
        "yearly_stats": yearly_stats,
    })


@app.api_route("/certificate/safety", methods=["GET","HEAD"], response_class=HTMLResponse)
async def safety_education_page(request: Request, db: Session = Depends(get_db)):

    current_year = datetime.now().year
    educations = db.query(SafetyEducation).filter(
        SafetyEducation.year == current_year
    ).order_by(SafetyEducation.education_date.desc()).all()

    # 연도별 시간 합계
    yearly_hours = {}
    for year in range(current_year - 2, current_year + 1):
        total = db.query(func.sum(SafetyEducation.hours)).filter(
            SafetyEducation.year == year
        ).scalar() or 0
        yearly_hours[year] = total

    return templates.TemplateResponse("safety_education.html", {
        "request": request,
        "educations": educations,
        "current_year": current_year,
        "yearly_hours": yearly_hours,
    })


@app.post("/certificate/legal/upload")
async def upload_legal_certificate(
    request: Request,
    file: UploadFile = File(...),
    education_type: str = Form(...),
    year: int = Form(default=datetime.now().year),
    db: Session = Depends(get_db),
):

    if not file.filename.lower().endswith(".pdf"):
        flash(request, "PDF 파일만 업로드 가능합니다.", "danger")
        return RedirectResponse("/certificate/legal", status_code=303)

    content = await file.read()

    # PDF 검증
    temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        flash(request, f"파일 저장 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/legal", status_code=303)

    try:
        validator.check_magic_number(temp_path)
        validator.check_file_size(temp_path)
    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/certificate/legal", status_code=303)

    # 암호화 검사
    if validator.is_encrypted(temp_path):
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, "암호화된 PDF는 지원되지 않습니다.", "danger")
        return RedirectResponse("/certificate/legal", status_code=303)

    if os.path.exists(temp_path):
        os.remove(temp_path)

    # OCI에 업로드
    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    object_name = f"uploads/{stored_filename}"
    
    try:
        storage.upload_file(object_name, content, "application/pdf")
    except Exception as e:
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/legal", status_code=303)

    # Conversion 레코드 생성
    conversion = Conversion(
        user_id=1,
        original_filename=file.filename,
        stored_filename=stored_filename,
        object_name=object_name,
        file_size=len(content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    # 법정의무교육 레코드 생성 (변환 후 상태 업데이트 예정)
    edu = LegalEducation(
        user_id=1,
        education_type=education_type,
        year=year,
        is_completed=True,
        completed_at=datetime.now(),
        certificate_filename=file.filename,
        certificate_object_name=object_name,
        conversion_id=conversion.id,
        hours=1.0,
    )
    db.add(edu)
    db.commit()

    flash(request, f"{education_type} 수료증이 업로드되었습니다. 변환을 진행합니다.", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


@app.post("/certificate/legal/toggle")
async def toggle_legal_education(
    request: Request,
    education_type: str = Form(...),
    year: int = Form(default=datetime.now().year),
    is_completed: bool = Form(default=True),
    db: Session = Depends(get_db),
):

    user_id = 1
    edu = db.query(LegalEducation).filter(
        LegalEducation.user_id == user_id,
        LegalEducation.education_type == education_type,
        LegalEducation.year == year,
    ).first()

    if edu:
        edu.is_completed = is_completed
        if is_completed:
            edu.completed_at = datetime.now()
        else:
            edu.completed_at = None
    else:
        edu = LegalEducation(
            user_id=user_id,
            education_type=education_type,
            year=year,
            is_completed=is_completed,
            completed_at=datetime.now() if is_completed else None,
            hours=1.0,
        )
        db.add(edu)

    db.commit()
    status = "이수" if is_completed else "미이수"
    flash(request, f"{education_type} {year}년: {status} 처리되었습니다.", "success")
    return RedirectResponse("/certificate/legal", status_code=303)


@app.post("/certificate/safety/upload")
async def upload_safety_certificate(
    request: Request,
    file: UploadFile = File(...),
    edu_year: int = Form(...),
    edu_hours: float = Form(...),
    edu_name: str = Form(...),
    edu_date: str = Form(...),
    edu_method: str = Form(...),
    db: Session = Depends(get_db),
):

    if not file.filename.lower().endswith(".pdf"):
        flash(request, "PDF 파일만 업로드 가능합니다.", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    content = await file.read()

    # PDF 검증
    temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        flash(request, f"파일 저장 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    try:
        validator.check_magic_number(temp_path)
        validator.check_file_size(temp_path)
    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    # 암호화 검사
    if validator.is_encrypted(temp_path):
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, "암호화된 PDF는 지원되지 않습니다.", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    if os.path.exists(temp_path):
        os.remove(temp_path)

    # OCI에 업로드
    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    object_name = f"uploads/{stored_filename}"
    
    try:
        storage.upload_file(object_name, content, "application/pdf")
    except Exception as e:
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    # Conversion 레코드 생성
    conversion = Conversion(
        user_id=1,
        original_filename=file.filename,
        stored_filename=stored_filename,
        object_name=object_name,
        file_size=len(content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    # 안전교육 레코드 생성
    edu = SafetyEducation(
        user_id=1,
        year=edu_year,
        education_name=edu_name,
        hours=edu_hours,
        education_date=datetime.strptime(edu_date, "%Y-%m-%d"),
        method=edu_method,
        certificate_filename=file.filename,
        certificate_object_name=object_name,
        conversion_id=conversion.id,
    )
    db.add(edu)
    db.commit()

    flash(request, f"{edu_name} ({edu_year}년) 수료증이 업로드되었습니다. 변환을 진행합니다.", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


@app.post("/certificate/safety/add")
async def add_safety_education(
    request: Request,
    year: int = Form(...),
    hours: float = Form(...),
    name: str = Form(...),
    date: str = Form(...),
    method: str = Form(...),
    organization: str = Form(""),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):

    user_id = 1
    edu = SafetyEducation(
        user_id=user_id,
        year=year,
        education_name=name,
        hours=hours,
        education_date=datetime.strptime(date, "%Y-%m-%d"),
        method=method,
        organization=organization,
        memo=memo,
    )
    db.add(edu)
    db.commit()

    flash(request, f"{name} ({year}년) 교육이 추가되었습니다.", "success")
    return RedirectResponse("/certificate/safety", status_code=303)


@app.post("/certificate/safety/delete/{edu_id}")
async def delete_safety_education(
    request: Request,
    edu_id: int,
    db: Session = Depends(get_db),
):

    edu = db.query(SafetyEducation).filter(SafetyEducation.id == edu_id).first()
    if edu:
        db.delete(edu)
        db.commit()
        flash(request, "교육 내역이 삭제되었습니다.", "success")
    return RedirectResponse("/certificate/safety", status_code=303)


# === 청렴교육 ===
@app.api_route("/certificate/integrity", methods=["GET","HEAD"], response_class=HTMLResponse)
async def integrity_education_page(request: Request, db: Session = Depends(get_db)):

    current_year = datetime.now().year
    educations = db.query(IntegrityEducation).filter(
        IntegrityEducation.year == current_year
    ).order_by(IntegrityEducation.education_date.desc()).all()

    yearly_hours = {}
    for year in range(current_year - 2, current_year + 1):
        total = db.query(func.sum(IntegrityEducation.hours)).filter(
            IntegrityEducation.year == year
        ).scalar() or 0
        yearly_hours[year] = total

    return templates.TemplateResponse("integrity_education.html", {
        "request": request,
        "educations": educations,
        "current_year": current_year,
        "yearly_hours": yearly_hours,
    })


@app.post("/certificate/integrity/upload")
async def upload_integrity_certificate(
    request: Request,
    file: UploadFile = File(...),
    edu_year: int = Form(...),
    edu_hours: float = Form(...),
    edu_name: str = Form(...),
    edu_date: str = Form(...),
    edu_method: str = Form(...),
    db: Session = Depends(get_db),
):

    if not file.filename.lower().endswith(".pdf"):
        flash(request, "PDF 파일만 업로드 가능합니다.", "danger")
        return RedirectResponse("/certificate/integrity", status_code=303)

    content = await file.read()

    # PDF 검증
    temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        flash(request, f"파일 저장 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/integrity", status_code=303)

    try:
        validator.check_magic_number(temp_path)
        validator.check_file_size(temp_path)
    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/certificate/integrity", status_code=303)

    # 암호화 검사
    if validator.is_encrypted(temp_path):
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, "암호화된 PDF는 지원되지 않습니다.", "danger")
        return RedirectResponse("/certificate/integrity", status_code=303)

    if os.path.exists(temp_path):
        os.remove(temp_path)

    # OCI에 업로드
    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    object_name = f"uploads/{stored_filename}"
    
    try:
        storage.upload_file(object_name, content, "application/pdf")
    except Exception as e:
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/certificate/integrity", status_code=303)

    # Conversion 레코드 생성
    conversion = Conversion(
        user_id=1,
        original_filename=file.filename,
        stored_filename=stored_filename,
        object_name=object_name,
        file_size=len(content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    # 청렴교육 레코드 생성
    edu = IntegrityEducation(
        user_id=1,
        year=edu_year,
        education_name=edu_name,
        hours=edu_hours,
        education_date=datetime.strptime(edu_date, "%Y-%m-%d"),
        method=edu_method,
        certificate_filename=file.filename,
        certificate_object_name=object_name,
        conversion_id=conversion.id,
    )
    db.add(edu)
    db.commit()

    flash(request, f"{edu_name} ({edu_year}년) 수료증이 업로드되었습니다. 변환을 진행합니다.", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


@app.post("/certificate/integrity/add")
async def add_integrity_education(
    request: Request,
    year: int = Form(...),
    hours: float = Form(...),
    name: str = Form(...),
    date: str = Form(...),
    method: str = Form(...),
    organization: str = Form(""),
    memo: str = Form(""),
    db: Session = Depends(get_db),
):

    user_id = 1
    edu = IntegrityEducation(
        user_id=user_id,
        year=year,
        education_name=name,
        hours=hours,
        education_date=datetime.strptime(date, "%Y-%m-%d"),
        method=method,
        organization=organization,
        memo=memo,
    )
    db.add(edu)
    db.commit()

    flash(request, f"{name} ({year}년) 교육이 추가되었습니다.", "success")
    return RedirectResponse("/certificate/integrity", status_code=303)


@app.post("/certificate/integrity/delete/{edu_id}")
async def delete_integrity_education(
    request: Request,
    edu_id: int,
    db: Session = Depends(get_db),
):

    edu = db.query(IntegrityEducation).filter(IntegrityEducation.id == edu_id).first()
    if edu:
        db.delete(edu)
        db.commit()
        flash(request, "교육 내역이 삭제되었습니다.", "success")
    return RedirectResponse("/certificate/integrity", status_code=303)


@app.api_route("/upload", methods=["GET","HEAD"], response_class=HTMLResponse)
async def upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload")
async def upload_file(
    request: Request,
    files: List[UploadFile] = File(...),
    upload_mode: str = Form("single"),
    db: Session = Depends(get_db),
):

    # 단일 파일 업로드 모드
    if upload_mode == "single" or len(files) == 1:
        return await _upload_single_file(request, files[0], db)
    
    # 배치 업로드 모드
    return await _upload_batch_files(request, files, db)


async def _upload_single_file(request: Request, file: UploadFile, db: Session):
    """단일 파일 업로드 처리"""
    if not file.filename.lower().endswith(".pdf"):
        flash(request, "PDF 파일만 업로드 가능합니다.", "danger")
        return RedirectResponse("/upload", status_code=303)

    content = await file.read()

    # 임시 파일에 저장
    temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
    except Exception as e:
        flash(request, f"파일 저장 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    # 기본 검증 (매직 넘버, 파일 크기)
    try:
        validator.check_magic_number(temp_path)
        validator.check_file_size(temp_path)
    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    # 암호화 검사
    if validator.is_encrypted(temp_path):
        request.session["pending_pdf_temp"] = temp_path
        request.session["pending_pdf_name"] = file.filename
        return templates.TemplateResponse("password.html", {
            "request": request,
            "filename": file.filename,
        })

    # 암호화되지 않은 PDF
    try:
        pages = validator.validate(temp_path)
    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    if os.path.exists(temp_path):
        os.remove(temp_path)

    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    object_name = f"uploads/{stored_filename}"

    try:
        storage.upload_file(object_name, content, "application/pdf")
    except Exception as e:
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    conversion = Conversion(
        user_id=0,
        original_filename=file.filename,
        stored_filename=stored_filename,
        object_name=object_name,
        file_size=len(content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    flash(request, "파일이 업로드되었습니다.", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


async def _upload_batch_files(request: Request, files: List[UploadFile], db: Session):
    """다중 파일 배치 업로드 처리"""
    uploaded_files = []
    errors = []
    
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            errors.append(f"{file.filename}: PDF가 아닙니다")
            continue
        
        try:
            content = await file.read()
            
            # 임시 파일 저장 및 검증
            temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
            with open(temp_path, "wb") as f:
                f.write(content)
            
            try:
                validator.check_magic_number(temp_path)
                validator.check_file_size(temp_path)
            except PDFValidationError as e:
                errors.append(f"{file.filename}: {str(e)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue
            
            # 암호화 검사
            if validator.is_encrypted(temp_path):
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                errors.append(f"{file.filename}: 암호화된 파일은 배치 처리에서 지원되지 않습니다")
                continue
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            # Object Storage에 업로드
            stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
            object_name = f"uploads/{stored_filename}"
            storage.upload_file(object_name, content, "application/pdf")
            
            # 변환 레코드 생성
            conversion = Conversion(
                user_id=0,
                original_filename=file.filename,
                stored_filename=stored_filename,
                object_name=object_name,
                file_size=len(content),
                status="pending",
            )
            db.add(conversion)
            db.commit()
            db.refresh(conversion)
            
            uploaded_files.append({
                "filename": file.filename,
                "conversion_id": conversion.id
            })
            
        except Exception as e:
            errors.append(f"{file.filename}: {str(e)}")
    
    # 결과 메시지
    if uploaded_files:
        if len(uploaded_files) == 1:
            flash(request, f"파일이 업로드되었습니다.", "success")
            return RedirectResponse(f"/convert/{uploaded_files[0]['conversion_id']}", status_code=303)
        else:
            flash(request, f"{len(uploaded_files)}개 파일이 업로드되었습니다.", "success")
            # 첫 번째 파일의 변환 페이지로 이동 (배치 처리 시작)
            return RedirectResponse(f"/convert/{uploaded_files[0]['conversion_id']}", status_code=303)
    
    if errors:
        flash(request, f"업로드 실패: {'; '.join(errors)}", "danger")
    
    return RedirectResponse("/upload", status_code=303)


@app.post("/upload-with-password")
async def upload_with_password(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
):

    temp_path = request.session.get("pending_pdf_temp")
    filename = request.session.get("pending_pdf_name")

    if not temp_path or not os.path.exists(temp_path):
        flash(request, "업로드된 파일을 찾을 수 없습니다. 다시 업로드해주세요.", "danger")
        return RedirectResponse("/upload", status_code=303)

    # 복호화 시도
    decrypted_path = f"/tmp/decrypted_{uuid.uuid4().hex}.pdf"
    try:
        if not validator.decrypt(temp_path, password, decrypted_path):
            flash(request, "비밀번호가 올바르지 않습니다.", "danger")
            return templates.TemplateResponse("password.html", {
                "request": request,
                "filename": filename,
                "error": "비밀번호가 올바르지 않습니다.",
            })

        # 복호화된 파일 검증
        pages = validator.validate(decrypted_path)

    except PDFValidationError as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(decrypted_path):
            os.remove(decrypted_path)
        flash(request, f"PDF 검증 실패: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(decrypted_path):
            os.remove(decrypted_path)
        flash(request, f"처리 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    # 세션 정리
    request.session.pop("pending_pdf_temp", None)
    request.session.pop("pending_pdf_name", None)

    # 원본 파일 삭제
    if os.path.exists(temp_path):
        os.remove(temp_path)

    # 복호화된 파일을 Object Storage에 업로드
    stored_filename = f"{uuid.uuid4().hex}_{filename}"
    object_name = f"uploads/{stored_filename}"

    try:
        with open(decrypted_path, "rb") as f:
            decrypted_content = f.read()
        storage.upload_file(object_name, decrypted_content, "application/pdf")
    except Exception as e:
        if os.path.exists(decrypted_path):
            os.remove(decrypted_path)
        flash(request, f"파일 업로드 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse("/upload", status_code=303)

    if os.path.exists(decrypted_path):
        os.remove(decrypted_path)

    conversion = Conversion(
        user_id=0,
        original_filename=filename,
        stored_filename=stored_filename,
        object_name=object_name,
        file_size=len(decrypted_content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    flash(request, "파일이 업로드되었습니다. (암호화 해제됨)", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


# === 변환 설정 ===
@app.api_route("/convert/{conversion_id}", methods=["GET","HEAD"], response_class=HTMLResponse)
async def convert_page(request: Request, conversion_id: int, db: Session = Depends(get_db)):
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/upload", status_code=303)
    return templates.TemplateResponse("convert.html", {
        "request": request,
        "conversion": conversion,
    })


@app.post("/convert/{conversion_id}")
async def start_conversion(
    request: Request,
    conversion_id: int,
    output_format: str = Form("excel"),
    pdf_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):

    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/upload", status_code=303)

    conversion.output_format = output_format
    conversion.pdf_type = pdf_type
    conversion.status = "processing"
    db.commit()

    try:
        from parsers.roster import RosterParser
        from parsers.receipt import ReceiptParser
        from parsers.certificate import CertificateParser
        from exporters.excel import ExcelExporter
        from detectors.type_detector import PDFTypeDetector

        pdf_content = storage.download_file(conversion.object_name)
        temp_input_path = f"/tmp/{conversion.stored_filename}"
        with open(temp_input_path, "wb") as f:
            f.write(pdf_content)

        if not pdf_type:
            detector = PDFTypeDetector()
            pdf_type = detector.detect(temp_input_path)
            conversion.pdf_type = pdf_type

        parsers = {
            "roster": RosterParser(),
            "receipt": ReceiptParser(),
            "certificate": CertificateParser(),
        }
        parser = parsers.get(pdf_type, RosterParser())
        data = parser.parse(temp_input_path)

        output_filename = f"{conversion.stored_filename}.xlsx"
        temp_output_path = f"/tmp/{output_filename}"
        exporter = ExcelExporter()
        exporter.export(data, temp_output_path)

        output_object_name = f"outputs/{output_filename}"
        with open(temp_output_path, "rb") as f:
            excel_content = f.read()
        storage.upload_file(
            output_object_name,
            excel_content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        os.remove(temp_input_path)
        os.remove(temp_output_path)

        conversion.output_filename = output_filename
        conversion.output_object_name = output_object_name
        conversion.status = "completed"
        conversion.completed_at = datetime.now()
        db.commit()

        flash(request, "변환이 완료되었습니다!", "success")
        return RedirectResponse(f"/download/{conversion.id}", status_code=303)

    except Exception as e:
        conversion.status = "failed"
        conversion.error_message = str(e)
        db.commit()
        flash(request, f"변환 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


# === 다운로드 ===
@app.api_route("/download/{conversion_id}", methods=["GET","HEAD"], response_class=HTMLResponse)
async def download_page(request: Request, conversion_id: int, db: Session = Depends(get_db)):
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/upload", status_code=303)
    return templates.TemplateResponse("download.html", {
        "request": request,
        "conversion": conversion,
    })


@app.api_route("/download/{conversion_id}/file", methods=["GET","HEAD"])
async def download_file(request: Request, conversion_id: int, db: Session = Depends(get_db)):
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion or conversion.status != "completed":
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if conversion.output_object_name:
        par_url = storage.get_par_url(conversion.output_object_name)
        return RedirectResponse(par_url)
    output_path = os.path.join(OUTPUT_DIR, conversion.output_filename)
    if os.path.exists(output_path):
        download_name = conversion.original_filename.replace(".pdf", ".xlsx")
        return FileResponse(
            output_path,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=download_name,
        )
    raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")


# === API ===
@app.api_route("/api/status/{conversion_id}", methods=["GET","HEAD"])
async def get_status(request: Request, conversion_id: int, db: Session = Depends(get_db)):
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion:
        raise HTTPException(status_code=404, detail="변환 레코드를 찾을 수 없습니다.")
    return JSONResponse({
        "id": conversion.id,
        "status": conversion.status,
        "pdf_type": conversion.pdf_type,
        "output_format": conversion.output_format,
        "error_message": conversion.error_message,
        "created_at": conversion.created_at.isoformat() if conversion.created_at else None,
        "completed_at": conversion.completed_at.isoformat() if conversion.completed_at else None,
    })


@app.delete("/api/file/{conversion_id}")
async def delete_file(request: Request, conversion_id: int, db: Session = Depends(get_db)):
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion:
        raise HTTPException(status_code=404, detail="변환 레코드를 찾을 수 없습니다.")
    if conversion.object_name:
        storage.delete_file(conversion.object_name)
    if conversion.output_object_name:
        storage.delete_file(conversion.output_object_name)
    upload_path = os.path.join(UPLOAD_DIR, conversion.stored_filename)
    if os.path.exists(upload_path):
        os.remove(upload_path)
    if conversion.output_filename:
        output_path = os.path.join(OUTPUT_DIR, conversion.output_filename)
        if os.path.exists(output_path):
            os.remove(output_path)
    db.delete(conversion)
    db.commit()
    return JSONResponse({"message": "삭제 완료"})


# === 배치 처리 ===
@app.api_route("/batch", methods=["GET","HEAD"], response_class=HTMLResponse)
async def batch_page(request: Request, db: Session = Depends(get_db)):
    google_user = get_google_user(request, db)
    return templates.TemplateResponse("batch.html", {
        "request": request,
        "user": google_user,
    })


@app.post("/batch/upload")
async def batch_upload(
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    
    session_id = request.session.get("session_id", str(uuid.uuid4()))
    
    uploaded_files = []
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            flash(request, f"{file.filename}: PDF 파일만 업로드 가능합니다.", "danger")
            return RedirectResponse("/batch", status_code=303)
        
        content = await file.read()
        
        # 임시 파일 저장 및 검증
        temp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
        with open(temp_path, "wb") as f:
            f.write(content)
        
        try:
            validator.check_magic_number(temp_path)
            validator.check_file_size(temp_path)
        except PDFValidationError as e:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            flash(request, f"{file.filename}: {str(e)}", "danger")
            return RedirectResponse("/batch", status_code=303)
        
        # Object Storage에 업로드
        stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
        object_name = f"uploads/{stored_filename}"
        storage.upload_file(object_name, content, "application/pdf")
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        uploaded_files.append({
            "filename": file.filename,
            "stored_filename": stored_filename,
            "object_name": object_name,
            "file_size": len(content),
            "temp_path": temp_path
        })
    
    # 세션에 파일 정보 저장
    request.session["batch_files"] = uploaded_files
    
    flash(request, f"{len(uploaded_files)}개 파일이 업로드되었습니다.", "success")
    return RedirectResponse("/batch/confirm", status_code=303)


@app.api_route("/batch/confirm", methods=["GET","HEAD"], response_class=HTMLResponse)
async def batch_confirm_page(request: Request):
    
    batch_files = request.session.get("batch_files", [])
    if not batch_files:
        flash(request, "업로드된 파일이 없습니다.", "danger")
        return RedirectResponse("/batch", status_code=303)
    
    return templates.TemplateResponse("batch_confirm.html", {
        "request": request,
        "files": batch_files,
    })


@app.post("/batch/convert")
async def batch_convert(
    request: Request,
    output_format: str = Form("excel"),
    pdf_type: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    
    batch_files = request.session.get("batch_files", [])
    if not batch_files:
        flash(request, "업로드된 파일이 없습니다.", "danger")
        return RedirectResponse("/batch", status_code=303)
    
    # 배치 작업 생성
    job_id = batch_processor.create_job(batch_files)
    
    # 각 파일에 대한 변환 레코드 생성
    conversion_ids = []
    for file_info in batch_files:
        conversion = Conversion(
            user_id=0,
            original_filename=file_info['filename'],
            stored_filename=file_info['stored_filename'],
            object_name=file_info['object_name'],
            file_size=file_info['file_size'],
            status="pending",
            output_format=output_format,
            pdf_type=pdf_type
        )
        db.add(conversion)
        db.commit()
        db.refresh(conversion)
        conversion_ids.append(conversion.id)
    
    # 세션 정리
    request.session.pop("batch_files", None)
    
    # 배치 처리 시작 (백그라운드)
    asyncio.create_task(
        _process_batch_conversions(conversion_ids, output_format, pdf_type)
    )
    
    flash(request, f"배치 변환이 시작되었습니다. ({len(conversion_ids)}개 파일)", "success")
    return RedirectResponse(f"/batch/status/{job_id}", status_code=303)


async def _process_batch_conversions(conversion_ids: List[int], output_format: str, pdf_type: Optional[str]):
    """배치 변환 처리 (백그라운드)"""
    from database import SessionLocal
    from parsers.roster import RosterParser
    from parsers.receipt import ReceiptParser
    from parsers.certificate import CertificateParser
    from exporters.excel import ExcelExporter
    from detectors.type_detector import PDFTypeDetector
    
    db = SessionLocal()
    try:
        for conversion_id in conversion_ids:
            conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
            if not conversion:
                continue
            
            conversion.status = "processing"
            db.commit()
            
            try:
                # PDF 다운로드
                pdf_content = storage.download_file(conversion.object_name)
                temp_input_path = f"/tmp/{conversion.stored_filename}"
                with open(temp_input_path, "wb") as f:
                    f.write(pdf_content)
                
                # PDF 타입 감지
                current_pdf_type = pdf_type
                if not current_pdf_type:
                    detector = PDFTypeDetector()
                    current_pdf_type = detector.detect(temp_input_path)
                    conversion.pdf_type = current_pdf_type
                
                # 파싱
                parsers = {
                    "roster": RosterParser(),
                    "receipt": ReceiptParser(),
                    "certificate": CertificateParser(),
                }
                parser = parsers.get(current_pdf_type, RosterParser())
                data = parser.parse(temp_input_path)
                
                # Excel로 변환
                output_filename = f"{conversion.stored_filename}.xlsx"
                temp_output_path = f"/tmp/{output_filename}"
                exporter = ExcelExporter()
                exporter.export(data, temp_output_path)
                
                # Object Storage에 업로드
                output_object_name = f"outputs/{output_filename}"
                with open(temp_output_path, "rb") as f:
                    excel_content = f.read()
                storage.upload_file(
                    output_object_name,
                    excel_content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                
                # 임시 파일 정리
                if os.path.exists(temp_input_path):
                    os.remove(temp_input_path)
                if os.path.exists(temp_output_path):
                    os.remove(temp_output_path)
                
                # 변환 완료
                conversion.output_filename = output_filename
                conversion.output_object_name = output_object_name
                conversion.status = "completed"
                conversion.completed_at = datetime.now()
                db.commit()
                
            except Exception as e:
                conversion.status = "failed"
                conversion.error_message = str(e)
                db.commit()
    finally:
        db.close()


@app.api_route("/batch/status/{job_id}", methods=["GET","HEAD"], response_class=HTMLResponse)
async def batch_status_page(request: Request, job_id: str):
    
    job = batch_processor.get_job(job_id)
    if not job:
        flash(request, "배치 작업을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/batch", status_code=303)
    
    return templates.TemplateResponse("batch_status.html", {
        "request": request,
        "job": job.to_dict(),
    })


@app.api_route("/api/batch/status/{job_id}", methods=["GET","HEAD"])
async def get_batch_status(request: Request, job_id: str):
    
    job = batch_processor.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="배치 작업을 찾을 수 없습니다.")
    
    return JSONResponse(job.to_dict())


# === Google Sheets 연동 ===
@app.api_route("/sheets/sync/{conversion_id}", methods=["GET","HEAD"])
async def sync_to_sheets(
    request: Request,
    conversion_id: int,
    spreadsheet_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    
    user = get_google_user(request, db)
    if not user:
        flash(request, "Google 계정이 연결되어 있지 않습니다.", "danger")
        return RedirectResponse(f"/download/{conversion_id}", status_code=303)
    
    conversion = db.query(Conversion).filter(Conversion.id == conversion_id).first()
    if not conversion or conversion.status != "completed":
        flash(request, "변환된 파일을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/upload", status_code=303)
    
    try:
        # Excel 파일에서 데이터 추출
        import pandas as pd
        temp_path = f"/tmp/{conversion.output_filename}"
        
        # Object Storage에서 다운로드
        excel_content = storage.download_file(conversion.output_object_name)
        with open(temp_path, "wb") as f:
            f.write(excel_content)
        
        # 데이터 읽기
        df = pd.read_excel(temp_path)
        data = [df.columns.tolist()] + df.values.tolist()
        
        # Google Sheets에 동기화
        credentials = google_sheets_manager.get_credentials(user.google_token)
        title = f"PDF2Sheet - {conversion.original_filename}"
        
        result = google_sheets_manager.auto_sync_to_sheets(
            credentials, data, title, spreadsheet_id
        )
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        flash(request, f"Google Sheets에 동기화되었습니다.", "success")
        return RedirectResponse(result['url'], status_code=302)
        
    except Exception as e:
        flash(request, f"동기화 중 오류가 발생했습니다: {str(e)}", "danger")
        return RedirectResponse(f"/download/{conversion_id}", status_code=303)


@app.api_route("/sheets/list", methods=["GET","HEAD"])
async def list_sheets(request: Request, db: Session = Depends(get_db)):
    
    user = get_google_user(request, db)
    if not user:
        raise HTTPException(status_code=400, detail="Google 계정이 연결되어 있지 않습니다.")
    
    try:
        credentials = google_sheets_manager.get_credentials(user.google_token)
        sheets = google_sheets_manager.list_spreadsheets(credentials)
        return JSONResponse(sheets)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === 속도 최적화 API ===
@app.api_route("/api/cache/clear", methods=["GET","HEAD"])
async def clear_cache(request: Request):
    
    parallel_processor.cache.clear()
    return JSONResponse({"message": "캐시가 삭제되었습니다."})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
