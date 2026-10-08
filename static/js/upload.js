document.addEventListener('DOMContentLoaded', function() {
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const fileInfo = document.getElementById('file-info');
    const fileList = document.getElementById('file-list');
    const fileSummary = document.getElementById('file-summary');
    const uploadBtn = document.getElementById('upload-btn');
    const form = document.getElementById('upload-form');
    const modeSingle = document.getElementById('mode-single');
    const modeBatch = document.getElementById('mode-batch');
    
    let selectedFiles = [];
    
    // 드래그 앤 드롭
    uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadZone.classList.add('dragover');
    });
    
    uploadZone.addEventListener('dragleave', () => {
        uploadZone.classList.remove('dragover');
    });
    
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        
        const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith('.pdf'));
        addFiles(files);
    });
    
    // 클릭 업로드
    uploadZone.addEventListener('click', () => {
        fileInput.click();
    });
    
    fileInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        addFiles(files);
        fileInput.value = ''; // 같은 파일 재선택 가능하도록
    });
    
    function addFiles(newFiles) {
        // 중복 파일 제거
        const existingNames = new Set(selectedFiles.map(f => f.name));
        const uniqueFiles = newFiles.filter(f => !existingNames.has(f.name));
        
        selectedFiles = [...selectedFiles, ...uniqueFiles];
        updateFileList();
        updateUploadButton();
        updateModeOptions();
    }
    
    function updateFileList() {
        if (selectedFiles.length === 0) {
            fileInfo.style.display = 'none';
            return;
        }
        
        fileInfo.style.display = 'block';
        
        fileList.innerHTML = selectedFiles.map((file, index) => `
            <div class="file-item">
                <div class="file-icon-small">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                </div>
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
                <button type="button" class="remove-btn" onclick="removeFile(${index})" title="파일 제거">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
        `).join('');
        
        // 요약 정보
        const totalSize = selectedFiles.reduce((sum, f) => sum + f.size, 0);
        fileSummary.innerHTML = `
            <span class="summary-text">
                ${selectedFiles.length}개 파일 선택됨 (총 ${formatFileSize(totalSize)})
            </span>
        `;
    }
    
    function updateUploadButton() {
        uploadBtn.disabled = selectedFiles.length === 0;
        
        if (selectedFiles.length === 0) {
            uploadBtn.textContent = '파일을 선택하세요';
        } else if (selectedFiles.length === 1) {
            uploadBtn.textContent = '업로드 및 변환 설정';
        } else {
            uploadBtn.textContent = `${selectedFiles.length}개 파일 업로드 및 변환 설정`;
        }
    }
    
    function updateModeOptions() {
        if (selectedFiles.length <= 1) {
            modeSingle.checked = true;
            modeBatch.disabled = true;
            modeBatch.parentElement.classList.add('disabled');
        } else {
            modeBatch.disabled = false;
            modeBatch.parentElement.classList.remove('disabled');
        }
    }
    
    window.removeFile = function(index) {
        selectedFiles.splice(index, 1);
        updateFileList();
        updateUploadButton();
        updateModeOptions();
    };
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // 폼 제출
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        if (selectedFiles.length === 0) {
            return;
        }
        
        const formData = new FormData();
        const csrfToken = form.querySelector('input[name="csrf_token"]').value;
        formData.append('csrf_token', csrfToken);
        formData.append('upload_mode', document.querySelector('input[name="upload_mode"]:checked').value);
        
        selectedFiles.forEach(file => {
            formData.append('files', file);
        });
        
        uploadBtn.disabled = true;
        uploadBtn.textContent = '업로드 중...';
        
        fetch('/upload', {
            method: 'POST',
            body: formData
        }).then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else if (response.ok) {
                window.location.reload();
            } else {
                response.text().then(text => {
                    alert('업로드 중 오류가 발생했습니다: ' + text);
                    uploadBtn.disabled = false;
                    updateUploadButton();
                });
            }
        }).catch(error => {
            alert('업로드 중 오류가 발생했습니다: ' + error.message);
            uploadBtn.disabled = false;
            updateUploadButton();
        });
    });
});
