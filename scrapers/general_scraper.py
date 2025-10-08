import asyncio
import json
import re
from urllib.parse import urlparse, urljoin
from typing import Set, List, Dict, Optional
from datetime import datetime
import logging
from pathlib import Path
import hashlib
import time

from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import NoExtractionStrategy
from crawl4ai.async_configs import CrawlerRunConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

try:
    # Prefer centralized path helpers if available
    from paths import data_subdir
except Exception:
    data_subdir = None

class UniversityScraper:
    def __init__(self, output_dir: str = "data/general", max_concurrent: int = 5):
        # More restrictive domain filtering
        self.allowed_domains = {
            "isb.nu.edu.pk",
            "nu.edu.pk"  # This will match nu.edu.pk but not subdomains like khi.nu.edu.pk
        }
        
        # Exclude patterns (media, social, auth, campus pages, etc.)
        self.exclude_patterns = [
            r'facebook\.com', r'twitter\.com', r'linkedin\.com', r'instagram\.com',
            r'youtube\.com', r'github\.com', r'whatsapp\.com',
            r'/Campus/[A-Za-z]+', r'/campus/[A-Za-z]+',
            r'/(Karachi|Peshawar|Lahore|Islamabad|Faisalabad|Multan|Chiniot)',
            r'/(karachi|peshawar|lahore|islamabad|faisalabad|multan|chiniot)',
            r'/faculty', r'/staff', r'/people', r'/team',
            r'/professor', r'/instructor', r'/dean', r'/hod',
            r'/event', r'/calendar', r'/seminar', r'/workshop', r'/conference',
            r'\.(pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar|exe|jpg|jpeg|png|gif|mp4|mp3|wav|avi|mov|css|js|ico|svg|woff|woff2|ttf|eot)($|\?)',
            r'/login', r'/signin', r'/signup', r'/auth', r'/logout', r'/register',
            r'/404', r'/error', r'/search\?', r'#',
            r'mailto:', r'tel:', r'javascript:',
            r'/content/libs/',  # Bootstrap and other library files
            r'/assets/',        # Asset files
            r'/static/',        # Static files
            r'/resources/',     # Resource files
        ]
        
        self.visited_urls: Set[str] = set()
        self.failed_urls: Set[str] = set()
        self.scraped_data: List[Dict] = []
        # Route outputs under data/<name> by default, with centralized helper if present
        if data_subdir and output_dir.startswith("data/"):
            # Use the subfolder name after 'data/'
            sub = output_dir.split("/", 1)[1] or "general"
            self.output_dir = data_subdir(sub)
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.max_concurrent = max_concurrent
        
        # Thread-safe locks
        self.visited_lock = asyncio.Lock()
        self.data_lock = asyncio.Lock()
        
        # Output subfolders
        (self.output_dir / "raw").mkdir(exist_ok=True)
        (self.output_dir / "metadata").mkdir(exist_ok=True)
        
        # No LLM-based extraction; use plain crawling only
    
    def normalize_url(self, url: str) -> str:
        url = url.split('#')[0]
        url = url.rstrip('/')
        try:
            parsed = urlparse(url)
            normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                normalized += f"?{parsed.query}"
            return normalized
        except:
            return url
    
    def is_valid_url(self, url: str) -> bool:
        try:
            if not url or not url.startswith(('http://', 'https://')):
                return False
            
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www. for comparison
            clean_domain = domain.replace('www.', '') if domain.startswith('www.') else domain
            
            # Exact domain matching - no subdomains allowed except www
            domain_allowed = False
            for allowed in self.allowed_domains:
                clean_allowed = allowed.replace('www.', '') if allowed.startswith('www.') else allowed
                if clean_domain == clean_allowed or domain == f"www.{clean_allowed}":
                    domain_allowed = True
                    break
            
            if not domain_allowed:
                logger.debug(f"Domain not allowed: {domain}")
                return False
            
            # Check exclude patterns
            for pattern in self.exclude_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    logger.debug(f"URL excluded by pattern {pattern}: {url}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Error validating URL {url}: {e}")
            return False
    
    def extract_links(self, html: str, base_url: str) -> Set[str]:
        links = set()
        if not html:
            return links
        
        # Only extract href links, skip src and action to avoid CSS/JS files
        patterns = [r'href=[\'"]?([^\'" >]+)']
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                if match.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue
                
                absolute_url = urljoin(base_url, match)
                normalized_url = self.normalize_url(absolute_url)
                
                if self.is_valid_url(normalized_url):
                    links.add(normalized_url)
        
        return links
    
    def generate_file_hash(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
    
    async def scrape_page(self, url: str, crawler: AsyncWebCrawler, semaphore: asyncio.Semaphore) -> Optional[Dict]:
        async with semaphore:  # Limit concurrent requests
            try:
                logger.info(f"Scraping: {url}")

                config = CrawlerRunConfig(
                    url=url,
                    word_count_threshold=50,
                    extraction_strategy=NoExtractionStrategy(),
                    screenshot=False,
                    remove_overlay_elements=True,
                    excluded_tags=['header', 'footer', 'nav', 'script', 'style']
                )

                result = await crawler.arun(url=url, config=config)
                
                if not result or not result.success:
                    error_msg = getattr(result, 'error_message', 'Unknown error')
                    logger.warning(f"Failed to scrape {url}: {error_msg}")
                    async with self.visited_lock:
                        self.failed_urls.add(url)
                    return None

                html_content = getattr(result, 'html', '')
                markdown_content = getattr(result, 'markdown', '')
                cleaned_text_content = getattr(result, 'cleaned_text', markdown_content)
                metadata = getattr(result, 'metadata', {})

                links = self.extract_links(html_content, url) if html_content else set()

                page_data = {
                    'url': url,
                    'title': metadata.get('title', ''),
                    'description': metadata.get('description', ''),
                    'content': markdown_content,
                    'clean_text': cleaned_text_content,
                    'links': list(links),
                    'metadata': {
                        'scraped_at': datetime.now().isoformat(),
                        'word_count': len(cleaned_text_content.split()),
                        'language': metadata.get('language', 'en'),
                        'keywords': metadata.get('keywords', ''),
                    }
                }

                if page_data['metadata']['word_count'] < 50:
                    logger.info(f"Skipping {url} - insufficient content")
                    return None

                # Save files
                file_hash = self.generate_file_hash(url)
                with open(self.output_dir / "raw" / f"{file_hash}.md", 'w', encoding='utf-8') as f:
                    f.write(f"# {page_data['title']}\n\n")
                    f.write(f"**URL:** {url}\n\n")
                    f.write(f"**Description:** {page_data['description']}\n\n")
                    f.write("---\n\n")
                    f.write(page_data['content'])

                metadata_file_content = {
                    'url': url,
                    'file_hash': file_hash,
                    'title': page_data['title'],
                    'description': page_data['description'],
                    'word_count': page_data['metadata']['word_count'],
                    'scraped_at': page_data['metadata']['scraped_at'],
                    'links_found': len(page_data['links']),
                }
                with open(self.output_dir / "metadata" / f"{file_hash}.json", 'w', encoding='utf-8') as f:
                    json.dump(metadata_file_content, f, indent=2, ensure_ascii=False)

                return page_data

            except Exception as e:
                logger.error(f"Critical error scraping {url}: {e}", exc_info=True)
                async with self.visited_lock:
                    self.failed_urls.add(url)
                return None
    
    async def scrape_batch(self, urls: List[str], crawler: AsyncWebCrawler, semaphore: asyncio.Semaphore) -> List[Dict]:
        """Scrape multiple URLs concurrently"""
        tasks = [self.scrape_page(url, crawler, semaphore) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Task failed with exception: {result}")
            elif result is not None:
                successful_results.append(result)
        
        return successful_results
    
    async def scrape_recursive(self, start_urls: List[str], max_depth: int = 5, max_pages: int = 1000):
        # Initialize multiple crawler instances for better concurrency
        crawlers = []
        semaphore = asyncio.Semaphore(self.max_concurrent)
        
        try:
            # Create crawler pool
            for i in range(min(3, self.max_concurrent)):  # Max 3 browser instances
                crawler = AsyncWebCrawler(
                    browser_type="chromium",
                    headless=True,
                    page_timeout=60000,  # Reduced timeout
                    delay_before_return_html=1.0  # Reduced delay
                )
                await crawler.start()
                crawlers.append(crawler)
            
            # Use the first crawler for the main loop
            main_crawler = crawlers[0]
            
            queue = [(self.normalize_url(url), 0) for url in start_urls]
            batch_size = min(self.max_concurrent, 10)  # Process in batches
            
            while queue and len(self.visited_urls) < max_pages:
                # Get batch of URLs to process
                current_batch = []
                batch_urls = []
                
                while queue and len(current_batch) < batch_size:
                    url, depth = queue.pop(0)
                    
                    async with self.visited_lock:
                        if url in self.visited_urls or depth > max_depth:
                            continue
                        self.visited_urls.add(url)
                    
                    current_batch.append((url, depth))
                    batch_urls.append(url)
                
                if not current_batch:
                    break
                
                # Process batch concurrently
                batch_results = await self.scrape_batch(batch_urls, main_crawler, semaphore)
                
                # Add successful results and extract new links
                async with self.data_lock:
                    for i, page_data in enumerate(batch_results):
                        if page_data:
                            self.scraped_data.append(page_data)
                            url, depth = current_batch[i]
                            
                            # Add new links to queue if within depth limit
                            if depth < max_depth:
                                for link in page_data['links']:
                                    normalized_link = self.normalize_url(link)
                                    
                                    async with self.visited_lock:
                                        if (normalized_link not in self.visited_urls and 
                                            not any(q_url == normalized_link for q_url, _ in queue)):
                                            queue.append((normalized_link, depth + 1))
                
                # Progress update
                if len(self.visited_urls) % 20 == 0:
                    logger.info(f"Progress: {len(self.visited_urls)} visited, {len(self.scraped_data)} scraped, {len(queue)} in queue")
                
                # Small delay between batches
                await asyncio.sleep(0.5)
                
        finally:
            # Close all crawlers
            for crawler in crawlers:
                try:
                    await crawler.close()
                except Exception as e:
                    logger.error(f"Error closing crawler: {e}")
    
    
    def generate_report(self):
        report = {
            'summary': {
                'total_visited': len(self.visited_urls),
                'total_scraped': len(self.scraped_data),
                'total_failed': len(self.failed_urls),
                'output_directory': str(self.output_dir),
                'allowed_domains': list(self.allowed_domains)
            },
            'visited_urls': sorted(list(self.visited_urls)),
            'failed_urls': sorted(list(self.failed_urls)),
            'scraped_domains': sorted(list(set(urlparse(url).netloc for url in self.visited_urls)))
        }
        
        report_file = self.output_dir / "metadata" / "report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Report generated: {report_file}")
        
        # Print summary
        print(f"\n=== SCRAPING SUMMARY ===")
        print(f"Total URLs visited: {len(self.visited_urls)}")
        print(f"Total pages scraped: {len(self.scraped_data)}")
        print(f"Total failed: {len(self.failed_urls)}")
        print(f"Domains scraped: {', '.join(report['scraped_domains'])}")
        print(f"Output directory: {self.output_dir}")

# -------------------------------
# Example usage
# -------------------------------
async def main():
    OUTPUT_DIR = "data/general"
    MAX_DEPTH = 5
    MAX_PAGES = 1000
    MAX_CONCURRENT = 8  # Adjust based on your system and target server capacity
    
    print(f"Initializing parallel scraper (Concurrent: {MAX_CONCURRENT})...")
    scraper = UniversityScraper(output_dir=OUTPUT_DIR, max_concurrent=MAX_CONCURRENT)
    
    start_urls = [
        "https://isb.nu.edu.pk/",
        "https://www.nu.edu.pk/"
    ]
    
    start_time = time.time()
    try:
        await scraper.scrape_recursive(start_urls, MAX_DEPTH, MAX_PAGES)
        scraper.generate_report()
    except KeyboardInterrupt:
        print("Interrupted by user")
        scraper.generate_report()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        scraper.generate_report()
    
    elapsed_time = time.time() - start_time
    print(f"\nTotal time: {elapsed_time/60:.2f} minutes")
    print(f"Data saved to: {OUTPUT_DIR}/")

if __name__ == "__main__":
    asyncio.run(main())