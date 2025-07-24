// static/script.js (Đã cập nhật để chọn nhiều file và tối ưu)

// Why: Gom tất cả các biến trạng thái vào một object để dễ quản lý.
const appState = {
    currentPath: '',
    selectedImages: new Set(),
    lastSelectedPath: null, // Why: Lưu lại ảnh cuối cùng được click để dùng cho Shift-select.
    isMarqueeActive: false, // Why: Cờ trạng thái cho biết người dùng có đang kéo chuột chọn vùng hay không.
    marqueeStartX: 0,
    marqueeStartY: 0,
};

// Why: DOM elements được query một lần và lưu lại, tránh query lặp lại.
const DOMElements = {
    treeContainer: document.getElementById('folderTree'),
    gridWrapper: document.getElementById('imageGridWrapper'), // Why: Dùng wrapper để bắt sự kiện mousedown cho marquee
    gridContainer: document.getElementById('imageGrid'),
    labelButtonsContainer: document.getElementById('labelButtons'),
    breadcrumbContainer: document.getElementById('breadcrumbContainer'),
    statusMessage: document.getElementById('statusMessage'),
    newLabelInput: document.getElementById('newLabelInput'),
    createLabelBtn: document.getElementById('createLabelBtn'),
    reloadTreeBtn: document.getElementById('reloadTreeBtn'),
    selectionOverlay: document.getElementById('selectionOverlay'),
};

// --- API Client ---
// Why: Một hàm fetch tập trung giúp quản lý lỗi và loading dễ dàng.
async function api(endpoint, options = {}) {
    try {
        const response = await fetch(endpoint, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
        }
        return response.json();
    } catch (error) {
        showStatus(error.message, 'danger');
        throw error;
    }
}

// --- Render Functions ---
// Why: Tách riêng logic render ra các hàm nhỏ, dễ đọc và bảo trì.
function renderTree(nodes, parentElement) {
    parentElement.innerHTML = '';
    nodes.forEach(node => {
        const li = document.createElement('li');
        const isRoot = node.isRoot;
        li.innerHTML = `
            <div class="node-item ${isRoot ? 'fw-bold' : ''}" data-path="${node.path}">
                <i class="bi ${node.children?.length ? 'bi-folder' : 'bi-folder-fill'} text-warning"></i>
                <span>${node.name}</span>
            </div>
        `;
        const childrenUl = document.createElement('ul');
        if (node.children && node.children.length > 0) {
            renderTree(node.children, childrenUl);
            li.appendChild(childrenUl);
        }
        parentElement.appendChild(li);
    });
}

function renderContent({ images, labels, breadcrumbs }) {
    // Render images
    DOMElements.gridContainer.innerHTML = images.length
        ? images.map(img => `
            <div class="image-item" data-path="${img.path}">
                <img src="${img.thumbnail}" alt="${img.name}" loading="lazy">
                <div class="filename" title="${img.name}">${img.name}</div>
            </div>`).join('')
        : '<div class="text-center text-muted p-5">Thư mục trống</div>';

    // Render labels
    DOMElements.labelButtonsContainer.innerHTML = labels.length
        ? labels.map(label => `
            <button class="btn btn-outline-primary btn-sm" data-path="${label.path}" title="Gán vào: ${label.name}">
                <i class="bi bi-tag"></i> ${label.name}
            </button>`).join('')
        : '<span class="text-muted small">Chưa có nhãn con</span>';

    // Render breadcrumbs
    DOMElements.breadcrumbContainer.innerHTML = `
        <li class="breadcrumb-item"><a href="#" data-path="">
            <i class="bi bi-house-door"></i> Home</a>
        </li>
        ${breadcrumbs.map(b => `
            <li class="breadcrumb-item"><a href="#" data-path="${b.path}">${b.name}</a></li>
        `).join('')}`;
}


// --- Main Logic & UI Feedback ---
function showStatus(message, type = 'success', duration = 3000) {
    const { statusMessage } = DOMElements;
    statusMessage.className = `alert alert-${type}`;
    statusMessage.textContent = message;
    statusMessage.classList.remove('d-none');
    setTimeout(() => statusMessage.classList.add('d-none'), duration);
}

async function loadTree() {
    try {
        const treeData = await api('/api/tree');
        renderTree(treeData, DOMElements.treeContainer);
    } catch (e) { /* Lỗi đã được xử lý trong `api` */ }
}

async function navigateToPath(path) {
    appState.currentPath = path;
    appState.selectedImages.clear();
    appState.lastSelectedPath = null;

    // Update URL for better navigation history
    const url = new URL(window.location);
    url.searchParams.set('path', path);
    window.history.pushState({ path }, '', url);

    // Highlight active tree node
    document.querySelectorAll('#folderTree .node-item.active').forEach(el => el.classList.remove('active'));
    document.querySelector(`#folderTree .node-item[data-path="${path}"]`)?.classList.add('active');

    try {
        const content = await api(`/api/content?path=${encodeURIComponent(path)}`);
        renderContent(content);
    } catch (e) { /* Lỗi đã được xử lý trong `api` */ }
}

async function createLabel() {
    const name = DOMElements.newLabelInput.value.trim();
    if (!name) return showStatus('Vui lòng nhập tên nhãn', 'warning');

    try {
        const data = await api('/api/create_label', {
            method: 'POST',
            body: JSON.stringify({ name, path: appState.currentPath }),
        });
        DOMElements.newLabelInput.value = '';
        showStatus(data.message);
        // Refresh tree and content
        await loadTree();
        await navigateToPath(appState.currentPath);
    } catch (e) { /* Lỗi đã được xử lý trong `api` */ }
}

async function assignToLabel(labelPath) {
    if (appState.selectedImages.size === 0) {
        return showStatus('Chưa chọn ảnh nào.', 'warning');
    }

    try {
        const data = await api('/api/assign_label', {
            method: 'POST',
            body: JSON.stringify({
                files: Array.from(appState.selectedImages),
                labelPath,
            }),
        });
        let message = `Đã di chuyển ${data.moved} ảnh.`;
        if (data.errors.length > 0) {
            message += `\nLỗi: ${data.errors.join(', ')}`;
        }
        showStatus(message, data.errors.length > 0 ? 'warning' : 'success');
        // Refresh tree and content after moving files
        await loadTree();
        await navigateToPath(appState.currentPath);
    } catch (e) { /* Lỗi đã được xử lý trong `api` */ }
}


// --- SELECTION LOGIC ---
function updateSelectionUI() {
    DOMElements.gridContainer.querySelectorAll('.image-item').forEach(item => {
        item.classList.toggle('selected', appState.selectedImages.has(item.dataset.path));
    });
}

function handleImageClick(e) {
    const item = e.target.closest('.image-item');
    if (!item) return;

    const path = item.dataset.path;
    const allItems = Array.from(DOMElements.gridContainer.querySelectorAll('.image-item'));

    if (e.shiftKey && appState.lastSelectedPath) {
        const lastIdx = allItems.findIndex(el => el.dataset.path === appState.lastSelectedPath);
        const currentIdx = allItems.indexOf(item);
        
        if (!e.ctrlKey) {
            appState.selectedImages.clear();
        }

        const [start, end] = [Math.min(lastIdx, currentIdx), Math.max(lastIdx, currentIdx)];
        for (let i = start; i <= end; i++) {
            appState.selectedImages.add(allItems[i].dataset.path);
        }
    } else if (e.ctrlKey) {
        appState.selectedImages.has(path)
            ? appState.selectedImages.delete(path)
            : appState.selectedImages.add(path);
        appState.lastSelectedPath = path;
    } else {
        appState.selectedImages.clear();
        appState.selectedImages.add(path);
        appState.lastSelectedPath = path;
    }
    updateSelectionUI();
}

function handleMarqueeStart(e) {
    if (e.target.closest('.image-item')) return;
    e.preventDefault();

    appState.isMarqueeActive = true;
    appState.marqueeStartX = e.clientX;
    appState.marqueeStartY = e.clientY;

    const rect = DOMElements.gridWrapper.getBoundingClientRect();
    DOMElements.selectionOverlay.style.left = `${e.clientX - rect.left}px`;
    DOMElements.selectionOverlay.style.top = `${e.clientY - rect.top}px`;
    DOMElements.selectionOverlay.style.width = '0px';
    DOMElements.selectionOverlay.style.height = '0px';
    DOMElements.selectionOverlay.style.display = 'block';

    if (!e.ctrlKey) {
        appState.selectedImages.clear();
        updateSelectionUI();
    }
}

function handleMarqueeMove(e) {
    if (!appState.isMarqueeActive) return;
    e.preventDefault();

    const rect = DOMElements.gridWrapper.getBoundingClientRect();
    const width = e.clientX - appState.marqueeStartX;
    const height = e.clientY - appState.marqueeStartY;

    DOMElements.selectionOverlay.style.width = `${Math.abs(width)}px`;
    DOMElements.selectionOverlay.style.height = `${Math.abs(height)}px`;
    DOMElements.selectionOverlay.style.left = `${(width > 0 ? appState.marqueeStartX : e.clientX) - rect.left}px`;
    DOMElements.selectionOverlay.style.top = `${(height > 0 ? appState.marqueeStartY : e.clientY) - rect.top}px`;
    
    updateSelectionFromMarquee();
}

function handleMarqueeEnd(e) {
    if (!appState.isMarqueeActive) return;
    e.preventDefault();
    appState.isMarqueeActive = false;
    DOMElements.selectionOverlay.style.display = 'none';
}

function updateSelectionFromMarquee() {
    const overlayRect = DOMElements.selectionOverlay.getBoundingClientRect();
    DOMElements.gridContainer.querySelectorAll('.image-item').forEach(item => {
        const itemRect = item.getBoundingClientRect();
        const isIntersecting = !(overlayRect.right < itemRect.left || 
                                 overlayRect.left > itemRect.right || 
                                 overlayRect.bottom < itemRect.top || 
                                 overlayRect.top > itemRect.bottom);
        
        if (isIntersecting) {
            if (!appState.selectedImages.has(item.dataset.path)) {
                appState.selectedImages.add(item.dataset.path);
                item.classList.add('selected');
            }
        }
    });
}


// --- Event Listeners Setup ---
function setupEventListeners() {
    DOMElements.treeContainer.addEventListener('click', e => {
        const nodeItem = e.target.closest('.node-item');
        if (nodeItem) navigateToPath(nodeItem.dataset.path);
    });

    DOMElements.breadcrumbContainer.addEventListener('click', e => {
        e.preventDefault();
        const link = e.target.closest('a[data-path]');
        if (link) navigateToPath(link.dataset.path);
    });
    
    DOMElements.labelButtonsContainer.addEventListener('click', e => {
        const button = e.target.closest('button[data-path]');
        if(button) assignToLabel(button.dataset.path);
    });

    DOMElements.createLabelBtn.addEventListener('click', createLabel);
    DOMElements.newLabelInput.addEventListener('keyup', e => {
        if (e.key === 'Enter') createLabel();
    });

    DOMElements.reloadTreeBtn.addEventListener('click', loadTree);

    // Selection Event Listeners
    DOMElements.gridContainer.addEventListener('click', handleImageClick);
    DOMElements.gridWrapper.addEventListener('mousedown', handleMarqueeStart);
    document.addEventListener('mousemove', handleMarqueeMove);
    document.addEventListener('mouseup', handleMarqueeEnd);
}

// --- Initialization ---
function init() {
    setupEventListeners();
    const initialPath = new URLSearchParams(window.location.search).get('path') || '';
    
    // Load initial data
    loadTree().then(() => {
        navigateToPath(initialPath);
    });
    
    // Handle browser back/forward buttons
    window.addEventListener('popstate', e => {
        const path = e.state?.path || '';
        navigateToPath(path);
    });
}

document.addEventListener('DOMContentLoaded', init);