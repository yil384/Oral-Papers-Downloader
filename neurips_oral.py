import requests
from bs4 import BeautifulSoup
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import argparse

class NeurIPSPaperDownloader:
    def __init__(self, year=2025, save_dir="neurips_papers"):
        self.base_url = "https://neurips.cc"
        self.year = year
        self.save_dir = save_dir
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 创建保存目录
        os.makedirs(save_dir, exist_ok=True)
        os.makedirs(os.path.join(save_dir, "pdfs"), exist_ok=True)
        
    def get_paper_list(self, event_type="oral"):
        """获取论文列表"""
        page_url = f"{self.base_url}/virtual/{self.year}/events/{event_type}"
        print(f"正在获取论文列表: {page_url}")
        
        response = requests.get(page_url, headers=self.headers)
        if response.status_code != 200:
            print(f"获取页面失败: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        paper_divs = soup.find_all('div', class_='virtual-card')
        
        papers = []
        for div in paper_divs:
            try:
                link = div.find('a', class_='small-title text-underline-hover')
                if not link:
                    continue
                
                title = link.text.strip()
                relative_url = link.get('href', '')
                paper_url = self.base_url + relative_url if relative_url else ""
                
                # 获取论文ID（从URL中提取）
                paper_id = relative_url.split('/')[-1] if relative_url else ""
                
                # 获取作者信息
                authors = ""
                author_div = div.find_next_sibling('div', class_='author-str')
                if author_div:
                    authors = author_div.text.strip().replace(' · ', '; ')
                
                papers.append({
                    'id': paper_id,
                    'title': title,
                    'paper_page_url': paper_url,
                    'authors': authors,
                    'event_type': event_type
                })
                
            except Exception as e:
                print(f"解析论文信息出错: {e}")
                continue
        
        print(f"找到 {len(papers)} 篇论文")
        return papers
    
    def get_openreview_url(self, paper_page_url):
        """从论文页面获取OpenReview链接"""
        try:
            response = requests.get(paper_page_url, headers=self.headers)
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找OpenReview链接
            openreview_link = soup.find('a', {'title': 'OpenReview'})
            if openreview_link:
                return openreview_link.get('href')
            
            # 备选方法：查找包含openreview.net的链接
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                if 'openreview.net/forum' in link['href']:
                    return link['href']
            
            return None
        except Exception as e:
            print(f"获取OpenReview链接失败: {e}")
            return None
    
    def get_pdf_url_from_openreview(self, openreview_url):
        """将OpenReview forum链接转换为PDF链接"""
        if not openreview_url:
            return None
        
        # 提取ID参数
        if 'forum?id=' in openreview_url:
            paper_id = openreview_url.split('forum?id=')[1].split('&')[0]
            pdf_url = f"https://openreview.net/pdf?id={paper_id}"
            return pdf_url
        
        return None
    
    def download_pdf(self, pdf_url, filename, max_retries=3):
        """下载PDF文件"""
        if not pdf_url:
            return False
        
        for attempt in range(max_retries):
            try:
                response = requests.get(pdf_url, headers=self.headers, timeout=30, stream=True)
                if response.status_code == 200:
                    with open(filename, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    return True
                elif response.status_code == 404:
                    print(f"PDF不存在: {pdf_url}")
                    return False
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                print(f"下载失败: {e}")
                return False
        
        return False
    
    def clean_filename(self, filename):
        """清理文件名，移除非法字符"""
        # 移除或替换Windows文件名中的非法字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        # 限制文件名长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename.strip()
    
    def download_single_paper(self, paper):
        """下载单篇论文"""
        paper_id = paper['id']
        title = paper['title']
        
        # 生成安全的文件名
        safe_title = self.clean_filename(title)
        pdf_filename = os.path.join(self.save_dir, "pdfs", f"{paper_id}_{safe_title}.pdf")
        
        # 如果文件已存在，跳过
        if os.path.exists(pdf_filename):
            return {'status': 'exists', 'paper': paper}
        
        # 获取OpenReview链接
        openreview_url = self.get_openreview_url(paper['paper_page_url'])
        if not openreview_url:
            return {'status': 'no_openreview', 'paper': paper}
        
        # 获取PDF链接
        pdf_url = self.get_pdf_url_from_openreview(openreview_url)
        if not pdf_url:
            return {'status': 'no_pdf_url', 'paper': paper}
        
        # 下载PDF
        paper['openreview_url'] = openreview_url
        paper['pdf_url'] = pdf_url
        
        if self.download_pdf(pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            return {'status': 'success', 'paper': paper}
        else:
            return {'status': 'download_failed', 'paper': paper}
    
    def download_all_papers(self, papers, max_workers=5):
        """并行下载所有论文"""
        print(f"\n开始下载 {len(papers)} 篇论文的PDF...")
        
        results = {
            'success': [],
            'exists': [],
            'failed': []
        }
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有下载任务
            future_to_paper = {
                executor.submit(self.download_single_paper, paper): paper 
                for paper in papers
            }
            
            # 使用tqdm显示进度条
            with tqdm(total=len(papers), desc="下载进度") as pbar:
                for future in as_completed(future_to_paper):
                    result = future.result()
                    status = result['status']
                    paper = result['paper']
                    
                    if status == 'success':
                        results['success'].append(paper)
                        tqdm.write(f"✅ 下载成功: {paper['title'][:50]}...")
                    elif status == 'exists':
                        results['exists'].append(paper)
                        tqdm.write(f"⏭️  已存在: {paper['title'][:50]}...")
                    else:
                        results['failed'].append(paper)
                        tqdm.write(f"❌ 下载失败 ({status}): {paper['title'][:50]}...")
                    
                    pbar.update(1)
                    time.sleep(0.5)  # 避免请求过快
        
        return results
    
    def save_metadata(self, papers, filename="paper_metadata.json"):
        """保存论文元数据"""
        filepath = os.path.join(self.save_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        print(f"元数据已保存到: {filepath}")
    
    def run(self, event_types=None):
        """运行完整的下载流程"""
        if event_types is None:
            event_types = ["oral"]  # 默认只下载oral论文
        
        all_papers = []
        
        # 获取所有类型的论文
        for event_type in event_types:
            print(f"\n获取 {event_type} 论文...")
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
        
        if not all_papers:
            print("没有找到论文")
            return
        
        print(f"\n总共找到 {len(all_papers)} 篇论文")
        
        # 下载所有论文
        results = self.download_all_papers(all_papers, max_workers=3)
        
        # 保存元数据
        self.save_metadata(results['success'] + results['exists'], "downloaded_papers.json")
        if results['failed']:
            self.save_metadata(results['failed'], "failed_papers.json")
        
        # 打印统计信息
        print("\n" + "="*50)
        print("下载统计:")
        print(f"✅ 成功下载: {len(results['success'])} 篇")
        print(f"⏭️  已存在: {len(results['exists'])} 篇")
        print(f"❌ 下载失败: {len(results['failed'])} 篇")
        print(f"📁 PDF保存位置: {os.path.join(self.save_dir, 'pdfs')}")
        print("="*50)

def main():
    parser = argparse.ArgumentParser(description="NeurIPS paper downloader")
    parser.add_argument('--year', type=int, default=2024, help='Year of the NeurIPS conference (default: 2024)')
    args = parser.parse_args()

    # 创建下载器实例
    downloader = NeurIPSPaperDownloader(
        year=args.year,
        save_dir=f"neurips_{args.year}_papers"
    )
    
    # 运行下载
    # 可以指定要下载的论文类型：["oral", "poster", "spotlight"]
    downloader.run(event_types=["oral"])
    
    # 如果要下载所有类型的论文：
    # downloader.run(event_types=["oral", "poster", "spotlight"])

if __name__ == "__main__":
    main()