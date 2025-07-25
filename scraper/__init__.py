# from .Scraper import InstagramScraper, ThreadsScraper, FacebookScraper
from .instagram import InstagramScraper
from .threads import ThreadsScraper
from .facebook import FacebookScraper

__all__ = ['InstagramScraper', 'ThreadsScraper', 'FacebookScraper']