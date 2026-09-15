// 파일 업로드 처리
document.addEventListener('DOMContentLoaded', function() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileName = document.getElementById('file-name');
    const fileSize = document.getElementById('file-size');
    const removeFile = document.getElementById('remove-file');
    const uploadBtn = document.getElementById('upload-btn');
    const uploadForm = document.getElementById('upload-form');
    
    if (!uploadZone) return;
    
    // 클릭 시 파일 선택
    uploadZone.addEventListener('click', function() {
        fileInput.click();
    });
    
    // 드래그 앤 드롭
    uploadZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });
    
    uploadZone.addEventListener('dragleave', function() {
        uploadZone.classList.remove('dragover');
    });
    
    uploadZone.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFile(files[0]);
        }
    });
    
    // 파일 선택 시
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length > 0) {
            handleFile(fileInput.files[0]);
        }
    });
    
    // 파일 처리
    function handleFile(file) {
        // PDF 검증
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            alert('PDF 파일만 업로드 가능합니다.');
            return;
        }
        
        // 크기 검증 (50MB)
        if (file.size > 50 * 1024 * 1024) {
            alert('파일 크기가 50MB를 초과합니다.');
            return;
        }
        
        // 파일 정보 표시
        fileName.textContent = file.name;
        fileSize.textContent = formatFileSize(file.size);
        fileInfo.style.display = 'flex';
        uploadZone.style.display = 'none';
        uploadBtn.disabled = false;
    }
    
    // 파일 제거
    if (removeFile) {
        removeFile.addEventListener('click', function() {
            fileInput.value = '';
            fileInfo.style.display = 'none';
            uploadZone.style.display = 'block';
            uploadBtn.disabled = true;
        });
    }
    
    // 폼 제출
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            if (!fileInput.files.length) {
                e.preventDefault();
                alert('파일을 선택해주세요.');
            }
        });
    }
    
    // 파일 크기 포맷
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
});
