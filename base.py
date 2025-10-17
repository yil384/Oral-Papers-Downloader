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
        self.base_url = base_url.rstrip("/")  # 确保没有尾部斜杠
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
        
        # arXiv搜索相关设置
        self.arxiv_last_request_time = 0
        self.arxiv_request_interval = 5  # 增加到5秒间隔
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
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
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
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
            response = self.session.get(page_url, timeout=30)
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
    
    def wait_for_arxiv_rate_limit(self):
        """等待arXiv API速率限制"""
        current_time = time.time()
        time_since_last_request = current_time - self.arxiv_last_request_time
        if time_since_last_request < self.arxiv_request_interval:
            sleep_time = self.arxiv_request_interval - time_since_last_request
            time.sleep(sleep_time + random.uniform(1.0, 3.0))  # 增加随机延迟
        self.arxiv_last_request_time = time.time()
    
    def search_arxiv(self, title, authors):
        """在arXiv搜索论文 - 改进的模糊匹配版本"""
        try:
            # 遵守arXiv API速率限制
            self.wait_for_arxiv_rate_limit()
            
            # 清理标题，移除特殊字符和常见会议名称
            clean_title = re.sub(r'[^\w\s]', ' ', title)
            # 移除常见的会议相关词汇以减少噪音
            conference_words = ['neurips', 'icml', 'iclr', 'cvpr', 'eccv', 'aaai', 'ijcai', 'acl', 'emnlp', 'naacl', 'conference', 'proceedings', 'workshop']
            for word in conference_words:
                clean_title = re.sub(r'\b' + word + r'\b', '', clean_title, flags=re.IGNORECASE)
            
            clean_title = re.sub(r'\s+', ' ', clean_title).strip()
            
            if not clean_title:
                return None
            
            # 使用多种搜索策略
            search_strategies = [
                f'ti:"{clean_title}"',  # 精确标题搜索
                f'all:"{clean_title}"',  # 全文搜索
            ]
            
            # 如果标题太长，使用关键词
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
                        # 检查是否返回了HTML（被屏蔽）
                        if 'html' in response.headers.get('content-type', '').lower():
                            self.log("arXiv返回HTML页面，可能被屏蔽，跳过此次搜索")
                            continue
                            
                        soup = BeautifulSoup(response.content, 'xml')
                        entries = soup.find_all('entry')
                        
                        best_match = None
                        best_score = 0
                        
                        for entry in entries:
                            entry_title = entry.find('title').text.strip() if entry.find('title') else ""
                            entry_authors = [author.find('name').text.strip() if author.find('name') else "" 
                                           for author in entry.find_all('author')]
                            
                            # 计算综合匹配分数
                            title_score = self.title_similarity(clean_title, entry_title)
                            author_score = self.author_similarity(authors, ' '.join(entry_authors))
                            
                            # 综合评分，标题匹配更重要
                            total_score = title_score * 0.7 + author_score * 0.3
                            
                            if total_score > best_score and total_score > 0.4:  # 设置匹配阈值
                                best_score = total_score
                                pdf_link = entry.find('link', title='pdf')
                                if pdf_link and pdf_link.get('href'):
                                    best_match = pdf_link.get('href')
                        
                        if best_match:
                            self.log(f"arXiv找到匹配 (分数: {best_score:.2f}): {best_match}")
                            return best_match
                            
                except Exception as e:
                    self.log(f"arXiv搜索策略失败 {search_query}: {e}")
                    continue
            
            return None
            
        except Exception as e:
            self.log(f"arXiv搜索失败: {e}")
            return None
    
    def extract_important_words(self, text):
        """提取标题中的重要词汇"""
        # 移除停用词
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being'}
        words = text.lower().split()
        important_words = [word for word in words if word not in stop_words and len(word) > 3]
        
        # 返回前3-5个重要词汇
        return important_words[:4]
    
    def title_similarity(self, title1, title2):
        """改进的标题相似度计算"""
        if not title1 or not title2:
            return 0
            
        # 预处理标题
        t1 = re.sub(r'[^\w\s]', ' ', title1.lower())
        t2 = re.sub(r'[^\w\s]', ' ', title2.lower())
        
        words1 = set(t1.split())
        words2 = set(t2.split())
        
        if not words1 or not words2:
            return 0
        
        # Jaccard相似度
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        jaccard_sim = len(intersection) / len(union)
        
        # 序列相似度（考虑单词顺序）
        seq1 = t1.split()
        seq2 = t2.split()
        seq_sim = self.sequence_similarity(seq1, seq2)
        
        # 综合评分
        return jaccard_sim * 0.6 + seq_sim * 0.4
    
    def sequence_similarity(self, seq1, seq2):
        """计算序列相似度"""
        if not seq1 or not seq2:
            return 0
            
        # 简单的序列匹配：计算最长公共子序列的比例
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
        """作者相似度计算"""
        if not authors1 or not authors2:
            return 0
            
        # 提取姓氏进行比较
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
        """通过搜索寻找PDF - 现在只使用arXiv"""
        title = paper['title']
        authors = paper['authors']
        
        self.log(f"开始在arXiv搜索论文: {title}")
        
        # 只在arXiv搜索
        arxiv_pdf = self.search_arxiv(title, authors)
        if arxiv_pdf:
            self.log(f"在arXiv找到PDF: {arxiv_pdf}")
            return arxiv_pdf
        
        self.log("arXiv搜索未能找到PDF")
        return None
    
    def download_pdf(self, pdf_url, filename):
        """下载PDF文件 - 改进版本，处理反爬虫"""
        try:
            # 对于arXiv URL，添加随机延迟
            if 'arxiv.org' in pdf_url:
                time.sleep(random.uniform(2.0, 5.0))
            
            # 使用session保持连接
            response = self.session.get(pdf_url, timeout=60, stream=True)
            
            if response.status_code == 200:
                # 检查内容类型
                content_type = response.headers.get('content-type', '').lower()
                
                # 如果返回的是HTML，说明被屏蔽了
                if 'text/html' in content_type:
                    self.log(f"被反爬虫屏蔽，返回HTML页面: {pdf_url}")
                    return False
                
                # 检查文件内容是否为PDF
                first_chunk = response.content[:100]
                if b'%PDF' not in first_chunk:
                    self.log(f"URL返回的内容不是PDF，内容类型: {content_type}")
                    # 检查是否是错误页面
                    if b'captcha' in first_chunk.lower() or b'robot' in first_chunk.lower():
                        self.log("检测到验证码页面，被反爬虫机制阻止")
                    return False
                
                # 保存PDF文件
                with open(filename, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # 验证文件大小
                file_size = os.path.getsize(filename)
                if file_size < 1024:  # 小于1KB可能是错误页面
                    self.log(f"下载的文件过小 ({file_size} bytes)，可能是错误页面")
                    os.remove(filename)
                    return False
                
                self.log(f"PDF下载成功: {filename} ({file_size} bytes)")
                return True
            else:
                self.log(f"下载失败，状态码: {response.status_code}")
                return False
                
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
        
        # 方法2: 只在arXiv搜索
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
    
    def download_all_papers(self, papers, max_workers=2):  # 减少并发数
        """并行下载所有论文"""
        self.log(f"开始下载 {len(papers)} 篇论文...")
        results = {'success': [], 'exists': [], 'failed': []}
        
        # 限制并发数，避免触发反爬虫
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
    
    def run(self, event_types, max_workers=2):  # 默认并发数减少到2
        """运行下载流程"""
        all_papers = []
        for event_type in event_types:
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
            self.save_metadata(papers, f"{event_type}_papers.json")

        results = self.download_all_papers(all_papers, max_workers=max_workers)

        # 保存详细结果，成功和已存在的合并保存
        combined_success = results['success'] + results['exists']
        self.save_metadata(combined_success, "downloaded_papers.json")
        # self.save_metadata(results['success'], "downloaded_papers.json")
        self.save_metadata(results['failed'], "failed_papers.json")

        # 生成摘要报告
        self.generate_summary_report(results)

        self.log("下载完成！")
        if self.use_selenium:
            self.close_selenium()
    
    def generate_summary_report(self, results):
        """生成下载摘要报告"""
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
    parser.add_argument('-c', type=str, required=True, help='Conference shortname (neurips/iclr/icml) or base URL (e.g., https://icml.cc)')
    parser.add_argument('-y', type=int, required=True, help='Year of the conference')
    parser.add_argument('--event_types', nargs='+', default=["oral"], help='Event types to download (e.g., oral, poster)')
    parser.add_argument('--max_workers', type=int, default=2, help='Maximum number of parallel downloads (建议1-2)')
    
    args = parser.parse_args()
    
    # 允许 -c 接收简短名字或完整 URL
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
        # 如果用户输入像 "neurips" 或者带有年份等，尝试按短名解析
        # 取首个单词作为候选短名
        candidate = conf_key.split()[0]
        base_url = shortname_map.get(candidate, conf_input)

    downloader = ConferencePDFDownloader(
        base_url=base_url,
        year=args.y,
        save_dir=f"{conf_key}_{args.y}_papers"
    )
    downloader.log(f"使用的 base_url: {base_url}")
    
    try:
        downloader.run(event_types=args.event_types, max_workers=args.max_workers)
    except KeyboardInterrupt:
        downloader.log("用户中断下载")
    except Exception as e:
        downloader.log(f"程序异常: {e}")


if __name__ == "__main__":
    main()