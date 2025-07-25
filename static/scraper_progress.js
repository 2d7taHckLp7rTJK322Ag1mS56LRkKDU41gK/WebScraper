document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Element Selectors ---
    const form = document.getElementById('scraper-form');
    const startButton = document.getElementById('start-scrape-btn');
    const progressContainer = document.getElementById('progress-container');
    const profileInfo = document.getElementById('profile-info');
    const profilePic = document.getElementById('profile-pic');
    const profileName = document.getElementById('profile-name');
    const profileId = document.getElementById('profile-id');
    const progressBar = document.getElementById('progress-bar');
    const progressStatus = document.getElementById('progress-status');
    const progressCount = document.getElementById('progress-count');

    let eventSource;

    // --- Form Submission Handler ---
    form.addEventListener('submit', (e) => {
        e.preventDefault();

        // Close any existing connection to prevent duplicates
        if (eventSource) {
            eventSource.close();
        }

        const platform = document.getElementById('platformSelect').value;
        const username = document.getElementById('usernameInput').value.trim();

        if (!username) {
            alert('Vui lòng nhập tên người dùng.');
            return;
        }

        // --- Reset and Prepare UI for a new run ---
        resetUI();
        startButton.disabled = true;
        startButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>`;
        progressContainer.style.display = 'block';

        // --- Initialize Server-Sent Events (SSE) connection ---
        const url = `/scrape-stream?platform=${platform}&username=${encodeURIComponent(username)}`;
        eventSource = new EventSource(url);

        // --- Event Listeners for SSE ---
        eventSource.onopen = function() {
            updateStatus('Đã kết nối, đang bắt đầu quá trình cào...');
            updateProgressBar(5, 'bg-info');
        };

        eventSource.onmessage = function(event) {
            try {
                const eventData = JSON.parse(event.data);
                handleServerEvent(eventData.type, eventData.data);
            } catch (error) {
                console.error('Failed to parse event data:', event.data, error);
            }
        };

        eventSource.onerror = function() {
            handleServerEvent('error', { message: 'Mất kết nối với máy chủ. Vui lòng thử lại.' });
            eventSource.close();
        };
    });

    // --- UI Update Functions ---
    function resetUI() {
        progressContainer.style.display = 'none';
        profileInfo.style.display = 'none';
        profilePic.src = '';
        profileName.textContent = '';
        profileId.textContent = '';
        progressStatus.textContent = '';
        progressCount.textContent = '';
        updateProgressBar(0, 'bg-primary');
    }

    function updateStatus(message) {
        progressStatus.textContent = message;
    }

    function updateProgressBar(percentage, cssClass = 'bg-primary') {
        progressBar.style.width = `${percentage}%`;
        progressBar.className = `progress-bar progress-bar-striped progress-bar-animated ${cssClass}`;
    }

    function displayProfile(data) {
        profileName.textContent = data.name || 'Không có tên';
        profileId.textContent = `ID: ${data.id || 'N/A'}`;
        profilePic.src = data.profile_pic_url || 'https://placehold.co/80x80/eee/ccc?text=?';
        profileInfo.style.display = 'block';
    }
    
    // --- Main Event Handling Logic ---
    function handleServerEvent(type, data) {
        switch (type) {
            case 'status':
                updateStatus(data.message);
                break;

            case 'profile':
                displayProfile(data);
                updateProgressBar(20);
                break;

            case 'progress':
                progressCount.textContent = `${data.found} bài đăng`;
                // Make progress bar move slowly towards 80%
                const currentWidth = parseFloat(progressBar.style.width) || 20;
                if (currentWidth < 80) {
                     updateProgressBar(currentWidth + 2);
                }
                break;

            case 'done':
                updateStatus(data.message);
                updateProgressBar(100, 'bg-success');
                progressCount.textContent = ''; // Clear count on completion
                finish();
                break;

            case 'error':
                updateStatus(`Lỗi: ${data.message}`);
                updateProgressBar(100, 'bg-danger');
                finish();
                break;
        }
    }
    
    function finish() {
        if (eventSource) {
            eventSource.close();
        }
        startButton.disabled = false;
        startButton.innerHTML = 'Cào';
        progressBar.classList.remove('progress-bar-animated');
    }
});
