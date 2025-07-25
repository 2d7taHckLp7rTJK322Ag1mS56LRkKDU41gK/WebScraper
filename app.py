# app.py (Đã cập nhật routing)

import os
import shutil
import glob
from flask import Flask, render_template, jsonify, request, abort, redirect, url_for, flash
from PIL import Image
from functools import lru_cache
from scraper.Scraper import InstagramScraper, ThreadsScraper, FacebookScraper

app = Flask(__name__)
app.secret_key = 'a_very_secret_key_please_change_me' # IMPORTANT: Change this key for production

# --- Configuration ---
BASE_DIR = os.path.realpath("CloudStorage")
THUMBNAIL_DIR = os.path.realpath(os.path.join('static', 'thumbnails'))
THUMBNAIL_SIZE = (150, 150)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# Create necessary directories on startup
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


# --- Helper Functions ---
def allowed_file(filename):
    """Kiểm tra phần mở rộng của file có hợp lệ không."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_safe_path(path_str=""):
    """
    Chuyển đổi đường dẫn tương đối thành đường dẫn tuyệt đối và xác thực.
    Ngăn chặn tấn công Path Traversal.
    """
    if not path_str:
        return BASE_DIR
    # Nối đường dẫn và giải quyết các ký tự '..' hoặc './'
    full_path = os.path.realpath(os.path.join(BASE_DIR, path_str))
    # Đảm bảo đường dẫn cuối cùng phải nằm trong BASE_DIR
    if not full_path.startswith(BASE_DIR):
        abort(400, "Đường dẫn không hợp lệ.")
    if not os.path.exists(full_path):
        abort(404, "Đường dẫn không tồn tại.")
    return full_path

def create_thumbnail(image_full_path):
    """Tạo thumbnail cho ảnh, chỉ tạo nếu chưa tồn tại."""
    rel_path = os.path.relpath(image_full_path, BASE_DIR)
    # Tạo tên file an toàn cho thumbnail để tránh xung đột
    safe_name = rel_path.replace(os.sep, '_')
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    if not os.path.exists(thumb_path):
        try:
            with Image.open(image_full_path) as img:
                img.thumbnail(THUMBNAIL_SIZE)
                img.save(thumb_path)
        except Exception as e:
            print(f"Lỗi tạo thumbnail cho {image_full_path}: {e}")
            return None
    return f"/static/thumbnails/{safe_name}"

def remove_thumbnail(image_rel_path):
    """Xóa thumbnail tương ứng khi ảnh gốc bị di chuyển/xóa."""
    safe_name = image_rel_path.replace('/', '_').replace('\\', '_')
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    if os.path.exists(thumb_path):
        os.remove(thumb_path)

# --- Page Routes ---
@app.route('/')
def label_tool():
    """Trang chính cho công cụ gắn nhãn."""
    return render_template('label_tool.html')

@app.route('/scraper')
def scraper_page():
    """Trang hiển thị form để cào dữ liệu."""
    return render_template('scraper_form.html')

@app.route('/run_scraper', methods=['POST'])
def run_scraper():
    """Xử lý dữ liệu từ form cào dữ liệu."""
    platform = request.form.get('platform')
    username = request.form.get('username', '').strip()
    
    if not platform or not username:
        flash('Vui lòng điền đầy đủ thông tin.', 'warning')
        return redirect(url_for('scraper_page'))

    scraper = None
    try:
        # Xác định scraper dựa trên platform
        # Note: Pass the BASE_DIR to the scraper so it knows where to save files.
        if platform == 'instagram':
            scraper = InstagramScraper(headless=True, working_dir=BASE_DIR)
        elif platform == 'threads':
            scraper = ThreadsScraper(headless=True, working_dir=BASE_DIR)
        elif platform == 'facebook':
            scraper = FacebookScraper(headless=True, working_dir=BASE_DIR)
        else:
            flash('Nền tảng không được hỗ trợ.', 'danger')
            return redirect(url_for('scraper_page'))
            
        # Chạy scraper
        scraper.scrape_users([username])
        
        # Xóa cache cây thư mục để giao diện cập nhật
        api_tree.cache_clear()
        
        flash(f'Đã cào dữ liệu thành công cho "{username}". Dữ liệu mới đã có trong công cụ gắn nhãn.', 'success')
        return redirect(url_for('label_tool')) # Chuyển hướng về trang gắn nhãn

    except Exception as e:
        print(f"Scraping Error: {e}") # Ghi log lỗi ra console
        flash(f'Đã xảy ra lỗi khi cào dữ liệu: {e}', 'danger')
        return redirect(url_for('scraper_page')) # Quay lại trang scraper nếu có lỗi
    finally:
        if scraper:
            scraper.close()


# --- API Routes for Labeling Tool ---
@app.route('/api/content')
def api_content():
    """API gộp, lấy cả ảnh và thư mục con một lúc."""
    current_dir = get_safe_path(request.args.get('path', ''))
    
    # Lấy ảnh
    image_files = sorted([f for f in glob.glob(os.path.join(current_dir, "*")) if os.path.isfile(f) and allowed_file(f)], key=os.path.basename)
    images = [{'path': os.path.relpath(p, BASE_DIR).replace('\\', '/'), 'name': os.path.basename(p), 'thumbnail': create_thumbnail(p)} for p in image_files if create_thumbnail(p)]

    # Lấy thư mục con (nhãn)
    subfolders = sorted([{'name': d, 'path': os.path.relpath(os.path.join(current_dir, d), BASE_DIR).replace('\\', '/')} for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))], key=lambda x: x['name'])
    
    # Lấy breadcrumbs
    rel_path = os.path.relpath(current_dir, BASE_DIR) if current_dir != BASE_DIR else ""
    breadcrumbs = []
    if rel_path and rel_path != '.':
        parts = rel_path.split(os.sep)
        for i, part in enumerate(parts):
            breadcrumbs.append({'name': part, 'path': '/'.join(parts[:i+1])})

    return jsonify({'images': images, 'labels': subfolders, 'breadcrumbs': breadcrumbs})

@app.route('/api/tree')
@lru_cache(maxsize=1)
def api_tree():
    """API xây dựng cây thư mục, được cache để tăng tốc."""
    def build_tree(path):
        items = []
        try:
            for item in sorted(os.listdir(path)):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    rel_path = os.path.relpath(item_path, BASE_DIR).replace('\\', '/')
                    items.append({'name': item, 'path': rel_path, 'children': build_tree(item_path)})
        except Exception:
            return []
        return items
    return jsonify([{'name': 'Workspace', 'path': '', 'children': build_tree(BASE_DIR), 'isRoot': True}])

@app.route('/api/create_label', methods=['POST'])
def create_label():
    """API tạo nhãn (thư mục) mới."""
    data = request.json
    label_name = data.get('name', '').strip()
    parent_path = get_safe_path(data.get('path', ''))
    if not label_name or '/' in label_name or '\\' in label_name:
        return jsonify({'error': 'Tên nhãn không hợp lệ.'}), 400
    new_folder = os.path.join(parent_path, label_name)
    if os.path.exists(new_folder):
        return jsonify({'error': f'Nhãn "{label_name}" đã tồn tại.'}), 409
    os.makedirs(new_folder)
    api_tree.cache_clear()
    return jsonify({'message': f'Nhãn "{label_name}" đã được tạo.'})

@app.route('/api/assign_label', methods=['POST'])
def assign_label():
    """API di chuyển các file ảnh vào một nhãn (thư mục)."""
    data = request.json
    file_rel_paths = data.get('files', [])
    dest_rel_path = data.get('labelPath', '')
    dest_full_path = get_safe_path(dest_rel_path)
    if not os.path.isdir(dest_full_path):
        return jsonify({'error': 'Thư mục đích không hợp lệ.'}), 400
    moved_count = 0
    errors = []
    for rel_path in file_rel_paths:
        try:
            src_full_path = get_safe_path(rel_path)
            dest_file = os.path.join(dest_full_path, os.path.basename(src_full_path))
            if os.path.exists(dest_file):
                errors.append(f"File '{os.path.basename(rel_path)}' đã tồn tại ở thư mục đích.")
                continue
            shutil.move(src_full_path, dest_file)
            remove_thumbnail(rel_path)
            moved_count += 1
        except Exception as e:
            errors.append(f"Lỗi di chuyển {rel_path}: {e}")
    api_tree.cache_clear()
    return jsonify({'moved': moved_count, 'errors': errors})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
