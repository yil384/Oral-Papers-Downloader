import requests
from bs4 import BeautifulSoup
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
import argparse


class ConferencePDFDownloader:
    def __init__(self, base_url, year, save_dir="conference_papers"):
        self.base_url = base_url.rstrip("/")  # 确保没有尾部斜杠
        self.year = year
        self.save_dir = f"{save_dir}_{year}"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 创建保存目录
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "pdfs"), exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "metadata"), exist_ok=True)
        
        # 日志文件
        self.log_file = os.path.join(self.save_dir, "download_log.txt")
        
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
                        'year': self.year
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
    
    def download_pdf(self, pdf_url, filename):
        """下载PDF文件"""
        try:
            response = requests.get(pdf_url, headers=self.headers, timeout=60, stream=True)
            if response.status_code == 200:
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
            return paper
        
        openreview_url = self.get_openreview_url(paper['paper_page_url'])
        if not openreview_url:
            paper['download_status'] = 'no_openreview'
            return paper
        
        pdf_url = self.get_pdf_url_from_openreview(openreview_url)
        if not pdf_url:
            paper['download_status'] = 'no_pdf_url'
            return paper
        
        if self.download_pdf(pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
        else:
            paper['download_status'] = 'failed'
        
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
        return results
    
    def save_metadata(self, papers, filename):
        """保存论文元数据"""
        filepath = os.path.join(self.save_dir, "metadata", filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        self.log(f"元数据已保存到: {filepath}")
    
    def run(self, event_types):
        """运行下载流程"""
        all_papers = []
        for event_type in event_types:
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
            self.save_metadata(papers, f"{event_type}_papers.json")
        
        results = self.download_all_papers(all_papers)
        self.save_metadata(results['success'], "downloaded_papers.json")
        self.save_metadata(results['failed'], "failed_papers.json")
        self.log("下载完成！")


def main():
    parser = argparse.ArgumentParser(description="Conference Paper Downloader")
    parser.add_argument('--base_url', type=str, required=True, help='Base URL of the conference (e.g., https://icml.cc)')
    parser.add_argument('--year', type=int, required=True, help='Year of the conference')
    parser.add_argument('--event_types', nargs='+', default=["oral"], help='Event types to download (e.g., oral, poster)')
    args = parser.parse_args()
    
    # TODO: Fixme
    downloader = ConferencePDFDownloader(
        base_url=args.base_url, 
        year=args.year,
        save_dir=f"conference_papers_{args.year}"
    )
    downloader.run(event_types=args.event_types)


if __name__ == "__main__":
    main()