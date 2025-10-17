import requests
from bs4 import BeautifulSoup
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
import argparse
import urllib.parse
import re
import random


class ConferencePDFDownloader:
    def __init__(self, base_url, year, save_dir="conference_papers", use_selenium=False):
        self.base_url = base_url.rstrip("/")  # Ensure no trailing slash
        self.year = year
        self.save_dir = f"{save_dir}"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.use_selenium = use_selenium
        self.driver = None
        
        # arXiv search settings
        self.arxiv_last_request_time = 0
        self.arxiv_request_interval = 5  # Increased to 5 seconds interval
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        if use_selenium:
            self.setup_selenium()
        
        # Create save directories
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "pdfs"), exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "metadata"), exist_ok=True)
        
        # Log file
        self.log_file = os.path.join(self.save_dir, "download_log.txt")
    
    def setup_selenium(self):
        """Setup Selenium WebDriver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Headless mode
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.set_page_load_timeout(30)
            self.log("Selenium WebDriver initialized successfully")
        except Exception as e:
            self.log(f"Selenium WebDriver initialization failed: {e}")
            self.use_selenium = False
    
    def close_selenium(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
    
    def log(self, message):
        """Log message"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')
    
    def get_paper_list(self, event_type="oral"):
        """Get conference paper list"""
        page_url = f"{self.base_url}/virtual/{self.year}/events/{event_type}"
        self.log(f"Fetching paper list: {page_url}")
        
        try:
            response = self.session.get(page_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            paper_divs = soup.find_all('div', class_='virtual-card')
            papers = []
            
            for idx, div in enumerate(paper_divs):
                try:
                    # Get title and link
                    link = div.find('a', class_='small-title text-underline-hover')
                    if not link: continue
                    
                    title = link.text.strip()
                    relative_url = link.get('href', '')
                    paper_url = self.base_url + relative_url if relative_url else ""
                    paper_id = relative_url.split('/')[-1] if relative_url else str(idx)
                    
                    # Get author information
                    authors = div.find_next_sibling('div', class_='author-str')
                    authors = authors.text.strip() if authors else "Unknown"
                    
                    # Get abstract
                    abstract = ""
                    details = div.find_next_sibling('details')
                    if details:
                        abstract_div = details.find('div', class_='text-start p-4')
                        if abstract_div:
                            abstract = abstract_div.text.strip()
                    
                    papers.append({
                        'id': paper_id,
                        'title': title,
                        'paper_page_url': paper_url,
                        'authors': authors,
                        'abstract': abstract,
                        'type': event_type.upper(),
                        'year': self.year,
                        'search_queries': {
                            'arxiv': title
                        }
                    })
                except Exception as e:
                    self.log(f"Error parsing paper: {e}")
                    continue
            
            self.log(f"Found {len(papers)} {event_type} papers")
            return papers
        except Exception as e:
            self.log(f"Failed to get paper list: {e}")
            return []
    
    def get_openreview_url(self, paper_page_url):
        """Get OpenReview link from paper page"""
        try:
            response = self.session.get(paper_page_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            openreview_link = soup.find('a', {'title': 'OpenReview'})
            if openreview_link:
                return openreview_link.get('href')
            
            for link in soup.find_all('a'):
                if 'openreview.net' in link.get('href', ''):
                    return link.get('href')
            
            return None
        except Exception as e:
            self.log(f"Failed to get OpenReview link: {e}")
            return None
    
    def get_pdf_url_from_openreview(self, openreview_url):
        """Get PDF from OpenReview link"""
        if not openreview_url:
            return None
        if 'forum?id=' in openreview_url:
            paper_id = openreview_url.split('forum?id=')[1].split('&')[0]
            return f"https://openreview.net/pdf?id={paper_id}"
        return None
    
    def wait_for_arxiv_rate_limit(self):
        """Wait for arXiv API rate limit"""
        current_time = time.time()
        time_since_last_request = current_time - self.arxiv_last_request_time
        if time_since_last_request < self.arxiv_request_interval:
            sleep_time = self.arxiv_request_interval - time_since_last_request
            time.sleep(sleep_time + random.uniform(1.0, 3.0))  # Add random delay
        self.arxiv_last_request_time = time.time()
    
    def search_arxiv(self, title, authors):
        """Search for paper on arXiv - improved fuzzy matching version"""
        try:
            # Respect arXiv API rate limits
            self.wait_for_arxiv_rate_limit()
            
            # Clean title, remove special characters and common conference names
            clean_title = re.sub(r'[^\w\s]', ' ', title)
            # Remove common conference-related words to reduce noise
            conference_words = ['neurips', 'icml', 'iclr', 'cvpr', 'eccv', 'aaai', 'ijcai', 'acl', 'emnlp', 'naacl', 'conference', 'proceedings', 'workshop']
            for word in conference_words:
                clean_title = re.sub(r'\b' + word + r'\b', '', clean_title, flags=re.IGNORECASE)
            
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            
            if not clean_title:
                return None
            
            # Use multiple search strategies
            search_strategies = [
                f'ti:"{clean_title}"',  # Exact title search
                f'all:"{clean_title}"',  # Full text search
            ]
            
            # If title is too long, use keywords
            if len(clean_title.split()) > 5:
                important_words = self.extract_important_words(clean_title)
                if important_words:
                    search_strategies.append(f'all:"{" ".join(important_words)}"')
            
            for search_query in search_strategies:
                query = urllib.parse.quote(search_query)
                arxiv_url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results=5"
                
                try:
                    response = self.session.get(arxiv_url, timeout=30)
                    if response.status_code == 200:
                        # Check if HTML is returned (blocked)
                        if 'html' in response.headers.get('content-type', '').lower():
                            self.log("arXiv returned HTML page, possibly blocked, skipping this search")
                            continue
                            
                        soup = BeautifulSoup(response.content, 'xml')
                        entries = soup.find_all('entry')
                        
                        best_match = None
                        best_score = 0
                        
                        for entry in entries:
                            entry_title = entry.find('title').text.strip() if entry.find('title') else ""
                            entry_authors = [author.find('name').text.strip() if author.find('name') else "" 
                                           for author in entry.find_all('author')]
                            
                            # Calculate comprehensive matching score
                            title_score = self.title_similarity(clean_title, entry_title)
                            author_score = self.author_similarity(authors, ' '.join(entry_authors))
                            
                            # Combined score, title matching is more important
                            total_score = title_score * 0.7 + author_score * 0.3
                            
                            if total_score > best_score and total_score > 0.4:  # Set matching threshold
                                best_score = total_score
                                pdf_link = entry.find('link', title='pdf')
                                if pdf_link and pdf_link.get('href'):
                                    best_match = pdf_link.get('href')
                        
                        if best_match:
                            self.log(f"arXiv found match (score: {best_score:.2f}): {best_match}")
                            return best_match
                            
                except Exception as e:
                    self.log(f"arXiv search strategy failed {search_query}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            self.log(f"arXiv search failed: {e}")
            return None
    
    def extract_important_words(self, text):
        """Extract important words from title"""
        # Remove stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}
        words = text.lower().split()
        important_words = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Return top 3-5 important words
        return important_words[:4]
    
    def title_similarity(self, title1, title2):
        """Improved title similarity calculation"""
        if not title1 or not title2:
            return 0
            
        # Preprocess titles
        t1 = re.sub(r'[^\w\s]', ' ', title1.lower())
        t2 = re.sub(r'[^\w\s]', ' ', title2.lower())
        
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        if not words1 or not words2:
            return 0
        
        # Jaccard similarity
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        jaccard_sim = len(intersection) / len(union)
        
        # Sequence similarity (consider word order)
        seq1 = t1.split()
        seq2 = t2.split()
        seq_sim = self.sequence_similarity(seq1, seq2)
        
        # Combined score
        return jaccard_sim * 0.6 + seq_sim * 0.4
    
    def sequence_similarity(self, seq1, seq2):
        """Calculate sequence similarity"""
        if not seq1 or not seq2:
            return 0
            
        # Simple sequence matching: calculate longest common subsequence ratio
        def lcs_length(x, y):
            m, n = len(x), len(y)
            dp = [[0] * (n + 1) for _ in range(m + 1)]
            
            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    if x[i-1] == y[j-1]:
                        dp[i][j] = dp[i-1][j-1] + 1
                    else:
                        dp[i][j] = max(dp[i-1][j], dp[i][j-1])
            
            return dp[m][n]
        
        lcs_len = lcs_length(seq1, seq2)
        return lcs_len / max(len(seq1), len(seq2))
    
    def author_similarity(self, authors1, authors2):
        """Author similarity calculation"""
        if not authors1 or not authors2:
            return 0
            
        # Extract last names for comparison
        def extract_last_names(authors_str):
            names = re.findall(r'\b[A-Z][a-z]+\b', authors_str)
            return set([name.lower() for name in names])
        
        last_names1 = extract_last_names(authors1)
        last_names2 = extract_last_names(authors2)
        
        if not last_names1 or not last_names2:
            return 0
            
        intersection = last_names1.intersection(last_names2)
        union = last_names1.union(last_names2)
        
        return len(intersection) / len(union) if union else 0
    
    def find_pdf_through_search(self, paper):
        """Find PDF through search - now only using arXiv"""
        title = paper['title']
        authors = paper['authors']
        
        self.log(f"Starting arXiv search for paper: {title}")
        
        # Only search on arXiv
        arxiv_pdf = self.search_arxiv(title, authors)
        if arxiv_pdf:
            self.log(f"Found PDF on arXiv: {arxiv_pdf}")
            return arxiv_pdf
        
        self.log("arXiv search failed to find PDF")
        return None
    
    def download_pdf(self, pdf_url, filename):
        """Download PDF file - improved version, handles anti-crawling"""
        try:
            # For arXiv URLs, add random delay
            if 'arxiv.org' in pdf_url:
                time.sleep(random.uniform(2.0, 5.0))
            
            # Use session to maintain connection
            response = self.session.get(pdf_url, timeout=60, stream=True)
            
            if response.status_code == 200:
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                
                # If HTML is returned, it means blocked
                if 'text/html' in content_type:
                    self.log(f"Blocked by anti-crawling, returned HTML page: {pdf_url}")
                    return False
                
                # Check if file content is PDF
                first_chunk = response.content[:100]
                if b'%PDF' not in first_chunk:
                    self.log(f"URL returned content is not PDF, content type: {content_type}")
                    # Check if it's an error page
                    if b'captcha' in first_chunk.lower() or b'robot' in first_chunk.lower():
                        self.log("Detected captcha page, blocked by anti-crawling mechanism")
                    return False
                
                # Save PDF file
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Verify file size
                file_size = os.path.getsize(filename)
                if file_size < 1024:  # Less than 1KB might be error page
                    self.log(f"Downloaded file too small ({file_size} bytes), might be error page")
                    os.remove(filename)
                    return False
                
                self.log(f"PDF downloaded successfully: {filename} ({file_size} bytes)")
                return True
            else:
                self.log(f"Download failed, status code: {response.status_code}")
                return False
                
        except Exception as e:
            self.log(f"Download failed: {e}")
            return False
    
    def clean_filename(self, filename):
        """Clean filename, remove illegal characters"""
        return ''.join(c if c.isalnum() or c in (' ', '.', '_') else '_' for c in filename).strip()[:150]
    
    def download_single_paper(self, paper):
        """Download single paper"""
        paper_id = paper['id']
        title = paper['title']
        safe_title = self.clean_filename(title)
        pdf_filename = os.path.join(self.save_dir, "pdfs", f"{paper_id}_{safe_title}.pdf")
        
        # Check if file already exists - don't modify existing files
        if os.path.exists(pdf_filename):
            # For existing files, preserve original metadata without modification
            existing_paper = paper.copy()
            existing_paper['local_pdf_path'] = pdf_filename
            existing_paper['download_status'] = 'exists'
            existing_paper['download_method'] = 'existing'
            return existing_paper
        
        # Method 1: Original method (OpenReview)
        openreview_url = self.get_openreview_url(paper['paper_page_url'])
        pdf_url = self.get_pdf_url_from_openreview(openreview_url) if openreview_url else None
        
        if pdf_url and self.download_pdf(pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
            paper['download_method'] = 'openreview'
            paper['pdf_url'] = pdf_url
            return paper
        
        # Method 2: Only search on arXiv
        search_pdf_url = self.find_pdf_through_search(paper)
        if search_pdf_url and self.download_pdf(search_pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
            paper['download_method'] = 'arxiv'
            paper['pdf_url'] = search_pdf_url
            return paper
        
        paper['download_status'] = 'failed'
        paper['download_method'] = 'none'
        return paper
    
    def download_all_papers(self, papers, max_workers=2):  # Reduced concurrency
        """Download all papers in parallel"""
        self.log(f"Starting download of {len(papers)} papers...")
        results = {'success': [], 'exists': [], 'failed': []}
        
        # Limit concurrency to avoid triggering anti-crawling
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_paper = {executor.submit(self.download_single_paper, paper): paper for paper in papers}
            with tqdm(total=len(papers), desc="Download Progress") as pbar:
                for future in as_completed(future_to_paper):
                    paper = future_to_paper[future]
                    try:
                        result = future.result()
                        if result['download_status'] == 'success':
                            results['success'].append(result)
                        elif result['download_status'] == 'exists':
                            results['exists'].append(result)
                        else:
                            results['failed'].append(result)
                    except Exception as e:
                        self.log(f"Download error: {e}")
                        results['failed'].append(paper)
                    pbar.update(1)
        
        # Count download methods
        methods = {}
        for paper in results['success']:
            method = paper.get('download_method', 'unknown')
            methods[method] = methods.get(method, 0) + 1
        
        self.log(f"Download method statistics: {methods}")
        return results
    
    def save_metadata(self, papers, filename):
        """Save paper metadata"""
        filepath = os.path.join(self.save_dir, "metadata", filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        self.log(f"Metadata saved to: {filepath}")
    
    def run(self, event_types, max_workers=2):  # Default concurrency reduced to 2
        """Run download process"""
        all_papers = []
        for event_type in event_types:
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
            self.save_metadata(papers, f"{event_type}_papers.json")

        results = self.download_all_papers(all_papers, max_workers=max_workers)

        # Save detailed results - keep existing files separate and append new successes
        # Don't modify existing metadata files, create new combined file
        combined_success = results['success'] + results['exists']
        self.save_metadata(combined_success, "downloaded_papers.json")
        self.save_metadata(results['failed'], "failed_papers.json")

        # Generate summary report
        self.generate_summary_report(results)

        self.log("Download completed!")
        if self.use_selenium:
            self.close_selenium()
    
    def generate_summary_report(self, results):
        """Generate download summary report"""
        total = len(results['success']) + len(results['exists']) + len(results['failed'])
        if total == 0:
            success_rate = 0
        else:
            success_rate = (len(results['success']) + len(results['exists'])) / total * 100
            
        report = {
            'total_papers': total,
            'successful_downloads': len(results['success']),
            'existing_files': len(results['exists']),
            'failed_downloads': len(results['failed']),
            'success_rate': success_rate,
            'download_methods': {}
        }
        
        # Count download methods
        for paper in results['success']:
            method = paper.get('download_method', 'unknown')
            report['download_methods'][method] = report['download_methods'].get(method, 0) + 1
        
        report_file = os.path.join(self.save_dir, "download_summary.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.log(f"Download summary: {report['successful_downloads']} successful, {report['existing_files']} existing, "
                f"{report['failed_downloads']} failed, success rate {report['success_rate']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Conference Paper Downloader")
    parser.add_argument('-c', type=str, required=True, help='Conference shortname (neurips/iclr/icml) or base URL (e.g., https://icml.cc)')
    parser.add_argument('-y', type=int, required=True, help='Year of the conference')
    parser.add_argument('--event_types', nargs='+', default=["oral"], help='Event types to download (e.g., oral, poster)')
    parser.add_argument('--max_workers', type=int, default=2, help='Maximum number of parallel downloads (recommended 1-2)')
    
    args = parser.parse_args()
    
    # Allow -c to accept short names or full URLs
    shortname_map = {
        'neurips': 'https://neurips.cc',
        'iclr': 'https://iclr.cc',
        'icml': 'https://icml.cc',
    }

    conf_input = args.c.strip()
    conf_key = conf_input.lower()
    if conf_key in shortname_map:
        base_url = shortname_map[conf_key]
    elif conf_input.startswith('http://') or conf_input.startswith('https://'):
        base_url = conf_input.rstrip('/')
    else:
        # If user input like "neurips" or with year etc., try to parse by short name
        # Take first word as candidate short name
        candidate = conf_key.split()[0]
        base_url = shortname_map.get(candidate, conf_input)

    downloader = ConferencePDFDownloader(
        base_url=base_url,
        year=args.y,
        save_dir=f"{conf_key}_{args.y}_papers"
    )
    downloader.log(f"Using base_url: {base_url}")
    
    try:
        downloader.run(event_types=args.event_types, max_workers=args.max_workers)
    except KeyboardInterrupt:
        downloader.log("User interrupted download")
    except Exception as e:
        downloader.log(f"Program exception: {e}")


if __name__ == "__main__":
    main()