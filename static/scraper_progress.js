document.addEventListener('DOMContentLoaded', () => {
    // === DOM Element Selectors ===
    const form = document.getElementById('scraper-form');
    const platformSelect = document.getElementById('platformSelect');
    const usernameInput = document.getElementById('usernameInput');
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
    let checkUserTimeout;

    // === Helper Functions ===
    function debounce(func, delay) {
        return function(...args) {
            clearTimeout(checkUserTimeout);
            checkUserTimeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    // === Core Logic ===
    async function checkUserExistsAndUpdateButton() {
        const platform = platformSelect.value;
        const username = usernameInput.value.trim();

        if (!username) {
            updateButtonUI(false); // Reset to default if input is empty
            return;
        }

        try {
            const response = await fetch(`/api/check_user_exists?platform=${platform}&username=${encodeURIComponent(username)}`);
            if (!response.ok) return;
            const data = await response.json();
            updateButtonUI(data.exists);
        } catch (error) {
            console.error('Error checking user:', error);
        }
    }

    // === UI Update Functions ===
    function updateButtonUI(exists) {
        if (exists) {
            startButton.innerHTML = '<i class="bi bi-arrow-repeat"></i> Cập nhật';
            startButton.classList.remove('btn-primary');
            startButton.classList.add('btn-success');
        } else {
            startButton.innerHTML = '<i class="bi bi-cloud-download"></i> Cào';
            startButton.classList.remove('btn-success');
            startButton.classList.add('btn-primary');
        }
    }

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
    
    // === Main Scraper Logic ===
    function handleFormSubmit(e) {
        e.preventDefault();
        if (eventSource) {
            eventSource.close();
        }

        const platform = platformSelect.value;
        const username = usernameInput.value.trim();
        if (!username) {
            alert('Vui lòng nhập tên người dùng.');
            return;
        }

        resetUI();
        startButton.disabled = true;
        startButton.innerHTML = `<span class="spinner-border spinner-border-sm"></span> Đang xử lý...`;
        progressContainer.style.display = 'block';

        const url = `/scrape-stream?platform=${platform}&username=${encodeURIComponent(username)}`;
        eventSource = new EventSource(url);

        eventSource.onopen = () => updateStatus('Đã kết nối, đang bắt đầu quá trình...');
        eventSource.onmessage = (event) => {
            try {
                const eventData = JSON.parse(event.data);
                handleServerEvent(eventData.type, eventData.data);
            } catch (error) {
                console.error('Failed to parse event data:', event.data, error);
            }
        };
        eventSource.onerror = () => {
            handleServerEvent('error', { message: 'Mất kết nối với máy chủ. Vui lòng thử lại.' });
            eventSource.close();
        };
    }
    
    function handleServerEvent(type, data) {
        switch (type) {
            case 'status': updateStatus(data.message); break;
            case 'profile': displayProfile(data); updateProgressBar(20); break;
            case 'progress':
                progressCount.textContent = `${data.found} bài đăng`;
                const currentWidth = parseFloat(progressBar.style.width) || 20;
                if (currentWidth < 80) updateProgressBar(currentWidth + 2);
                break;
            case 'done':
                updateStatus(data.message);
                updateProgressBar(100, 'bg-success');
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
        checkUserExistsAndUpdateButton(); // Update button state after finishing
        progressBar.classList.remove('progress-bar-animated');
        
        // Trigger a custom event to notify script.js to reload the tree
        document.dispatchEvent(new CustomEvent('scrapeComplete'));
    }

    // === Event Listeners Setup ===
    form.addEventListener('submit', handleFormSubmit);

    const debouncedCheck = debounce(checkUserExistsAndUpdateButton, 400);
    usernameInput.addEventListener('input', debouncedCheck);
    platformSelect.addEventListener('change', checkUserExistsAndUpdateButton);
});