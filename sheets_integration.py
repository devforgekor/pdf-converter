"""
Google Sheets API 연동

참조 소스:
- Google Sheets API Python Quickstart: https://developers.google.com/sheets/api/quickstart/python
- Google API Python Client: google.oauth2.credentials, googleapiclient.discovery
"""
import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


class GoogleSheetsManager:
    """Google Sheets 통합 관리자"""
    
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/userinfo.email',
    ]
    
    def __init__(self):
        self.client_id = os.getenv('GOOGLE_CLIENT_ID')
        self.client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GOOGLE_REDIRECT_URI', 'https://kuhwa.duckdns.org/auth/google/callback')
    
    def get_oauth_flow(self, state: Optional[str] = None) -> Flow:
        """OAuth 플로우 생성"""
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri]
                }
            },
            scopes=self.SCOPES,
            state=state
        )
        flow.redirect_uri = self.redirect_uri
        return flow
    
    def get_credentials(self, token_data: Dict[str, Any]) -> Credentials:
        """토큰 데이터로 자격증명 생성"""
        return Credentials(
            token=token_data.get('access_token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.SCOPES
        )
    
    def create_spreadsheet(self, credentials: Credentials, title: str, 
                          data: List[List[Any]], folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Google 스프레드시트 생성"""
        service = build('sheets', 'v4', credentials=credentials)
        
        # 스프레드시트 생성
        spreadsheet_body = {
            'properties': {
                'title': title,
                'locale': 'ko_KR',
                'timeZone': 'Asia/Seoul'
            }
        }
        
        if folder_id:
            spreadsheet_body['properties']['parentId'] = folder_id
        
        spreadsheet = service.spreadsheets().create(
            body=spreadsheet_body
        ).execute()
        
        spreadsheet_id = spreadsheet['spreadsheetId']
        
        # 데이터 삽입
        if data:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range='A1',
                valueInputOption='RAW',
                body={'values': data}
            ).execute()
        
        # 스타일 적용
        self._apply_styles(service, spreadsheet_id, len(data), len(data[0]) if data else 0)
        
        return {
            'spreadsheet_id': spreadsheet_id,
            'url': f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}",
            'title': title
        }
    
    def _apply_styles(self, service, spreadsheet_id: str, rows: int, cols: int):
        """헤더 스타일 적용"""
        if rows == 0 or cols == 0:
            return
        
        requests = [
            {
                'repeatCell': {
                    'range': {
                        'sheetId': 0,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': cols
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9},
                            'textFormat': {'bold': True},
                            'horizontalAlignment': 'CENTER'
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
                }
            }
        ]
        
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={'requests': requests}
        ).execute()
    
    def update_spreadsheet(self, credentials: Credentials, spreadsheet_id: str,
                          data: List[List[Any]], sheet_name: str = 'Sheet1') -> bool:
        """기존 스프레드시트 업데이트"""
        try:
            service = build('sheets', 'v4', credentials=credentials)
            
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A:Z'
            ).execute()
            
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f'{sheet_name}!A1',
                valueInputOption='RAW',
                body={'values': data}
            ).execute()
            
            return True
        except Exception as e:
            print(f"스프레드시트 업데이트 오류: {e}")
            return False
    
    def upload_to_drive(self, credentials: Credentials, file_path: str,
                       folder_id: Optional[str] = None) -> Dict[str, Any]:
        """Google Drive에 파일 업로드"""
        service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': os.path.basename(file_path),
            'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }
        
        if folder_id:
            file_metadata['parents'] = [folder_id]
        
        media = MediaFileUpload(file_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        return {
            'file_id': file.get('id'),
            'url': file.get('webViewLink'),
            'name': file_metadata['name']
        }
    
    def list_spreadsheets(self, credentials: Credentials, limit: int = 10) -> List[Dict[str, Any]]:
        """스프레드시트 목록 조회"""
        service = build('drive', 'v3', credentials=credentials)
        
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=limit,
            fields="files(id, name, createdTime, modifiedTime)",
            orderBy="modifiedTime desc"
        ).execute()
        
        return results.get('files', [])
    
    def get_spreadsheet_data(self, credentials: Credentials, 
                            spreadsheet_id: str, range_name: str = 'Sheet1') -> List[List[Any]]:
        """스프레드시트 데이터 조회"""
        service = build('sheets', 'v4', credentials=credentials)
        
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        
        return result.get('values', [])
    
    def auto_sync_to_sheets(self, credentials: Credentials, data: List[List[Any]],
                           title: str, existing_id: Optional[str] = None) -> Dict[str, Any]:
        """자동 동기화: 기존 스프레드시트 업데이트 또는 새 스프레드시트 생성"""
        if existing_id:
            success = self.update_spreadsheet(credentials, existing_id, data)
            if success:
                return {
                    'action': 'updated',
                    'spreadsheet_id': existing_id,
                    'url': f"https://docs.google.com/spreadsheets/d/{existing_id}"
                }
        
        return self.create_spreadsheet(credentials, title, data)


# 전역 인스턴스
google_sheets_manager = GoogleSheetsManager()
