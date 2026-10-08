"""이수증 템플릿 관리 라우트"""
import os
import uuid
import json
import re
import tempfile
import subprocess
import pandas as pd
from datetime import datetime

from fastapi import APIRouter, File, UploadFile, Form, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from database import get_db
from models import CertificateTemplate, CertificateRecord, ExampleFile
from storage import storage
from flash import flash, get_flashed_messages
from csrf import generate_csrf_token
from parsers import parser_registry
from layout_analyzer import analyzer
from exporters.excel import ExcelExporter

templates = Jinja2Templates(directory="templates")
templates.env.globals["get_flashed_messages"] = get_flashed_messages
templates.env.globals["csrf_token"] = generate_csrf_token
router = APIRouter()


def require_auth(request: Request):
    if not request.session.get("pin_authenticated"):
        return True
    return False


# === 템플릿 관리 페이지 ===
@router.get("/admin/templates", response_class=HTMLResponse)
async def admin_templates_page(request: Request, db: Session = Depends(get_db)):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    templates_list = db.query(CertificateTemplate).order_by(CertificateTemplate.created_at.desc()).all()
    examples = db.query(ExampleFile).filter(ExampleFile.file_type == "excel").all()
    return templates.TemplateResponse("admin_templates.html", {
        "request": request,
        "templates": templates_list,
        "examples": examples,
    })


@router.post("/admin/templates/create")
async def create_template(
    request: Request,
    name: str = Form(...),
    issuer: str = Form(""),
    description: str = Form(""),
    parsing_patterns: str = Form(""),
    field_mapping: str = Form(""),
    linked_form_id: int = Form(0),
    output_sheet_name: str = Form(""),
    output_start_row: int = Form(2),
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    form_object_name = None
    form_original_name = None
    if linked_form_id:
        example = db.query(ExampleFile).filter(ExampleFile.id == linked_form_id).first()
        if example:
            form_object_name = example.object_name
            form_original_name = example.original_filename

    template = CertificateTemplate(
        name=name,
        issuer=issuer,
        description=description,
        parsing_patterns=parsing_patterns,
        field_mapping=field_mapping,
        linked_form_object_name=form_object_name,
        linked_form_original_name=form_original_name,
        output_sheet_name=output_sheet_name,
        output_start_row=output_start_row,
    )
    db.add(template)
    db.commit()

    flash(request, f"템플릿 '{name}'이(가) 생성되었습니다.", "success")
    return RedirectResponse("/admin/templates", status_code=303)


@router.post("/admin/templates/{template_id}/delete")
async def delete_template(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if template:
        db.delete(template)
        db.commit()
        flash(request, "템플릿이 삭제되었습니다.", "success")
    return RedirectResponse("/admin/templates", status_code=303)


@router.get("/admin/templates/{template_id}/edit", response_class=HTMLResponse)
async def edit_template_page(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        return RedirectResponse("/admin/templates", status_code=303)

    examples = db.query(ExampleFile).filter(ExampleFile.file_type == "excel").all()
    return templates.TemplateResponse("admin_template_edit.html", {
        "request": request,
        "template": template,
        "examples": examples,
    })


@router.post("/admin/templates/{template_id}/update")
async def update_template(
    request: Request,
    template_id: int,
    name: str = Form(...),
    issuer: str = Form(""),
    description: str = Form(""),
    parsing_patterns: str = Form(""),
    field_mapping: str = Form(""),
    linked_form_id: int = Form(0),
    output_sheet_name: str = Form(""),
    output_start_row: int = Form(2),
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        return RedirectResponse("/admin/templates", status_code=303)

    form_object_name = None
    form_original_name = None
    if linked_form_id:
        example = db.query(ExampleFile).filter(ExampleFile.id == linked_form_id).first()
        if example:
            form_object_name = example.object_name
            form_original_name = example.original_filename

    template.name = name
    template.issuer = issuer
    template.description = description
    template.parsing_patterns = parsing_patterns
    template.field_mapping = field_mapping
    template.linked_form_object_name = form_object_name
    template.linked_form_original_name = form_original_name
    template.output_sheet_name = output_sheet_name
    template.output_start_row = output_start_row
    db.commit()

    flash(request, "템플릿이 수정되었습니다.", "success")
    return RedirectResponse("/admin/templates", status_code=303)


# === 예시 PDF 분석 (파싱 규칙 학습) ===
@router.post("/admin/templates/{template_id}/learn")
async def learn_from_example(
    request: Request,
    template_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        flash(request, "템플릿을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/admin/templates", status_code=303)

    # PDF 텍스트 추출
    content = await file.read()
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result = subprocess.run(['pdftotext', '-layout', tmp_path, '-'], capture_output=True, text=True)
        pdf_text = result.stdout
    finally:
        os.unlink(tmp_path)

    # 레이아웃 분석
    analysis = analyzer.analyze(pdf_text)
    parsing_config = analyzer.to_parsing_config(analysis)

    # 템플릿에 규칙 저장
    template.parsing_patterns = parsing_config
    db.commit()

    flash(request, f"파싱 규칙이 학습되었습니다. ({len(analysis['labels'])}개 필드 감지)", "success")
    return RedirectResponse(f"/admin/templates/{template_id}/edit", status_code=303)


@router.get("/admin/templates/{template_id}/learn-preview")
async def learn_preview(
    request: Request,
    template_id: int,
    db: Session = Depends(get_db),
):
    """학습된 파싱 규칙 미리보기 (API)"""
    if require_auth(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        return JSONResponse({"error": "template not found"}, status_code=404)

    patterns = {}
    if template.parsing_patterns:
        try:
            patterns = json.loads(template.parsing_patterns)
        except json.JSONDecodeError:
            pass

    return {"template_id": template_id, "patterns": patterns}


# === 이수증 자동 파싱 ===
@router.get("/certificate/auto-parse", response_class=HTMLResponse)
async def auto_parse_page(request: Request, db: Session = Depends(get_db)):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    templates_list = db.query(CertificateTemplate).all()
    return templates.TemplateResponse("admin_auto_parse.html", {
        "request": request,
        "templates_list": templates_list,
    })


@router.post("/certificate/auto-parse")
async def auto_parse_certificate(
    request: Request,
    template_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        flash(request, "템플릿을 찾을 수 없습니다.", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    content = await file.read()
    pdf_object_name = f"certificates/{uuid.uuid4().hex}_{file.filename}"
    try:
        storage.upload_file(pdf_object_name, content, "application/pdf")
    except Exception as e:
        flash(request, f"파일 업로드 실패: {str(e)}", "danger")
        return RedirectResponse("/certificate/safety", status_code=303)

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        # 1차: pdftotext (기본)
        result = subprocess.run(['pdftotext', '-layout', tmp_path, '-'], capture_output=True, text=True)
        pdf_text = result.stdout

        # pdftotext 결과가 부족하면 Azure DI로 재시도
        if len(pdf_text.strip()) < 50:
            azure_parser = parser_registry.get("azure_di")
            if azure_parser and azure_parser.is_enabled():
                with open(tmp_path, "rb") as f:
                    pdf_bytes = f.read()
                ir = azure_parser.parse_read(pdf_bytes)
                pdf_text = ir.metadata.get("full_text", "")
    finally:
        os.unlink(tmp_path)

    # 레지스트리에서 파서 가져오기 (이수증 기본)
    doc_type = "이수증"
    if template.doc_type:
        doc_type = template.doc_type
    
    # Azure DI 텍스트 소스 처리: Azure DI 파서가 지정되면 PDF에서 직접 텍스트 추출
    if doc_type == "azure_di":
        azure_parser = parser_registry.get("azure_di")
        if azure_parser and azure_parser.is_enabled():
            with open(pdf_object_name if os.path.exists(pdf_object_name) else tmp_path, "rb") as f:
                pdf_bytes = f.read()
            ir = azure_parser.parse_read(pdf_bytes)
            pdf_text = ir.metadata.get("full_text", "")
        else:
            flash(request, "Azure DI가 비활성화되어 있습니다.", "error")
            return RedirectResponse("/certificate/records", status_code=303)
    
    parser = parser_registry.get(doc_type)
    if parser is None:
        flash(request, f"지원하지 않는 문서 유형입니다: {doc_type}", "error")
        return RedirectResponse("/certificate/records", status_code=303)
    
    # pdftotext 정규화기로 파싱 시도
    from text_normalizer import normalizer
    normalized = normalizer.normalize(pdf_text)
    pairs = normalizer.parse_label_value_pairs(normalized)
    
    # pdftotext로 충분한 필드가 추출됐으면 사용
    if len(pairs) >= 5:
        ir = parser.parse(pdf_text)
        parsed_data = ir.fields
    else:
        # pdftotext 실패 시 Azure DI 폴백
        azure_parser = parser_registry.get("azure_di")
        if azure_parser and azure_parser.is_enabled():
            import re
            # Azure DI에서 다시 텍스트 추출
            with open(tmp_path, "rb") as f:
                pdf_bytes = f.read()
            ir_azure = azure_parser.parse_read(pdf_bytes)
            azure_text = ir_azure.metadata.get("full_text", "")
            
            from text_normalizer import azure_di_normalizer
            normalized_azure = azure_di_normalizer.normalize(azure_text)
            pairs_azure = azure_di_normalizer.parse_label_value_pairs(normalized_azure)
            
            field_map = {
                "성명": "성명", "생년월일": "생년월일", "직급": "직급",
                "근무기관": "근무기관", "연수기간": "연수기간", "연수종류": "연수종류",
                "이수시간": "이수시간", "이수번호": "이수번호",
            }
            parsed_data = {}
            for key, pair_key in field_map.items():
                if pair_key in pairs_azure:
                    value = pairs_azure[pair_key]
                    if key == "이수시간":
                        match = re.search(r'(\d+)', value)
                        if match:
                            value = match.group(1)
                    elif key in ["근무기관", "연수종류"]:
                        value = value.replace(' ', '')
                    parsed_data[key] = value
            
            lines = azure_text.split('\n')
            for i, line in enumerate(lines):
                if '과정명:' in line or '과 정 명 :' in line:
                    parts = re.split(r'과정명\s*:\s*|과\s*정\s*명\s*:\s*', line, maxsplit=1)
                    if len(parts) == 2:
                        course_name = parts[1].strip()
                        if i + 1 < len(lines) and lines[i + 1].strip():
                            next_line = lines[i + 1].strip()
                            if not any(kw in next_line for kw in ['성명:', '생년월일:', '직급:', '근무기관:']):
                                course_name += next_line
                        parsed_data["과정명"] = course_name
                    break
            
            for line in lines:
                match = re.search(r'(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일', line)
                if match:
                    year, month, day = match.group(1), match.group(2).zfill(2), match.group(3).zfill(2)
                    parsed_data["수료일"] = f"{year}.{month}.{day}."
                    break
            
            for line in lines:
                match = re.search(r'제\s+(\S+)\s*호', line)
                if match:
                    parsed_data["이수번호"] = match.group(1)
                    break
            
            parsed_data["기관"] = parser.detect_institution(azure_text)
        else:
            ir = parser.parse(pdf_text)
            parsed_data = ir.fields

    verification_code = f"CERT-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

    # 이수시간 안전 변환
    hours_val = None
    raw_hours = parsed_data.get('이수시간', '')
    if raw_hours:
        import re as _re
        match = _re.search(r'(\d+)', str(raw_hours))
        if match:
            hours_val = int(match.group(1))

    record = CertificateRecord(
        template_id=template_id,
        original_pdf_object_name=pdf_object_name,
        original_pdf_filename=file.filename,
        parsed_data=json.dumps(parsed_data, ensure_ascii=False),
        holder_name=parsed_data.get('성명'),
        holder_birth=parsed_data.get('생년월일'),
        course_name=parsed_data.get('과정명'),
        hours=hours_val,
        certificate_number=parsed_data.get('이수번호'),
        verification_code=verification_code,
    )
    db.add(record)
    db.commit()

    flash(request, f"파싱 완료: {parsed_data.get('성명', '알 수 없음')} ({verification_code})", "success")
    return RedirectResponse(f"/certificate/records/{record.id}", status_code=303)


# === 파싱 기록 관리 ===
@router.get("/certificate/records", response_class=HTMLResponse)
async def certificate_records_page(request: Request, db: Session = Depends(get_db)):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    records = db.query(CertificateRecord).order_by(CertificateRecord.created_at.desc()).all()
    templates_list = db.query(CertificateTemplate).all()
    return templates.TemplateResponse("certificate_records.html", {
        "request": request,
        "records": records,
        "templates": templates_list,
    })


@router.get("/certificate/records/{record_id}", response_class=HTMLResponse)
async def certificate_record_detail(
    request: Request,
    record_id: int,
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    record = db.query(CertificateRecord).filter(CertificateRecord.id == record_id).first()
    if not record:
        return RedirectResponse("/certificate/records", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == record.template_id).first()

    parsed_data = {}
    if record.parsed_data:
        try:
            parsed_data = json.loads(record.parsed_data)
        except json.JSONDecodeError:
            pass

    return templates.TemplateResponse("certificate_record_detail.html", {
        "request": request,
        "record": record,
        "template": template,
        "parsed_data": parsed_data,
    })


@router.post("/certificate/records/{record_id}/delete")
async def delete_certificate_record(
    request: Request,
    record_id: int,
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    record = db.query(CertificateRecord).filter(CertificateRecord.id == record_id).first()
    if record:
        if record.original_pdf_object_name:
            try:
                storage.delete_file(record.original_pdf_object_name)
            except Exception:
                pass
        db.delete(record)
        db.commit()
        flash(request, "기록이 삭제되었습니다.", "success")
    return RedirectResponse("/certificate/records", status_code=303)


@router.post("/certificate/export")
async def export_certificate_records(
    request: Request,
    template_id: int = Form(...),
    record_ids: str = Form(""),
    db: Session = Depends(get_db),
):
    if require_auth(request):
        return RedirectResponse("/login", status_code=303)

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == template_id).first()
    if not template:
        flash(request, "템플릿을 찾을 수 없습니다.", "error")
        return RedirectResponse("/certificate/records", status_code=303)

    # record_ids가 있으면 해당 기록, 없으면 해당 템플릿의 모든 기록
    if record_ids:
        try:
            id_list = [int(rid.strip()) for rid in record_ids.split(",") if rid.strip()]
        except ValueError:
            flash(request, "잘못된 기록 ID입니다.", "error")
            return RedirectResponse("/certificate/records", status_code=303)
        records = db.query(CertificateRecord).filter(
            CertificateRecord.id.in_(id_list),
            CertificateRecord.template_id == template_id
        ).all()
    else:
        records = db.query(CertificateRecord).filter(
            CertificateRecord.template_id == template_id
        ).all()

    if not records:
        flash(request, "내보낼 기록이 없습니다.", "error")
        return RedirectResponse("/certificate/records", status_code=303)

    # field_mapping 파싱
    field_mapping = {}
    if template.field_mapping:
        try:
            field_mapping = json.loads(template.field_mapping)
        except (json.JSONDecodeError, ValueError):
            pass

    # 기본 필드 매핑 (field_mapping이 없을 경우)
    default_fields = ["성명", "생년월일", "직급", "근무기관", "과정명", "연수기간", "연수종류", "이수시간", "이수번호", "수료일"]

    # 엑셀 데이터 구성
    rows = []
    for record in records:
        parsed = {}
        if record.parsed_data:
            try:
                parsed = json.loads(record.parsed_data)
            except (json.JSONDecodeError, ValueError):
                pass

        row = {}
        for field in default_fields:
            row[field] = parsed.get(field, "")
        rows.append(row)

    # DataFrame 생성
    df = pd.DataFrame(rows)

    # Excel 파일 저장
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{template.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    output_path = os.path.join(output_dir, filename)

    exporter = ExcelExporter()
    exporter.export(df, output_path)

    # OCI에 업로드 (선택사항)
    try:
        object_name = f"exports/{filename}"
        with open(output_path, "rb") as f:
            storage.upload_file(object_name, f.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        pass

    # 파일 다운로드
    return FileResponse(
        output_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/api/certificate/verify/{verification_code}")
async def verify_certificate(verification_code: str, db: Session = Depends(get_db)):
    record = db.query(CertificateRecord).filter(
        CertificateRecord.verification_code == verification_code
    ).first()
    if not record:
        return {"valid": False, "message": "인증서를 찾을 수 없습니다."}

    template = db.query(CertificateTemplate).filter(CertificateTemplate.id == record.template_id).first()
    return {
        "valid": True,
        "holder_name": record.holder_name,
        "course_name": record.course_name,
        "hours": record.hours,
        "completion_date": record.completion_date,
        "certificate_number": record.certificate_number,
        "template_name": template.name if template else None,
        "issuer": template.issuer if template else None,
    }
