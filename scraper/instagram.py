import os
import json
import time
from datetime import datetime, timezone
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode
from .base import BaseScraper
class InstagramScraper(BaseScraper):
    """
    Cào dữ liệu các bài đăng và hình ảnh trên Instagram cho (các) người dùng được chỉ định.
    """
    def __init__(self, headless=True, working_dir="CloudStorage"):
        super().__init__(headless, working_dir)
        self.driver.get("https://www.instagram.com/")
        if not self._load_cookies("cookies/instagram.pkl"):
            print("Vui lòng đăng nhập vào Instagram và lưu cookie.")
            input("Nhấn Enter sau khi đăng nhập...")
            self._save_cookies("cookies/instagram.pkl")

    def scrape_users(self, users):
        """Cào dữ liệu nhiều người dùng Instagram."""
        for user in users:
            # yield from will pass through all yielded events from scrape_user
            yield from self.scrape_user(user)

    def scrape_user(self, user):
        """Cào dữ liệu một người dùng Instagram duy nhất."""
        if not user: return
        yield self._yield_event("status", {"message": f"Đang kết nối tới Instagram cho người dùng: {user}..."})
        self.driver.get("https://www.instagram.com/")
        if not self._load_cookies("cookies/instagram.pkl"):
            yield self._yield_event("error", {"message": "Cookie Instagram không tìm thấy. Vui lòng đăng nhập thủ công và lưu lại."})
            return

        print(f"Đang cào dữ liệu người dùng Instagram: {user}")
        self.driver.scopes = ['https://www.instagram.com/graphql/query*']
        self._clean_driver_requests()
        self.driver.get(f"https://www.instagram.com/{user}/")
        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            print(f"Không thể truy xuất dữ liệu hồ sơ cho người dùng {user}")
            yield self._yield_event("error", {"message": f"Không thể tìm thấy hồ sơ cho người dùng {user}."})
            return
        print(f"THÔNG TIN HỒ SƠ:")
        print(f"\tTên người dùng: {profile_data['name']}")
        print(f"\tID người dùng: {profile_data['id']}")
        print(f"\tURL hồ sơ: {profile_data['url']}")
        print(f"\tThời gian: {profile_data['timestamp']}")

        yield self._yield_event("profile", profile_data)
        yield self._yield_event("status", {"message": "Đã tìm thấy hồ sơ. Bắt đầu cuộn trang để thu thập bài đăng..."})
        # The scroll_to_bottom method now yields progress events
        yield from self._scroll_to_bottom()

        user_folder = os.path.join(self.working_dir, "instagram", user)
        os.makedirs(user_folder, exist_ok=True)
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        photos = self._extract_info_nodes(all_nodes)

        yield self._yield_event("status", {"message": f"Đã thu thập xong. Bắt đầu tải xuống {len(photos)} tệp..."})
        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
        yield self._yield_event("done", {"message": f"Hoàn tất! Đã tải xuống {len(photos)} tệp cho {user}."})
                
        print(f"\tĐã cào dữ liệu thành công {len(photos)} hình ảnh cho người dùng {user}")

    def _get_all_nodes(self):
        """Truy xuất tất cả các nút chứa thông tin hình ảnh."""
        all_nodes = []
        for request in self.driver.requests:
            # if request.response and request.headers.get('x-fb-friendly-name') == 'ProfileCometAppCollectionPhotosRendererPaginationQuery':
            if request.response and request.headers.get('x-fb-friendly-name') in ['PolarisProfilePostsQuery', 'PolarisProfilePostsTabContentQuery_connection']:
                response = request.response
                data = json.loads(decode(response.body, response.headers.get('Content-Encoding', 'identity')))
                all_nodes.extend(data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['edges'])
        return all_nodes
    
    def _get_profile_data(self):
        """Truy xuất dữ liệu hồ sơ người dùng."""
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') == 'PolarisProfilePageContentQuery':
                data = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
                if 'data' in data and 'user' in data['data']:
                    _data = data['data']['user']
                    break
        return {
            "url": self.driver.current_url,
            "name": _data.get('full_name', '').strip(),
            "id": _data.get('id', ''),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def _extract_info_nodes(self, all_nodes):
        """Trích xuất các nút hình ảnh từ dữ liệu đã thu thập."""
        # photos (list): Danh sách các tuple chứa (image_url, post_url, taken_at).
        results = []
        for node in all_nodes:
            carousel_media = node['node'].get('carousel_media', [])
            if not carousel_media:
                image_url = node['node']['image_versions2']['candidates'][0]['url']
                taken_at = node['node'].get('taken_at')
                post_url = f"https://www.instagram.com/p/{node['node']['code']}/"
                results.append((image_url, post_url, taken_at))
            else:
                for media in carousel_media:
                    image_url = media['image_versions2']['candidates'][0]['url']
                    taken_at = media.get('taken_at')
                    post_url = f"https://www.instagram.com/p/{node['node']['code']}/"
                    results.append((image_url, post_url, taken_at))
        return results