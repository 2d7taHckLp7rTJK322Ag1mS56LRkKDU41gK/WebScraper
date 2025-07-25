import os
import json
import time
import re
import base64
import argparse
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode
from datetime import datetime
from .base import BaseScraper

class FacebookScraper(BaseScraper):
    """
    Cào dữ liệu ảnh Facebook cho (các) người dùng được chỉ định.
    """
    def __init__(self, headless=True, working_dir="CloudStorage"):
        super().__init__(headless, working_dir)
        self.driver.get("https://www.facebook.com/")

        if not self._load_cookies("cookies/facebook.pkl"):
            print("Vui lòng đăng nhập vào Facebook và lưu cookie.")
            input("Nhấn Enter sau khi đăng nhập...")
            self._save_cookies("cookies/facebook.pkl")

    def scrape_users(self, users):
        """Cào dữ liệu nhiều người dùng Facebook."""
        for user in users:
            yield from self.scrape_user(user)

    def scrape_user(self, user):
        if not user: return
        yield self._yield_event("status", {"message": f"Đang kết nối tới Facebook cho người dùng: {user}..."})
        self.driver.get(f"https://www.facebook.com/")
        if not self._load_cookies("cookies/facebook.pkl"):
            yield self._yield_event("error", {"message": "Cookie Facebook không tìm thấy. Vui lòng đăng nhập thủ công và lưu lại."})
            return

        print(f"Đang cào dữ liệu người dùng Facebook: {user}")
        self.driver.scopes = ['https://www.facebook.com/api/graphql/*']
        self._clean_driver_requests()

        self.driver.get(f"https://www.facebook.com/{user}/photos_by")
        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            yield self._yield_event("error", {"message": f"Không thể tìm thấy hồ sơ cho người dùng {user}."})
            print(f"Không thể truy xuất dữ liệu hồ sơ cho người dùng {user}")
            return
        print(f"THÔNG TIN HỒ SƠ:")
        print(f"\tTên người dùng: {profile_data['name']}")
        print(f"\tID người dùng: {profile_data['id']}")
        print(f"\tURL hồ sơ: {profile_data['url']}")
        print(f"\tThời gian: {profile_data['timestamp']}")
        yield self._yield_event("profile", profile_data)

        yield self._yield_event("status", {"message": "Đã tìm thấy hồ sơ. Bắt đầu cuộn trang để thu thập bài đăng..."})
        

        yield from self._scroll_to_bottom()

        user_folder = os.path.join(self.working_dir, "facebook", user)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        
        photos = self._extract_info_nodes(all_nodes)
        photos += self._extract_info_nodes_in_html(user)

        yield self._yield_event("status", {"message": f"Đã thu thập xong. Bắt đầu tải xuống {len(photos)} tệp..."})
        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
        yield self._yield_event("done", {"message": f"Hoàn tất! Đã tải xuống {len(photos)} tệp cho {user}."})

    def _get_profile_data(self):
        """Truy xuất dữ liệu hồ sơ người dùng."""
        try:
            while not self._waiting_for_page_load():
                time.sleep(1)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, 0);")
            try:
                h1_text = self.driver.find_element(By.TAG_NAME, 'h1').text
            except:
                title = self.driver.title
                h1_text = title.split(" | ")[0] if " | " in title else title
                h1_text = h1_text.split(")")[1].strip() if ")" in h1_text else h1_text.strip()

            all_nodes = self._get_all_nodes()
            user_id = base64.b64decode(all_nodes[0]['node']['id']).decode('utf-8').split(':')[1]
            return {
                "url": self.driver.current_url,
                "name": re.sub(r"\s*\(.*?\)", "", h1_text).strip(),
                "id": user_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except:
            # return None
            time.sleep(5)
            return self._get_profile_data()
        
    def get_photo_fbid_links(self):
        """
        Lấy tất cả các liên kết đến ảnh có dạng photo.php?fbid=*
        """
        # Lấy tất cả thẻ a
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)  # Đợi trang tải xong
        a_tags = self.driver.find_elements(By.TAG_NAME, "a")

        fbid_links = []
        for a in a_tags:
            href = a.get_attribute("href")
            if href and re.match(r"https://www\.facebook\.com/photo\.php\?fbid=\d+", href):
                fbid_links.append(href.split('&')[0])  # Chỉ lấy phần trước dấu '?'

        return fbid_links

    def _extract_info_nodes(self, all_nodes):
        """Trích xuất các nút hình ảnh từ dữ liệu đã thu thập."""
        # photos (list): Danh sách các tuple chứa (image_url, post_url, taken_at).
        results = []
        for node in all_nodes:
            image_url = node['node']['node']['viewer_image']['uri']
            post_url = node['node']['url'].split('&')[0] 
            taken_at = None
            results.append((image_url, post_url, taken_at))
        return results
    
    def _extract_info_nodes_in_html(self, user):
        self.driver.get(f"https://www.facebook.com/{user}/photos_by")
        time.sleep(5)
        results = []
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        self.driver.execute_script("window.scrollTo(0, 0);")
        while not self._waiting_for_page_load():
            time.sleep(2)

        a_tags = self.driver.find_elements(By.TAG_NAME, "a")
        fbid_links = []
        for a in a_tags:
            href = a.get_attribute("href")
            if href and re.match(r"https://www\.facebook\.com/photo\.php\?fbid=\d+", href):
                fbid_links.append(href.split('&')[0])  # Chỉ lấy phần trước dấu '?'
        for fbid_link in fbid_links:
            try:
                self.driver.get(fbid_link)
                time.sleep(2)
                image_uri = self.driver.find_element(By.CSS_SELECTOR, 'img[data-visualcompletion="media-vc-image"]').get_attribute("src")
                results.append((image_uri, fbid_link, None))
            except Exception as e:
                print(f"Lỗi khi trích xuất hình ảnh từ liên kết {fbid_link}: {e}")
        return results


    def _get_all_nodes(self):
        """Truy xuất tất cả các nút chứa thông tin hình ảnh."""
        all_nodes = []
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') == 'ProfileCometAppCollectionPhotosRendererPaginationQuery':
                response = request.response
                data = json.loads(decode(response.body, response.headers.get('Content-Encoding', 'identity')))
                all_nodes.extend(data['data']['node']['pageItems']['edges'])
        return all_nodes

