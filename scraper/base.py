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

    def _yield_event(self, event_type, data):
        """Helper function to format and yield event data."""
        return json.dumps({"type": event_type, "data": data})

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
            # Yield progress after each scroll
            all_nodes = self._get_all_nodes()
            yield self._yield_event("progress", {"found": len(all_nodes)})
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

    def _get_all_nodes(self):
        # This method needs to be implemented by each subclass
        raise NotImplementedError