# app.py (Đã tối ưu)

import os
import shutil
from flask import Flask, render_template, jsonify, request, abort
from PIL import Image
import glob
from functools import lru_cache

app = Flask(__name__)

# --- Cấu hình ---
BASE_DIR = os.path.realpath("CloudStorage")
THUMBNAIL_DIR = os.path.realpath(os.path.join('static', 'thumbnails'))
THUMBNAIL_SIZE = (150, 150)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}

# Why: Tạo các thư mục cần thiết ngay khi khởi động
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)


# --- Helpers ---
def allowed_file(filename):
    """Kiểm tra phần mở rộng của file có hợp lệ không."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_safe_path(path_str=""):
    """
    Hàm trọng yếu để đảm bảo an toàn.
    Chuyển đổi đường dẫn tương đối thành đường dẫn tuyệt đối và xác thực.
    Why: Ngăn chặn tuyệt đối tấn công Path Traversal.
    """
    if not path_str:
        return BASE_DIR

    # Nối đường dẫn và giải quyết các ký tự '..' hoặc './'
    full_path = os.path.realpath(os.path.join(BASE_DIR, path_str))

    # Đảm bảo đường dẫn cuối cùng phải nằm trong BASE_DIR
    if not full_path.startswith(BASE_DIR):
        abort(400, "Đường dẫn không hợp lệ.") # Trả về lỗi thay vì mặc định

    if not os.path.exists(full_path):
        abort(404, "Đường dẫn không tồn tại.") # Rõ ràng hơn khi không tìm thấy

    return full_path

def create_thumbnail(image_full_path):
    """
    Tạo thumbnail cho ảnh. Tối ưu để chỉ tạo nếu chưa tồn tại.
    Why: Tăng hiệu năng, tránh xử lý lặp lại.
    """
    rel_path = os.path.relpath(image_full_path, BASE_DIR)
    # Why: Tạo tên file an toàn cho thumbnail để tránh xung đột
    safe_name = rel_path.replace(os.sep, '_')
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    
    if not os.path.exists(thumb_path):
        try:
            with Image.open(image_full_path) as img:
                img.thumbnail(THUMBNAIL_SIZE)
                img.save(thumb_path)
        except Exception as e:
            print(f"Lỗi tạo thumbnail cho {image_full_path}: {e}")
            return None # Trả về None nếu có lỗi
            
    return f"/static/thumbnails/{safe_name}"

def remove_thumbnail(image_rel_path):
    """
    Xóa thumbnail tương ứng khi ảnh gốc bị di chuyển/xóa.
    Why: Dọn dẹp file rác, giữ hệ thống sạch sẽ.
    """
    safe_name = image_rel_path.replace('/', '_').replace('\\', '_')
    thumb_path = os.path.join(THUMBNAIL_DIR, safe_name)
    if os.path.exists(thumb_path):
        os.remove(thumb_path)

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/content')
def api_content():
    """
    API gộp, lấy cả ảnh và thư mục con một lúc.
    Why: Giảm số lượng request từ client, tăng tốc độ tải trang.
    """
    current_dir = get_safe_path(request.args.get('path', ''))
    
    # Lấy ảnh
    image_files = sorted(
        [f for f in glob.glob(os.path.join(current_dir, "*")) if os.path.isfile(f) and allowed_file(f)],
        key=os.path.basename
    )
    
    images = [{
        'path': os.path.relpath(p, BASE_DIR).replace('\\', '/'),
        'name': os.path.basename(p),
        'thumbnail': create_thumbnail(p)
    } for p in image_files if create_thumbnail(p)]

    # Lấy thư mục con (nhãn)
    subfolders = sorted(
        [{
            'name': d,
            'path': os.path.relpath(os.path.join(current_dir, d), BASE_DIR).replace('\\', '/')
        } for d in os.listdir(current_dir) if os.path.isdir(os.path.join(current_dir, d))],
        key=lambda x: x['name']
    )
    
    # Lấy breadcrumbs
    rel_path = os.path.relpath(current_dir, BASE_DIR) if current_dir != BASE_DIR else ""
    breadcrumbs = []
    if rel_path and rel_path != '.':
        parts = rel_path.split(os.sep)
        for i, part in enumerate(parts):
            breadcrumbs.append({
                'name': part,
                'path': '/'.join(parts[:i+1])
            })

    return jsonify({
        'images': images,
        'labels': subfolders,
        'breadcrumbs': breadcrumbs
    })

@app.route('/api/tree')
@lru_cache(maxsize=1) # Why: Cache kết quả của hàm này. Chỉ chạy lại khi server restart.
def api_tree():
    """API xây dựng cây thư mục, được cache để tăng tốc."""
    def build_tree(path):
        items = []
        try:
            for item in sorted(os.listdir(path)):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    rel_path = os.path.relpath(item_path, BASE_DIR).replace('\\', '/')
                    items.append({
                        'name': item,
                        'path': rel_path,
                        'children': build_tree(item_path)
                    })
        except Exception:
            return []
        return items

    return jsonify([{
        'name': 'Workspace',
        'path': '',
        'children': build_tree(BASE_DIR),
        'isRoot': True # Why: Thêm cờ để client dễ dàng xác định node gốc
    }])


@app.route('/api/create_label', methods=['POST'])
def create_label():
    data = request.json
    label_name = data.get('name', '').strip()
    parent_path = get_safe_path(data.get('path', ''))

    if not label_name or '/' in label_name or '\\' in label_name:
        return jsonify({'error': 'Tên nhãn không hợp lệ.'}), 400

    new_folder = os.path.join(parent_path, label_name)
    if os.path.exists(new_folder):
        return jsonify({'error': f'Nhãn "{label_name}" đã tồn tại.'}), 409 # 409 Conflict

    os.makedirs(new_folder)
    api_tree.cache_clear() # Why: Xóa cache cây thư mục để lần gọi sau sẽ cập nhật
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
            
            # Why: Kiểm tra nếu file đích đã tồn tại để tránh ghi đè
            if os.path.exists(dest_file):
                errors.append(f"File '{os.path.basename(rel_path)}' đã tồn tại ở thư mục đích.")
                continue

            shutil.move(src_full_path, dest_file)
            remove_thumbnail(rel_path) # Why: Xóa thumbnail cũ sau khi di chuyển thành công
            moved_count += 1
        except Exception as e:
            errors.append(f"Lỗi di chuyển {rel_path}: {e}")

    return jsonify({'moved': moved_count, 'errors': errors})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)