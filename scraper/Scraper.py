import os
import json
import time
import pickle
import re
import base64
from urllib.request import urlretrieve
from concurrent.futures import ThreadPoolExecutor, as_completed
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode
from tqdm import tqdm
from datetime import datetime, timezone

class BaseScraper:
    """
    Lớp cơ sở cho trình cào dữ liệu, được nâng cấp để phát ra các sự kiện (yield).
    """
    def __init__(self, headless=True, working_dir="CloudStorage"):
        self.driver = self._initialize_driver(headless=headless)
        self.working_dir = os.path.realpath(working_dir)
        os.makedirs(self.working_dir, exist_ok=True)

    def _initialize_driver(self, headless):
        options = webdriver.ChromeOptions()
        options.add_argument('--enable-unsafe-swiftshader')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        if headless:
            options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)
        return driver

    def _yield_event(self, event_type, data):
        """Helper function to format and yield event data."""
        return json.dumps({"type": event_type, "data": data})

    def _load_cookies(self, cookie_file):
        if os.path.exists(cookie_file):
            with open(cookie_file, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            return True
        return False

    def _save_cookies(self, cookie_file):
        os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
        with open(cookie_file, "wb") as f:
            pickle.dump(self.driver.get_cookies(), f)
    
    def _download_files(self, photos, download_dir, history_file):
        # This part remains mostly the same, but we could also yield progress here if needed.
        os.makedirs(download_dir, exist_ok=True)
        history = set()
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                history = set(f.read().splitlines())

        def download_file(photo):
            image_url, post_url, taken_at = photo
            filename = image_url.split("/")[-1].split('?')[0]
            if filename in history:
                return
            filename = f"{datetime.fromtimestamp(taken_at).strftime('%Y%m%d_%H%M%S')}_{filename}" if taken_at else filename
            filepath = os.path.join(download_dir, filename)
            if not os.path.exists(filepath):
                urlretrieve(image_url, filepath)
                with open(history_file, "a") as f:
                    f.write(f"{post_url}, {filename}\n")
        
        # Using tqdm for console progress, but we're also yielding events for the UI
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(download_file, photo) for photo in set(photos)]
            for _ in tqdm(as_completed(futures), total=len(futures), desc="Downloading", unit="file"):
                pass

    def _scroll_to_bottom(self):
        """Cuộn xuống cuối trang và phát ra sự kiện tiến trình."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            # Yield progress after each scroll
            all_nodes = self._get_all_nodes()
            yield self._yield_event("progress", {"found": len(all_nodes)})
            
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        self.driver.execute_script("window.scrollTo(0, 0);")

    def close(self):
        self.driver.quit()

    def _get_all_nodes(self):
        # This method needs to be implemented by each subclass
        raise NotImplementedError

class InstagramScraper(BaseScraper):
    def scrape_users(self, users):
        for user in users:
            # yield from will pass through all yielded events from scrape_user
            yield from self.scrape_user(user)

    def scrape_user(self, user):
        if not user: return
        yield self._yield_event("status", {"message": f"Đang kết nối tới Instagram cho người dùng: {user}..."})
        self.driver.get("https://www.instagram.com/")
        if not self._load_cookies("cookies/instagram.pkl"):
            yield self._yield_event("error", {"message": "Cookie Instagram không tìm thấy. Vui lòng đăng nhập thủ công và lưu lại."})
            return

        self.driver.scopes = ['https://www.instagram.com/graphql/query*']
        self.driver.get(f"https://www.instagram.com/{user}/")
        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            yield self._yield_event("error", {"message": f"Không thể tìm thấy hồ sơ cho người dùng {user}."})
            return
        yield self._yield_event("profile", profile_data)

        yield self._yield_event("status", {"message": "Đã tìm thấy hồ sơ. Bắt đầu cuộn trang để thu thập bài đăng..."})
        
        # The scroll_to_bottom method now yields progress events
        yield from self._scroll_to_bottom()

        all_nodes = self._get_all_nodes()
        photos = self._extract_info_nodes(all_nodes)
        
        user_folder = os.path.join(self.working_dir, "instagram", user)
        os.makedirs(user_folder, exist_ok=True)
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
        
        yield self._yield_event("status", {"message": f"Đã thu thập xong. Bắt đầu tải xuống {len(photos)} tệp..."})
        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
        
        yield self._yield_event("done", {"message": f"Hoàn tất! Đã tải xuống {len(photos)} tệp cho {user}."})

    def _get_all_nodes(self):
        all_nodes = []
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') in ['PolarisProfilePostsQuery', 'PolarisProfilePostsTabContentQuery_connection']:
                try:
                    data = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
                    if 'data' in data and 'xdt_api__v1__feed__user_timeline_graphql_connection' in data['data']:
                        all_nodes.extend(data['data']['xdt_api__v1__feed__user_timeline_graphql_connection']['edges'])
                except (json.JSONDecodeError, AttributeError):
                    continue
        return all_nodes

    def _get_profile_data(self):
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') == 'PolarisProfilePageContentQuery':
                try:
                    data = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
                    if 'data' in data and 'user' in data['data']:
                        _data = data['data']['user']
                        return {
                            "url": self.driver.current_url,
                            "name": _data.get('full_name', '').strip(),
                            "id": _data.get('id', ''),
                            "profile_pic_url": _data.get('profile_pic_url'),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                except (json.JSONDecodeError, AttributeError):
                    continue
        return None

    def _extract_info_nodes(self, all_nodes):
        results = []
        for node in all_nodes:
            node_data = node.get('node', {})
            if not node_data: continue
            carousel_media = node_data.get('carousel_media', [])
            if not carousel_media:
                if node_data.get('image_versions2'):
                    image_url = node_data['image_versions2']['candidates'][0]['url']
                    taken_at = node_data.get('taken_at')
                    post_url = f"https://www.instagram.com/p/{node_data.get('code', '')}/"
                    results.append((image_url, post_url, taken_at))
            else:
                for media in carousel_media:
                    if media.get('image_versions2'):
                        image_url = media['image_versions2']['candidates'][0]['url']
                        taken_at = media.get('taken_at')
                        post_url = f"https://www.instagram.com/p/{node_data.get('code', '')}/"
                        results.append((image_url, post_url, taken_at))
        return results

# Note: The FacebookScraper and ThreadsScraper classes would need similar modifications
# to become generators and yield events. For brevity, only InstagramScraper is fully shown.
class FacebookScraper(BaseScraper):
    # TODO: Implement the same generator pattern as InstagramScraper
    def scrape_users(self, users):
        yield self._yield_event("error", {"message": "Chức năng cào Facebook đang được xây dựng."})

class ThreadsScraper(BaseScraper):
    # TODO: Implement the same generator pattern as InstagramScraper
    def scrape_users(self, users):
        yield self._yield_event("error", {"message": "Chức năng cào Threads đang được xây dựng."})

