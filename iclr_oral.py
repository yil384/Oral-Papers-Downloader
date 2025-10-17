import requests
from bs4 import BeautifulSoup
import time
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
import argparse

class ICLRPaperDownloader:
    def __init__(self, year=2025, save_dir="iclr_papers"):
        self.base_url = "https://iclr.cc"
        self.year = year
        self.save_dir = f"{save_dir}_{year}"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
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
        """获取ICLR论文列表"""
        page_url = f"{self.base_url}/virtual/{self.year}/events/{event_type}"
        self.log(f"获取论文列表: {page_url}")
        
        try:
            response = requests.get(page_url, headers=self.headers, timeout=30)
            if response.status_code != 200:
                self.log(f"获取页面失败: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有论文卡片
            paper_divs = soup.find_all('div', class_='virtual-card')
            papers = []
            
            for idx, div in enumerate(paper_divs):
                try:
                    # 获取标题和链接
                    link = div.find('a', class_='small-title text-underline-hover')
                    if not link:
                        continue
                    
                    title = link.text.strip()
                    relative_url = link.get('href', '')
                    paper_url = self.base_url + relative_url if relative_url else ""
                    
                    # 提取论文ID
                    paper_id = relative_url.split('/')[-1] if relative_url else str(idx)
                    
                    # 获取论文类型
                    paper_type = event_type.upper()
                    type_div = div.find_next_sibling('div', class_='type_display_name_virtual_card')
                    if type_div:
                        paper_type = type_div.text.strip()
                    
                    # 获取作者信息
                    authors = ""
                    author_div = div.find_next_sibling('div', class_='author-str')
                    if author_div:
                        authors = author_div.text.strip()
                        # 清理作者名中的特殊字符
                        authors = authors.replace(' · ', '; ').replace('&middot;', ';')
                    
                    # 获取摘要
                    abstract = ""
                    details = div.find_next_sibling('details')
                    if not details:
                        # 尝试查找后续的details标签
                        for sibling in div.find_next_siblings():
                            if sibling.name == 'details':
                                details = sibling
                                break
                            elif sibling.name == 'div' and 'virtual-card' in sibling.get('class', []):
                                break
                    
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
                        'type': paper_type,
                        'event_type': event_type,
                        'year': self.year
                    })
                    
                except Exception as e:
                    self.log(f"解析论文信息出错: {e}")
                    continue
            
            self.log(f"找到 {len(papers)} 篇 {event_type} 论文")
            return papers
            
        except Exception as e:
            self.log(f"获取论文列表失败: {e}")
            return []
    
    def get_openreview_url(self, paper_page_url, max_retries=3):
        """从ICLR论文页面获取OpenReview链接"""
        for attempt in range(max_retries):
            try:
                response = requests.get(paper_page_url, headers=self.headers, timeout=30)
                if response.status_code != 200:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return None
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找OpenReview链接 - 多种方式
                # 方式1: 通过title属性
                openreview_link = soup.find('a', {'title': 'OpenReview'})
                if openreview_link:
                    return openreview_link.get('href')
                
                # 方式2: 通过链接文本
                for link in soup.find_all('a'):
                    if 'OpenReview' in link.text:
                        href = link.get('href', '')
                        if 'openreview.net' in href:
                            return href
                
                # 方式3: 直接查找包含openreview.net的链接
                for link in soup.find_all('a', href=True):
                    if 'openreview.net/forum' in link['href']:
                        return link['href']
                
                return None
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                self.log(f"获取OpenReview链接失败: {e}")
                return None
        
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
    
    def clean_filename(self, filename):
        """清理文件名，移除非法字符"""
        # 移除或替换文件名中的非法字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*', '\n', '\r', '\t']
        for char in illegal_chars:
            filename = filename.replace(char, '_')
        
        # 移除多余的空格
        filename = ' '.join(filename.split())
        
        # 限制文件名长度
        if len(filename) > 150:
            filename = filename[:150]
        
        return filename.strip()
    
    def download_pdf(self, pdf_url, filename, max_retries=3):
        """下载PDF文件"""
        if not pdf_url:
            return False
        
        for attempt in range(max_retries):
            try:
                response = requests.get(pdf_url, headers=self.headers, timeout=60, stream=True)
                if response.status_code == 200:
                    # 检查内容类型
                    content_type = response.headers.get('content-type', '')
                    if 'pdf' not in content_type.lower() and 'octet-stream' not in content_type.lower():
                        self.log(f"警告: 内容类型不是PDF: {content_type}")
                    
                    # 下载文件
                    total_size = int(response.headers.get('content-length', 0))
                    with open(filename, 'wb') as f:
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                    
                    # 验证文件大小
                    if os.path.getsize(filename) < 1000:  # 小于1KB可能是错误
                        os.remove(filename)
                        return False
                    
                    return True
                elif response.status_code == 404:
                    return False
                else:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                self.log(f"下载失败: {e}")
        
        return False
    
    def download_single_paper(self, paper):
        """下载单篇论文"""
        paper_id = paper['id']
        title = paper['title']
        
        # 生成安全的文件名
        safe_title = self.clean_filename(title)
        pdf_filename = os.path.join(self.save_dir, "pdfs", f"ICLR{self.year}_{paper_id}_{safe_title}.pdf")
        
        # 如果文件已存在且大小合理，跳过
        if os.path.exists(pdf_filename) and os.path.getsize(pdf_filename) > 10000:
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'exists'
            return {'status': 'exists', 'paper': paper}
        
        # 获取OpenReview链接
        openreview_url = self.get_openreview_url(paper['paper_page_url'])
        if not openreview_url:
            paper['download_status'] = 'no_openreview'
            return {'status': 'no_openreview', 'paper': paper}
        
        # 获取PDF链接
        pdf_url = self.get_pdf_url_from_openreview(openreview_url)
        if not pdf_url:
            paper['download_status'] = 'no_pdf_url'
            return {'status': 'no_pdf_url', 'paper': paper}
        
        # 更新论文信息
        paper['openreview_url'] = openreview_url
        paper['pdf_url'] = pdf_url
        
        # 下载PDF
        if self.download_pdf(pdf_url, pdf_filename):
            paper['local_pdf_path'] = pdf_filename
            paper['download_status'] = 'success'
            paper['file_size'] = os.path.getsize(pdf_filename)
            return {'status': 'success', 'paper': paper}
        else:
            paper['download_status'] = 'download_failed'
            return {'status': 'download_failed', 'paper': paper}
    
    def download_all_papers(self, papers, max_workers=3):
        """并行下载所有论文"""
        self.log(f"开始下载 {len(papers)} 篇论文的PDF...")
        
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
                    try:
                        result = future.result()
                        status = result['status']
                        paper = result['paper']
                        
                        if status == 'success':
                            results['success'].append(paper)
                            tqdm.write(f"✅ 下载成功: {paper['title'][:60]}...")
                        elif status == 'exists':
                            results['exists'].append(paper)
                            tqdm.write(f"⏭️  已存在: {paper['title'][:60]}...")
                        else:
                            results['failed'].append(paper)
                            tqdm.write(f"❌ 失败({status}): {paper['title'][:60]}...")
                        
                        pbar.update(1)
                        time.sleep(1)  # 避免请求过快
                        
                    except Exception as e:
                        self.log(f"处理下载结果时出错: {e}")
                        pbar.update(1)
        
        return results
    
    def save_metadata(self, papers, filename):
        """保存论文元数据"""
        filepath = os.path.join(self.save_dir, "metadata", filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
        self.log(f"元数据已保存到: {filepath}")
    
    def generate_report(self, results):
        """生成下载报告"""
        report_file = os.path.join(self.save_dir, "download_report.md")
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"# ICLR {self.year} Papers Download Report\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # 统计信息
            f.write("## 📊 统计信息\n\n")
            f.write(f"- ✅ 成功下载: {len(results['success'])} 篇\n")
            f.write(f"- ⏭️  已存在: {len(results['exists'])} 篇\n")
            f.write(f"- ❌ 下载失败: {len(results['failed'])} 篇\n")
            f.write(f"- 📁 总计: {len(results['success']) + len(results['exists']) + len(results['failed'])} 篇\n\n")
            
            # 成功下载的论文列表
            if results['success']:
                f.write("## ✅ 成功下载的论文\n\n")
                for i, paper in enumerate(results['success'], 1):
                    f.write(f"{i}. **{paper['title']}**\n")
                    f.write(f"   - 作者: {paper.get('authors', 'N/A')}\n")
                    f.write(f"   - OpenReview: [{paper.get('openreview_url', 'N/A')}]({paper.get('openreview_url', '#')})\n")
                    f.write(f"   - 文件大小: {paper.get('file_size', 0) / 1024 / 1024:.2f} MB\n\n")
            
            # 失败的论文列表
            if results['failed']:
                f.write("## ❌ 下载失败的论文\n\n")
                for i, paper in enumerate(results['failed'], 1):
                    f.write(f"{i}. **{paper['title']}**\n")
                    f.write(f"   - 失败原因: {paper.get('download_status', 'unknown')}\n")
                    f.write(f"   - 论文页面: [{paper['paper_page_url']}]({paper['paper_page_url']})\n\n")
        
        self.log(f"下载报告已生成: {report_file}")
    
    def run(self, event_types=None):
        """运行完整的下载流程"""
        if event_types is None:
            event_types = ["oral"]  # 默认只下载oral论文
        
        self.log("="*60)
        self.log(f"ICLR {self.year} 论文下载器启动")
        self.log("="*60)
        
        all_papers = []
        
        # 获取所有类型的论文
        for event_type in event_types:
            self.log(f"\n获取 {event_type} 论文列表...")
            papers = self.get_paper_list(event_type)
            all_papers.extend(papers)
            
            # 保存每种类型的论文列表
            if papers:
                self.save_metadata(papers, f"iclr_{self.year}_{event_type}_list.json")
        
        if not all_papers:
            self.log("没有找到任何论文")
            return
        
        self.log(f"\n总共找到 {len(all_papers)} 篇论文")
        
        # 保存完整的论文列表
        self.save_metadata(all_papers, f"iclr_{self.year}_all_papers_list.json")
        
        # 下载所有论文
        results = self.download_all_papers(all_papers, max_workers=3)
        
        # 保存下载结果
        if results['success']:
            self.save_metadata(results['success'], f"iclr_{self.year}_downloaded.json")
        if results['failed']:
            self.save_metadata(results['failed'], f"iclr_{self.year}_failed.json")
        
        # 生成报告
        self.generate_report(results)
        
        # 打印最终统计
        self.log("\n" + "="*60)
        self.log("下载完成！统计信息：")
        self.log(f"✅ 成功下载: {len(results['success'])} 篇")
        self.log(f"⏭️  已存在: {len(results['exists'])} 篇")
        self.log(f"❌ 下载失败: {len(results['failed'])} 篇")
        self.log(f"📁 PDF保存位置: {os.path.join(self.save_dir, 'pdfs')}")
        self.log("="*60)

def main():
    parser = argparse.ArgumentParser(description="NeurIPS paper downloader")
    parser.add_argument('--year', type=int, default=2024, help='Year of the NeurIPS conference (default: 2024)')
    args = parser.parse_args()

    # 创建ICLR下载器
    downloader = ICLRPaperDownloader(
        year=args.year,
        save_dir=f"iclr_{args.year}_papers"
    )
    
    # 下载oral论文
    downloader.run(event_types=["oral"])
    
    # 如果要下载所有类型的论文，可以使用：
    # downloader.run(event_types=["oral", "poster", "spotlight"])

if __name__ == "__main__":
    main()