import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from dotenv import load_dotenv
from authlib.integrations.starlette_client import OAuth
import httpx

from database import engine, get_db, Base
from models import User, Conversion
from flash import flash, get_flashed_messages
from csrf import generate_csrf_token, validate_csrf_token

load_dotenv()

# 테이블 생성
Base.metadata.create_all(bind=engine)

app = FastAPI(title="PDF to Spreadsheet")

# Google OAuth 설정
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)


# CSRF 미들웨어
class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # GET, HEAD, OPTIONS 요청은 CSRF 검증 건너뜀
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        # 세션 미들웨어가 아직 실행되지 않았을 수 있으므로 안전하게 처리
        try:
            # 세션에서 CSRF 토큰 확인
            session_token = request.session.get("csrf_token")
        except Exception:
            # 세션이 설정되지 않은 경우 CSRF 검증 건너뜀
            return await call_next(request)

        if not session_token:
            return await call_next(request)

        # 헤더 또는 폼 데이터에서 토큰 확인
        header_token = request.headers.get("X-CSRF-Token")

        if not header_token and request.method in ("POST", "PUT", "DELETE"):
            try:
                form = await request.form()
                header_token = form.get("csrf_token")
            except Exception:
                pass

        # 토큰 검증 (토큰이 있는 경우에만)
        if header_token and session_token:
            import secrets
            if not secrets.compare_digest(session_token, str(header_token)):
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    {"detail": "CSRF 토큰이 일치하지 않습니다."},
                    status_code=403
                )

        return await call_next(request)


# 세션 미들웨어
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-in-production"),
    session_cookie="session_id",
    max_age=3600,
    same_site="lax",
    https_only=False,
)
app.add_middleware(CSRFMiddleware)

# 정적 파일 마운트
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿
templates = Jinja2Templates(directory="templates")
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals["csrf_token"] = generate_csrf_token

# 비밀번호 해싱
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 업로드/출력 디렉토리
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# === 의존성 주입 ===
def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if user_id:
        return db.query(User).filter(User.id == user_id).first()
    return None


# === 인증 관련 라우트 ===
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/auth/google")
async def google_login(request: Request):
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    
    if not user_info:
        flash(request, "Google 인증에 실패했습니다.", "danger")
        return RedirectResponse("/login", status_code=303)
    
    email = user_info.get('email', '')
    
    # 도메인 제한 (@kuhwa.sen.sc.kr만 허용)
    if not email.endswith("@kuhwa.sen.sc.kr"):
        flash(request, "@kuhwa.sen.sc.kr 이메일만 사용 가능합니다.", "danger")
        return RedirectResponse("/login", status_code=303)
    
    # 사용자 조회 또는 생성
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # 새 사용자 생성
        user = User(
            username=email.split('@')[0],
            email=email,
            hashed_password=pwd_context.hash(uuid.uuid4().hex),  # 랜덤 비밀번호
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # 세션에 사용자 정보 저장
    request.session["user_id"] = user.id
    flash(request, f"환영합니다, {user.username}님!", "success")
    return RedirectResponse("/", status_code=303)


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_context.verify(password, user.hashed_password):
        flash(request, "아이디 또는 비밀번호가 올바르지 않습니다.", "danger")
        return RedirectResponse("/login", status_code=303)

    request.session["user_id"] = user.id
    flash(request, f"환영합니다, {user.username}님!", "success")
    return RedirectResponse("/", status_code=303)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # 비밀번호 최소 길이 검증
    if len(password) < 8:
        flash(request, "비밀번호는 최소 8자 이상이어야 합니다.", "danger")
        return RedirectResponse("/register", status_code=303)

    # 사용자명 유효성 검증
    if len(username) < 3 or len(username) > 50:
        flash(request, "사용자명은 3자 이상 50자 이하여야 합니다.", "danger")
        return RedirectResponse("/register", status_code=303)

    # 중복 확인
    if db.query(User).filter(User.username == username).first():
        flash(request, "이미 존재하는 사용자명입니다.", "danger")
        return RedirectResponse("/register", status_code=303)

    if db.query(User).filter(User.email == email).first():
        flash(request, "이미 존재하는 이메일입니다.", "danger")
        return RedirectResponse("/register", status_code=303)

    # 사용자 생성
    user = User(
        username=username,
        email=email,
        hashed_password=pwd_context.hash(password),
    )
    db.add(user)
    db.commit()

    flash(request, "회원가입이 완료되었습니다. 로그인해주세요.", "success")
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# === 메인 페이지 (업로드) ===
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # 사용자의 최근 변환 이력
    recent_conversions = (
        db.query(Conversion)
        .filter(Conversion.user_id == user.id)
        .order_by(Conversion.created_at.desc())
        .limit(5)
        .all()
    )
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "user": user,
        "recent_conversions": recent_conversions,
    })


@app.post("/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # PDF 파일 검증
    if not file.filename.lower().endswith(".pdf"):
        flash(request, "PDF 파일만 업로드 가능합니다.", "danger")
        return RedirectResponse("/", status_code=303)

    # 파일 크기 검증 (50MB)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        flash(request, "파일 크기가 50MB를 초과합니다.", "danger")
        return RedirectResponse("/", status_code=303)

    # 파일 저장
    stored_filename = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, stored_filename)
    with open(file_path, "wb") as f:
        f.write(content)

    # DB 레코드 생성
    conversion = Conversion(
        user_id=user.id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_size=len(content),
        status="pending",
    )
    db.add(conversion)
    db.commit()
    db.refresh(conversion)

    flash(request, "파일이 업로드되었습니다.", "success")
    return RedirectResponse(f"/convert/{conversion.id}", status_code=303)


# === 변환 설정 페이지 ===
@app.get("/convert/{conversion_id}", response_class=HTMLResponse)
async def convert_page(
    request: Request,
    conversion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse("convert.html", {
        "request": request,
        "user": user,
        "conversion": conversion,
    })


@app.post("/convert/{conversion_id}")
async def start_conversion(
    request: Request,
    conversion_id: int,
    output_format: str = Form("excel"),
    pdf_type: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/", status_code=303)

    # 변환 시작
    conversion.output_format = output_format
    conversion.pdf_type = pdf_type
    conversion.status = "processing"
    db.commit()

    # PDF 변환 실행
    try:
        from parsers.base import BaseParser
        from parsers.roster import RosterParser
        from parsers.receipt import ReceiptParser
        from parsers.certificate import CertificateParser
        from exporters.excel import ExcelExporter
        from detectors.type_detector import PDFTypeDetector

        input_path = os.path.join(UPLOAD_DIR, conversion.stored_filename)

        # PDF 유형 감지
        if not pdf_type:
            detector = PDFTypeDetector()
            pdf_type = detector.detect(input_path)
            conversion.pdf_type = pdf_type

        # 파서 선택
        parsers = {
            "roster": RosterParser(),
            "receipt": ReceiptParser(),
            "certificate": CertificateParser(),
        }
        parser = parsers.get(pdf_type, RosterParser())

        # PDF 파싱
        data = parser.parse(input_path)

        # Excel 출력
        output_filename = f"{conversion.stored_filename}.xlsx"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        exporter = ExcelExporter()
        exporter.export(data, output_path)

        # 완료 처리
        conversion.output_filename = output_filename
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


# === 결과 다운로드 ===
@app.get("/download/{conversion_id}", response_class=HTMLResponse)
async def download_page(
    request: Request,
    conversion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
    if not conversion:
        flash(request, "변환 레코드를 찾을 수 없습니다.", "danger")
        return RedirectResponse("/", status_code=303)

    return templates.TemplateResponse("download.html", {
        "request": request,
        "user": user,
        "conversion": conversion,
    })


@app.get("/download/{conversion_id}/file")
async def download_file(
    conversion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
    if not conversion or conversion.status != "completed":
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")

    output_path = os.path.join(OUTPUT_DIR, conversion.output_filename)
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="파일이 존재하지 않습니다.")

    # Excel 파일 다운로드
    download_name = conversion.original_filename.replace(".pdf", ".xlsx")
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=download_name,
    )


# === 변환 이력 ===
@app.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversions = (
        db.query(Conversion)
        .filter(Conversion.user_id == user.id)
        .order_by(Conversion.created_at.desc())
        .all()
    )
    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "conversions": conversions,
    })


# === API 엔드포인트 ===
@app.get("/api/status/{conversion_id}")
async def get_status(
    conversion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
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
async def delete_file(
    conversion_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversion = db.query(Conversion).filter(
        Conversion.id == conversion_id,
        Conversion.user_id == user.id,
    ).first()
    if not conversion:
        raise HTTPException(status_code=404, detail="변환 레코드를 찾을 수 없습니다.")

    # 파일 삭제
    upload_path = os.path.join(UPLOAD_DIR, conversion.stored_filename)
    if os.path.exists(upload_path):
        os.remove(upload_path)

    if conversion.output_filename:
        output_path = os.path.join(OUTPUT_DIR, conversion.output_filename)
        if os.path.exists(output_path):
            os.remove(output_path)

    # DB 레코드 삭제
    db.delete(conversion)
    db.commit()

    return JSONResponse({"message": "삭제 완료"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
