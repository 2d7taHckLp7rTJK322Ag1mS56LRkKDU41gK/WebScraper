# app.py (Tích hợp hoàn chỉnh)

import os
import shutil
import glob
from flask import Flask, Response, render_template, jsonify, request, abort
import json
from functools import lru_cache
from scraper import InstagramScraper, ThreadsScraper, FacebookScraper
from PIL import Image

app = Flask(__name__)
app.secret_key = 'a_very_secret_key_please_change_me'

# --- Configuration ---
BASE_DIR = os.path.realpath("CloudStorage")
THUMBNAIL_DIR = os.path.realpath(os.path.join('static', 'thumbnails'))
THUMBNAIL_SIZE = (150, 150)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# --- Helper Functions ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_safe_path(path_str=""):
    if not path_str:
        return BASE_DIR
    full_path = os.path.realpath(os.path.join(BASE_DIR, path_str))
    if not full_path.startswith(BASE_DIR):
        abort(400, "Đường dẫn không hợp lệ.")
    if not os.path.exists(full_path):
        abort(404, "Đường dẫn không tồn tại.")
    return full_path

def create_thumbnail(image_full_path):
    rel_path = os.path.relpath(image_full_path, BASE_DIR)
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
    safe_name = image_rel_path.replace('/', '_').replace('\\', '_')
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    if os.path.exists(thumb_path):
        os.remove(thumb_path)

# --- Main Route ---
@app.route('/')
def index():
    return render_template('index.html')

# --- Real-time Scraper Stream Route ---
@app.route('/scrape-stream')
def scrape_stream():
    platform = request.args.get('platform')
    username = request.args.get('username', '').strip()
    if not platform or not username:
        return Response("Missing parameters", status=400)

    def generate_events():
        scraper = None
        try:
            scraper_map = {
                'instagram': InstagramScraper,
                'threads': ThreadsScraper,
                'facebook': FacebookScraper
            }
            if platform in scraper_map:
                scraper = scraper_map[platform](headless=True, working_dir=BASE_DIR)
            else:
                error_event = json.dumps({"type": "error", "data": {"message": "Nền tảng không hợp lệ."}})
                yield f"data: {error_event}\n\n"
                return

            for event_data in scraper.scrape_users([username]):
                yield f"data: {event_data}\n\n"
            
            api_tree.cache_clear()
        except Exception as e:
            error_event = json.dumps({"type": "error", "data": {"message": str(e)}})
            yield f"data: {error_event}\n\n"
        finally:
            if scraper:
                scraper.close()
    return Response(generate_events(), mimetype='text/event-stream')

# --- API Routes ---
@app.route('/api/tree')
@lru_cache(maxsize=1)
def api_tree():
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
    return jsonify([{'name': 'CloudStorage', 'path': '', 'children': build_tree(BASE_DIR), 'isRoot': True}])

@app.route('/api/content')
def api_content():
    current_dir = get_safe_path(request.args.get('path', ''))
    image_files = sorted([f for f in glob.glob(os.path.join(current_dir, "*")) if os.path.isfile(f) and allowed_file(f)], key=os.path.basename)
    images = [{'path': os.path.relpath(p, BASE_DIR).replace('\\', '/'), 'name': os.path.basename(p), 'thumbnail': create_thumbnail(p)} for p in image_files if create_thumbnail(p)]
    subfolders = sorted([{'name': d, 'path': os.path.relpath(os.path.join(current_dir, d), BASE_DIR).replace('\\', '/')} for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))], key=lambda x: x['name'])
    
    rel_path = os.path.relpath(current_dir, BASE_DIR) if current_dir != BASE_DIR else ""
    breadcrumbs = []
    if rel_path and rel_path != '.':
        parts = rel_path.split(os.sep)
        for i, part in enumerate(parts):
            breadcrumbs.append({'name': part, 'path': '/'.join(parts[:i+1])})

    return jsonify({'images': images, 'labels': subfolders, 'breadcrumbs': breadcrumbs})

@app.route('/api/create_label', methods=['POST'])
def create_label():
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

@app.route('/api/check_user_exists')
def check_user_exists():
    """Kiểm tra xem thư mục của người dùng đã tồn tại hay chưa."""
    platform = request.args.get('platform')
    username = request.args.get('username', '').strip()
    if not platform or not username:
        return jsonify({'exists': False})
    
    user_folder = os.path.join(BASE_DIR, platform, username)
    return jsonify({'exists': os.path.exists(user_folder)})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=False)