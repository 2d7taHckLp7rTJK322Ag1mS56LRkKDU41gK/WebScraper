import os
import json
import time
import pickle
import re
import base64
import argparse
from urllib.request import urlretrieve
from concurrent.futures import ThreadPoolExecutor, as_completed
from seleniumwire import webdriver
from selenium.webdriver.common.by import By
from seleniumwire.utils import decode
from tqdm import tqdm
from datetime import datetime, timezone

# WORKING_DIR = "CloudStorage"


class BaseScraper:
    """
    Lớp cơ sở cho trình cào dữ liệu mạng xã hội, cung cấp các chức năng chung.
    """
    def __init__(self, headless=True, working_dir="CloudStorage"):
        self.driver = self._initialize_driver(headless=headless)
        self.working_dir = os.path.realpath(working_dir)
        os.makedirs(self.working_dir, exist_ok=True)

    def _initialize_driver(self, headless):
        """Khởi tạo WebDriver của Selenium với các tùy chọn được định cấu hình."""
        options = webdriver.ChromeOptions()
        options.add_argument('--enable-unsafe-swiftshader')
        options.add_argument('--ignore-certificate-errors')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--error-collection-disabled')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-infobars')
        if headless:
            options.add_argument('--headless')
        driver = webdriver.Chrome(options=options)
        # driver.set_window_size(300, 1400)
        return driver

    def _waiting_for_page_load(self):
        return self.driver.execute_script("return document.readyState") == "complete"
    
    def _clean_driver_requests(self):
        while len(self.driver.requests) > 0:
            # Xóa tất cả các yêu cầu đã thực hiện để tránh tràn bộ nhớ
            self.driver.requests.clear()
            del self.driver.requests

    def _load_cookies(self, cookie_file):
        """Tải cookie từ một tệp và thêm chúng vào phiên trình duyệt."""
        if os.path.exists(cookie_file):
            with open(cookie_file, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                self.driver.add_cookie(cookie)
            return True
        return False

    def _save_cookies(self, cookie_file):
        """Lưu cookie của phiên trình duyệt hiện tại vào một tệp."""
        os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
        with open(cookie_file, "wb") as f:
            pickle.dump(self.driver.get_cookies(), f)
    
    def _download_files(self, photos, download_dir, history_file):
        """Tải xuống tệp bằng đa luồng.
        Args:
            photos (list): Danh sách các tuple chứa (image_url, post_url, taken_at).
            download_dir (str): Thư mục để lưu các tệp đã tải xuống.
            history_file (str): Tệp để lưu lịch sử tải xuống.
        """
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

            filename = f"{datetime.fromtimestamp(taken_at).strftime("%Y%m%d_%H%M%S")}_{filename}" if taken_at else filename
            filepath = os.path.join(download_dir, filename)
            if not os.path.exists(filepath):
                urlretrieve(image_url, filepath)
            
                with open(history_file, "a") as f:
                    f.write(f"{post_url}, {filename}\n")

        # Dùng tqdm để hiển thị tiến trình tải xuống
        print(f"Đang tải xuống {len(photos)} tệp...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(download_file, photo) for photo in set(photos)]
            for _ in tqdm(as_completed(futures), total=len(futures), desc="Tải xuống", unit="tệp"):
                pass
    
    def _scroll_to_bottom(self):
        """Cuộn xuống cuối trang."""
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        while True:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        # Cuộn trở lại đầu trang
        self.driver.execute_script("window.scrollTo(0, 0);")  

        if not self._waiting_for_page_load():
            time.sleep(5)
            return self._scroll_to_bottom()

    def close(self):
        """Đóng WebDriver."""
        self.driver.quit()

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
            try:
                self.scrape_user(user)
            except Exception as e:
                print(f"Đã xảy ra lỗi khi cào dữ liệu người dùng {user}: {e}")

    def scrape_user(self, user):
        """Cào dữ liệu một người dùng Instagram duy nhất."""
        if not user:
            return

        print(f"Đang cào dữ liệu người dùng Instagram: {user}")
        self.driver.scopes = ['https://www.instagram.com/graphql/query*']
        self._clean_driver_requests()

        self.driver.get(f"https://www.instagram.com/{user}/")
        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            print(f"Không thể truy xuất dữ liệu hồ sơ cho người dùng {user}")
            return
        print(f"THÔNG TIN HỒ SƠ:")
        print(f"\tTên người dùng: {profile_data['name']}")
        print(f"\tID người dùng: {profile_data['id']}")
        print(f"\tURL hồ sơ: {profile_data['url']}")
        print(f"\tThời gian: {profile_data['timestamp']}")

        self._scroll_to_bottom()

        user_folder = os.path.join(self.working_dir, "instagram", user)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        print(f"\tĐã thu thập {len(all_nodes)} bài đăng từ người dùng {user}")
        
        photos = self._extract_info_nodes(all_nodes)

        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
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
            try:
                self.scrape_user(user)
            except Exception as e:
                print(f"Đã xảy ra lỗi khi cào dữ liệu người dùng {user}: {e}")


    def scrape_user(self, user):
        """Cào dữ liệu một người dùng Threads duy nhất."""
        if not user:
            return

        print(f"Đang cào dữ liệu người dùng Threads: {user}")
        # self.driver.scopes = ['https://www.facebook.com/api/graphql/*']
        self._clean_driver_requests()

        self.driver.get(f"https://www.threads.net/@{user}")

        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            print(f"Không thể truy xuất dữ liệu hồ sơ cho người dùng {user}")
            return
        print(f"THÔNG TIN HỒ SƠ:")
        print(f"\tTên người dùng: {profile_data['name']}")
        print(f"\tID người dùng: {profile_data['id']}")
        print(f"\tURL hồ sơ: {profile_data['url']}")
        print(f"\tThời gian: {profile_data['timestamp']}")

        self._scroll_to_bottom()

        user_folder = os.path.join(self.working_dir, "threads", user)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        print(f"\tĐã thu thập {len(all_nodes)} bài đăng từ người dùng {user}")
        photos = self._extract_info_nodes(all_nodes)
        photos += self._extract_info_nodes_in_html(user)

        
        print(f"\tĐã thu thập {len(photos)} hình ảnh từ người dùng {user}")

        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
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
            try:
                self.scrape_user(user)
            except Exception as e:
                print(f"Đã xảy ra lỗi khi cào dữ liệu người dùng {user}: {e}")

    def scrape_user(self, user):
        """Cào dữ liệu một người dùng Facebook duy nhất."""
        if not user:
            return

        print(f"Đang cào dữ liệu người dùng Facebook: {user}")
        self.driver.scopes = ['https://www.facebook.com/api/graphql/*']
        self._clean_driver_requests()

        self.driver.get(f"https://www.facebook.com/{user}/photos_by")
        time.sleep(5)

        profile_data = self._get_profile_data()
        if not profile_data:
            print(f"Không thể truy xuất dữ liệu hồ sơ cho người dùng {user}")
            return
        print(f"THÔNG TIN HỒ SƠ:")
        print(f"\tTên người dùng: {profile_data['name']}")
        print(f"\tID người dùng: {profile_data['id']}")
        print(f"\tURL hồ sơ: {profile_data['url']}")
        print(f"\tThời gian: {profile_data['timestamp']}")

        self._scroll_to_bottom()

        user_folder = os.path.join(self.working_dir, "facebook", user)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, 'info.json'), 'w', encoding='utf-8') as f:
            json.dump(profile_data, f, ensure_ascii=False, indent=4)
            
        all_nodes = self._get_all_nodes()
        
        photos = self._extract_info_nodes(all_nodes)
        photos += self._extract_info_nodes_in_html(user)

        self._download_files(photos, user_folder, os.path.join(user_folder, "history.txt"))
        print(f"\tĐã cào dữ liệu thành công {len(photos)} hình ảnh cho người dùng {user}")

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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Social Media Scraper Framework")
    parser.add_argument("platform", choices=['instagram', 'threads', 'facebook'], help="Nền tảng mạng xã hội để cào dữ liệu")
    parser.add_argument("-l", "--list_user", type=str, help="Đường dẫn đến tệp chứa danh sách tên người dùng")
    parser.add_argument("-u", "--user", type=str, help="Tên người dùng duy nhất để cào dữ liệu")
    parser.add_argument("-a", "--all", action="store_true", help="Cào dữ liệu tất cả người dùng trong lịch sử")
    parser.add_argument("--no-headless", action="store_true", help="Chạy trình duyệt ở chế độ không có giao diện đồ họa")
    args = parser.parse_args()

    list_user = []
    if args.list_user:
        with open(args.list_user, "r") as f:
            list_user = f.read().splitlines()
    elif args.user:
        list_user = [args.user]
    elif args.all:
        platform_dir = args.platform.capitalize()
        if os.path.exists(platform_dir):
            list_user = [d for d in os.listdir(platform_dir) if os.path.isdir(os.path.join(platform_dir, d))]

    if not list_user:
        print("Vui lòng cung cấp danh sách người dùng, một người dùng duy nhất hoặc tùy chọn '--all'.")
        exit(1)

    scraper = None
    try:
        if args.platform == 'instagram':
            scraper = InstagramScraper(headless=not args.no_headless)
        elif args.platform == 'threads':
            scraper = ThreadsScraper(headless=not args.no_headless)
        elif args.platform == 'facebook':
            scraper = FacebookScraper(headless=not args.no_headless)
        
        scraper.scrape_users(list_user)

    except Exception as e:
        print(f"Đã xảy ra lỗi không mong muốn: {e}")
    finally:
        if scraper:
            scraper.close()