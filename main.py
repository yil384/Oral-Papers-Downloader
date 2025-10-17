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
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re


class ConferencePDFDownloader:
    def __init__(self, base_url, year, save_dir="conference_papers", use_selenium=False):
        self.base_url = base_url.rstrip("/")  # 确保没有尾部斜杠
        self.year = year
        self.save_dir = f"{save_dir}_{year}"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.use_selenium = use_selenium
        self.driver = None
        
        if use_selenium:
            self.setup_selenium()
        
        # 创建保存目录
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "pdfs"), exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "metadata"), exist_ok=True)
        
        # 日志文件
        self.log_file = os.path.join(self.save_dir, "download_log.txt")
    
    def setup_selenium(self):
        """设置Selenium WebDriver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 无头模式
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(30)
            self.log("Selenium WebDriver 初始化成功")
        except Exception as e:
            self.log(f"Selenium WebDriver 初始化失败: {e}")
            self.use_selenium = False
    
    def close_selenium(self):
        """关闭Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
    
    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')
    
    def get_paper_list(self, event_type="oral"):
        """获取会议论文列表"""
        page_url = f"{self.base_url}/virtual/{self.year}/events/{event_type}"
        self.log(f"获取论文列表: {page_url}")
        
        try:
            response = requests.get(page_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            paper_divs = soup.find_all('div', class_='virtual-card')
            papers = []
            
            for idx, div in enumerate(paper_divs):
                try:
                    # 获取标题和链接
                    link = div.find('a', class_='small-title text-underline-hover')
                    if not link: continue
                    
                    title = link.text.strip()
                    relative_url = link.get('href', '')
                    paper_url = self.base_url + relative_url if relative_url else ""
                    paper_id = relative_url.split('/')[-1] if relative_url else str(idx)
                    
                    # 获取作者信息
                    authors = div.find_next_sibling('div', class_='author-str')
                    authors = authors.text.strip() if authors else "Unknown"
                    
                    # 获取摘要
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
                            'google': f"{title} {authors} {self.year} pdf",
                            'arxiv': title
                        }
                    })
                except Exception as e:
                    self.log(f"解析论文出错: {e}")
                    continue
            
            self.log(f"找到 {len(papers)} 篇 {event_type} 论文")
            return papers
        except Exception as e:
            self.log(f"获取论文列表失败: {e}")
            return []
    
    def get_openreview_url(self, paper_page_url):
        """从论文页面获取 OpenReview 链接"""
        try:
            response = requests.get(paper_page_url, headers=self.headers, timeout=30)
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
            self.log(f"获取 OpenReview 链接失败: {e}")
            return None
    
    def get_pdf_url_from_openreview(self, openreview_url):
        """从 OpenReview 链接获取 PDF"""
        if not openreview_url:
            return None
        if 'forum?id=' in openreview_url:
            paper_id = openreview_url.split('forum?id=')[1].split('&')[0]
            return f"https://openreview.net/pdf?id={paper_id}"
        return None
    
    def search_arxiv(self, title, authors):
        """在arXiv搜索论文"""
        try:
            # 清理标题，移除特殊字符
            clean_title = re.sub(r'[^\w\s]', ' ', title)
            query = urllib.parse.quote(clean_title)
            arxiv_url = f"http://export.arxiv.org/api/query?search_query=ti:\"{query}\"&start=0&max_results=3"
            
            response = requests.get(arxiv_url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'xml')
                entries = soup.find_all('entry')
                
                for entry in entries:
                    entry_title = entry.find('title').text.strip() if entry.find('title') else ""
                    # 简单的标题匹配
                    if self.title_similarity(clean_title, entry_title) > 0.7:
                        pdf_link = entry.find('link', title='pdf')
                        if pdf_link and pdf_link.get('href'):
                            return pdf_link.get('href')
            
            return None
        except Exception as e:
            self.log(f"arXiv搜索失败: {e}")
            return None
    
    def title_similarity(self, title1, title2):
        """计算两个标题的相似度（简单实现）"""
        words1 = set(title1.lower().split())
        words2 = set(title2.lower().split())
        if not words1 or not words2:
            return 0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)
    
    def search_google_scholar(self, query):
        """使用Selenium搜索Google Scholar"""
        if not self.use_selenium:
            return None
            
        try:
            search_url = f"https://scholar.google.com/scholar?q={urllib.parse.quote(query)}"
            self.driver.get(search_url)
            
            # 等待结果加载
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "gs_rt"))
            )
            
            # 查找PDF链接
            results = self.driver.find_elements(By.CLASS_NAME, "gs_rt")
            for result in results[:3]:  # 检查前3个结果
                pdf_links = result.find_elements(By.XPATH, ".//a[contains(@href, '.pdf')]")
                if pdf_links:
                    return pdf_links[0].get_attribute('href')
                
                # 检查结果标题中的链接
                links = result.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute('href')
                    if href and ('arxiv.org/pdf' in href or '.pdf' in href):
                        return href
            
            return None
        except Exception as e:
            self.log(f"Google Scholar搜索失败: {e}")
            return None
    
    def search_regular_google(self, query):
        """使用常规Google搜索（不推荐，容易被封）"""
        try:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}+filetype:pdf"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(search_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                # 查找PDF链接
                for link in soup.find_all('a', href=True):
                    href = link['href']
                    if '.pdf' in href and 'webcache' not in href:
                        # 提取真实的URL
                        if href.startswith('/url?q='):
                            real_url = href.split('/url?q=')[1].split('&')[0]
                            return urllib.parse.unquote(real_url)
            return None
        except Exception as e:
            self.log(f"Google搜索失败: {e}")
            return None
    
    def find_pdf_through_search(self, paper):
        """通过搜索寻找PDF"""
        title = paper['title']
        authors = paper['authors']
        
        self.log(f"开始搜索论文: {title}")
        
        # 方法1: 搜索arXiv
        self.log("尝试在arXiv搜索...")
        arxiv_pdf = self.search_arxiv(title, authors)
        if arxiv_pdf:
            self.log(f"在arXiv找到PDF: {arxiv_pdf}")
            return arxiv_pdf
        
        # 方法2: 搜索Google Scholar (需要Selenium)
        if self.use_selenium:
            self.log("尝试在Google Scholar搜索...")
            scholar_pdf = self.search_google_scholar(paper['search_queries']['google'])
            if scholar_pdf:
                self.log(f"在Google Scholar找到PDF: {scholar_pdf}")
                return scholar_pdf
        
        # 方法3: 常规Google搜索（谨慎使用）
        self.log("尝试在Google搜索...")
        google_pdf = self.search_regular_google(paper['search_queries']['google'])
        if google_pdf:
            self.log(f"在Google找到PDF: {google_pdf}")
            return google_pdf
        
        self.log("所有搜索方法都未能找到PDF")
        return None
    
    def download_pdf(self, pdf_url, filename):
        """下载PDF文件"""
        try:
            response = requests.get(pdf_url, headers=self.headers, timeout=60, stream=True)
            if response.status_code == 200:
                # 检查内容类型是否为PDF
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' not in content_type and 'application/pdf' not in content_type:
                    # 检查文件内容
                    first_chunk = response.content[:100]
                    if b'%PDF' not in first_chunk:
                        self.log(f"URL返回的内容不是PDF: {content_type}")
                        return False
                
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True
        except Exception as e:
            self.log(f"下载失败: {e}")
        return False
    
    def clean_filename(self, filename):
        """清理文件名，移除非法字符"""
        return ''.join(c if c.isalnum() or c in (' ', '.', '_') else '_' for c in filename).strip()[:150]
    
    def download_single_paper(self, paper):
        """下载单篇论文"""
        paper_id = paper['id']
        title = paper['title']
        safe_title = self.clean_filename(title)
        pdf_filename = os.path.join(self.save_dir, "pdfs", f"{paper_id}_{safe_title}.pdf")
        
        if os.path.exists(pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'exists'
            paper['download_method'] = 'existing'
            return paper
        
        # 方法1: 原始方法（OpenReview）
        openreview_url = self.get_openreview_url(paper['paper_page_url'])
        pdf_url = self.get_pdf_url_from_openreview(openreview_url) if openreview_url else None
        
        if pdf_url and self.download_pdf(pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
            paper['download_method'] = 'openreview'
            paper['pdf_url'] = pdf_url
            return paper
        
        # 方法2: 搜索备选方案
        search_pdf_url = self.find_pdf_through_search(paper)
        if search_pdf_url and self.download_pdf(search_pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
            paper['download_method'] = 'search'
            paper['pdf_url'] = search_pdf_url
            return paper
        
        paper['download_status'] = 'failed'
        paper['download_method'] = 'none'
        return paper
    
    def download_all_papers(self, papers, max_workers=3):
        """并行下载所有论文"""
        self.log(f"开始下载 {len(papers)} 篇论文...")
        results = {'success': [], 'exists': [], 'failed': []}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_paper = {executor.submit(self.download_single_paper, paper): paper for paper in papers}
            with tqdm(total=len(papers), desc="下载进度") as pbar:
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
                        self.log(f"下载出错: {e}")
                        results['failed'].append(paper)
                    pbar.update(1)
        
        # 统计下载方法
        methods = {}
        for paper in results['success']:
            method = paper.get('download_method', 'unknown')
            methods[method] = methods.get(method, 0) + 1
        
        self.log(f"下载方法统计: {methods}")
        return results
    
    def save_metadata(self, papers, filename):
        """保存论文元数据"""
        filepath = os.path.join(self.save_dir, "metadata", filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        self.log(f"元数据已保存到: {filepath}")
    
    def run(self, event_types, max_workers=3):
        """运行下载流程

        Args:
            event_types (list): 要抓取的事件类型列表（例如 ['oral']）。
            max_workers (int): 并行下载线程数，传递给 download_all_papers。
        """
        all_papers = []
        for event_type in event_types:
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
            self.save_metadata(papers, f"{event_type}_papers.json")

        results = self.download_all_papers(all_papers, max_workers=max_workers)

        # 保存详细结果
        self.save_metadata(results['success'], "downloaded_papers.json")
        self.save_metadata(results['failed'], "failed_papers.json")

        # 生成摘要报告
        self.generate_summary_report(results)

        self.log("下载完成！")
        if self.use_selenium:
            self.close_selenium()
    
    def generate_summary_report(self, results):
        """生成下载摘要报告"""
        report = {
            'total_papers': len(results['success']) + len(results['exists']) + len(results['failed']),
            'successful_downloads': len(results['success']),
            'existing_files': len(results['exists']),
            'failed_downloads': len(results['failed']),
            'success_rate': (len(results['success']) + len(results['exists'])) / 
                           (len(results['success']) + len(results['exists']) + len(results['failed'])) * 100,
            'download_methods': {}
        }
        
        # 统计下载方法
        for paper in results['success']:
            method = paper.get('download_method', 'unknown')
            report['download_methods'][method] = report['download_methods'].get(method, 0) + 1
        
        report_file = os.path.join(self.save_dir, "download_summary.json")
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        self.log(f"下载摘要: 成功{report['successful_downloads']}篇, 已存在{report['existing_files']}篇, "
                f"失败{report['failed_downloads']}篇, 成功率{report['success_rate']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Conference Paper Downloader")
    parser.add_argument('-c', type=str, required=True, help='Conference shortname (neurips/iclr/icml/cvpr) or base URL (e.g., https://icml.cc)')
    parser.add_argument('-y', type=int, required=True, help='Year of the conference')
    parser.add_argument('--event_types', nargs='+', default=["oral"], help='Event types to download (e.g., oral, poster)')
    parser.add_argument('--use_selenium', action='store_true', help='Use Selenium for Google Scholar search')
    parser.add_argument('--max_workers', type=int, default=3, help='Maximum number of parallel downloads')
    
    args = parser.parse_args()
    
    # 允许 -c 接收简短名字或完整 URL
    shortname_map = {
        'neurips': 'https://neurips.cc',
        'iclr': 'https://iclr.cc',
        'icml': 'https://icml.cc',
        'cvpr': 'https://cvpr.thecvf.com'
    }

    conf_input = args.c.strip()
    conf_key = conf_input.lower()
    if conf_key in shortname_map:
        base_url = shortname_map[conf_key]
    elif conf_input.startswith('http://') or conf_input.startswith('https://'):
        base_url = conf_input.rstrip('/')
    else:
        # 如果用户输入像 "neurips" 或者带有年份等，尝试按短名解析
        # 取首个单词作为候选短名
        candidate = conf_key.split()[0]
        base_url = shortname_map.get(candidate, conf_input)

    downloader = ConferencePDFDownloader(
        base_url=base_url,
        year=args.y,
        save_dir=f"conference_papers_{args.y}",
        use_selenium=args.use_selenium
    )
    downloader.log(f"使用的 base_url: {base_url}")
    
    try:
        downloader.run(event_types=args.event_types, max_workers=args.max_workers)
    except KeyboardInterrupt:
        downloader.log("用户中断下载")
        if downloader.use_selenium:
            downloader.close_selenium()
    except Exception as e:
        downloader.log(f"程序异常: {e}")
        if downloader.use_selenium:
            downloader.close_selenium()


if __name__ == "__main__":
    main()