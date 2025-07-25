import os
import json
import time
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode
from datetime import datetime, timezone
from .base import BaseScraper

class ThreadsScraper(BaseScraper):
    """
    Cào dữ liệu các bài đăng và hình ảnh trên Threads cho (các) người dùng được chỉ định.
    """
    def __init__(self, headless=True, working_dir="CloudStorage"):
        super().__init__(headless, working_dir)
        self.driver.get("https://www.threads.net/")
        if not self._load_cookies("cookies/threads.pkl"):
            print("Vui lòng đăng nhập vào Threads và lưu cookie.")
            input("Nhấn Enter sau khi đăng nhập...")
            self._save_cookies("cookies/threads.pkl")

    def scrape_users(self, users):
        """Cào dữ liệu nhiều người dùng Threads."""
        for user in users:
            yield from self.scrape_user(user)

    def scrape_user(self, user):
        """Cào dữ liệu một người dùng Threads duy nhất."""
        if not user: return
        yield self._yield_event("status", {"message": f"Đang kết nối tới Threads cho người dùng: {user}..."})
        self.driver.get("https://www.threads.net/")
        if not self._load_cookies("cookies/threads.pkl"):
            yield self._yield_event("error", {"message": "Cookie Threads không tìm thấy. Vui lòng đăng nhập thủ công và lưu lại."})
            return

        print(f"Đang cào dữ liệu người dùng Threads: {user}")
        # self.driver.scopes = ['https://www.facebook.com/api/graphql/*']
        self._clean_driver_requests()

        self.driver.get(f"https://www.threads.net/@{user}")

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

        user_folder = os.path.join(self.working_dir, "threads", user)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        print(f"\tĐã thu thập {len(all_nodes)} bài đăng từ người dùng {user}")
        photos = self._extract_info_nodes(all_nodes)
        photos += self._extract_info_nodes_in_html(user)

        
        print(f"\tĐã thu thập {len(photos)} hình ảnh từ người dùng {user}")
        yield self._yield_event("status", {"message": f"Đã thu thập xong. Bắt đầu tải xuống {len(photos)} tệp..."})
        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
        yield self._yield_event("done", {"message": f"Hoàn tất! Đã tải xuống {len(photos)} tệp cho {user}."})
        print(f"\tĐã cào dữ liệu thành công {len(photos)} hình ảnh cho người dùng {user}")

    def _get_profile_data(self):
        """Truy xuất dữ liệu hồ sơ người dùng."""
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') in ['BarcelonaProfileThreadsTabRefetchableDirectQuery']:
                data = json.loads(decode(request.response.body, request.response.headers.get('Content-Encoding', 'identity')))
                break
        return {
            "url": self.driver.current_url,
            "name": data['data']['mediaData']['edges'][0]['node']['thread_items'][0]['post']['user'].get('full_name', '').strip(),
            "id": data['data']['mediaData']['edges'][0]['node']['thread_items'][0]['post']['user'].get('id', ''),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    def _get_all_nodes(self):
        """Truy xuất tất cả các nút chứa thông tin hình ảnh."""
        all_nodes = []
        for request in self.driver.requests:
            if request.response and request.headers.get('x-fb-friendly-name') in ['BarcelonaProfileThreadsTabRefetchableDirectQuery']:
                response = request.response
                data = json.loads(decode(response.body, response.headers.get('Content-Encoding', 'identity')))
                all_nodes.extend(data['data']['mediaData']['edges'])
        return all_nodes
    
    def _extract_info_nodes_in_html(self, user):
        """Trích xuất các nút hình ảnh từ dữ liệu đã thu thập."""
        self.driver.get(f"https://www.threads.net/@{user}")
        time.sleep(5)
        try:
            div_element = self.driver.find_element(
                By.XPATH,
                '//div[@role="dialog" and @data-pressable-container="true" and @data-interactive-id="" and contains(@style, "opacity: 1")]'
            )

            links = div_element.find_elements(By.XPATH, f"//a[starts-with(@href, '/@{user}/post/')]")

            results = []
        except Exception as e:
            return []

        def iso_to_timestamp(iso_str: str) -> int:
            """
            Chuyển chuỗi ISO 8601 (ví dụ: '2025-01-07T11:15:08.000Z') sang Unix timestamp (int).
            """

            dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%S.%fZ")
            dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        
        # print(f"Đang trích xuất dữ liệu từ {len(links)} liên kết...")
        
        posts = []
        for link in links:
            try:
                t0 = link.find_element(By.TAG_NAME, "time").get_attribute("datetime") # 2025-01-07T11:15:08.000Z
                taken_at = iso_to_timestamp(t0)  # Chuyển đổi chuỗi ISO 8601 sang Unix timestamp
                post_url = link.get_attribute("href")
                posts.append((post_url, taken_at))
            except Exception as e:
                # print(f"Lỗi khi xử lý liên kết {link.get_attribute('href')}: {e}")
                pass

        for post_url, taken_at in posts:
            self.driver.get(post_url+"/media")
            time.sleep(2)
            image_element = self.driver.find_elements(By.XPATH, '//img[@referrerpolicy="origin-when-cross-origin"]')
            # print(f"Đang trích xuất hình ảnh từ bài đăng: {post_url}, at {taken_at}")
            for img in image_element:
                image_url = img.get_attribute("src")
                if image_url:
                    results.append((image_url, post_url.replace(f"@{user}/", ""), taken_at))
                    # print(f"\tĐã trích xuất hình ảnh: {image_url}")

        return results

    def _extract_info_nodes(self, all_nodes):
        """Trích xuất các nút hình ảnh từ dữ liệu đã thu thập."""
        results = []
        for node in all_nodes:
            thread_items = node['node'].get('thread_items', [])
            for item in thread_items:
                post = item.get('post', {})
                carousel_media = post.get('carousel_media', [])
                try:
                    if not carousel_media:
                        image_url = post['image_versions2']['candidates'][0]['url']
                        taken_at = post.get('taken_at')
                        post_url = f"https://www.threads.net/post/{post['code']}"
                        results.append((image_url, post_url, taken_at))
                    else:
                        for media in carousel_media:
                            image_url = media['image_versions2']['candidates'][0]['url']
                            taken_at = post.get('taken_at')
                            post_url = f"https://www.threads.net/post/{post['code']}"
                            results.append((image_url, post_url, taken_at))
                except Exception as e:
                    pass

        self.driver.execute_script("window.scrollTo(0, 0);")
        return results