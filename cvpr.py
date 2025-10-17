import os
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import argparse
from datetime import datetime
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


class CVPRPDFDownloader:
    def __init__(self, base_url, save_dir="cvpr_papers", use_selenium=True):
        self.base_url = base_url.rstrip("/")
        self.save_dir = save_dir
        self.use_selenium = use_selenium
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 创建保存目录
        os.makedirs(self.save_dir, exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "pdfs"), exist_ok=True)
        os.makedirs(os.path.join(self.save_dir, "metadata"), exist_ok=True)

        # 日志文件
        self.log_file = os.path.join(self.save_dir, "download_log.txt")
        
        # 初始化Selenium驱动（如果需要）
        self.driver = None
        if self.use_selenium:
            self.setup_selenium()

    def setup_selenium(self):
        """设置Selenium WebDriver"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # 无头模式
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.log("Selenium WebDriver initialized successfully")
        except Exception as e:
            self.log(f"Failed to initialize Selenium: {e}")
            self.log("Falling back to requests only (may not get all papers)")
            self.use_selenium = False

    def close_selenium(self):
        """关闭Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            self.log("Selenium WebDriver closed")

    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        print(log_message)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_message + '\n')

    def fetch_paper_list_selenium(self):
        """使用Selenium获取所有论文（包括动态加载的）"""
        self.log("Using Selenium to fetch all papers with dynamic loading...")
        
        try:
            self.driver.get(self.base_url)
            time.sleep(3)  # 初始加载等待
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            scroll_attempts = 0
            max_attempts = 10  # 最大滚动尝试次数
            
            while scroll_attempts < max_attempts:
                # 滚动到底部
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)  # 等待新内容加载
                
                # 检查是否有"加载更多"按钮并点击
                try:
                    load_more_buttons = self.driver.find_elements(By.XPATH, "//button[contains(text(), 'Load More') or contains(text(), 'Show More')]")
                    for button in load_more_buttons:
                        if button.is_displayed():
                            button.click()
                            self.log("Clicked 'Load More' button")
                            time.sleep(2)
                except:
                    pass
                
                # 检查是否有"下一页"按钮并点击
                try:
                    next_buttons = self.driver.find_elements(By.XPATH, "//a[contains(text(), 'Next') or contains(@class, 'next')]")
                    for button in next_buttons:
                        if button.is_displayed():
                            button.click()
                            self.log("Clicked 'Next' button")
                            time.sleep(3)
                except:
                    pass
                
                # 检查是否到达页面底部
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    scroll_attempts += 1
                    self.log(f"No new content loaded, attempt {scroll_attempts}/{max_attempts}")
                else:
                    scroll_attempts = 0  # 重置计数器
                    self.log(f"New content loaded, page height: {new_height}")
                
                last_height = new_height
                
                # 检查是否找到论文元素
                paper_divs = self.driver.find_elements(By.CSS_SELECTOR, "div.panel.paper")
                self.log(f"Currently found {len(paper_divs)} papers")
                
                if scroll_attempts >= 3:  # 连续3次没有新内容，认为加载完成
                    self.log("No more content to load, stopping scroll")
                    break
            
            # 解析页面内容
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            return self.parse_paper_list(soup)
            
        except Exception as e:
            self.log(f"Error in Selenium fetching: {e}")
            return []

    def fetch_paper_list_requests(self):
        """使用requests获取论文列表（基本功能）"""
        self.log(f"Fetching paper list from {self.base_url}...")
        try:
            response = requests.get(self.base_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            return self.parse_paper_list(soup)
        except Exception as e:
            self.log(f"Failed to fetch paper list: {e}")
            return []

    def parse_paper_list(self, soup):
        """解析论文列表"""
        paper_divs = soup.find_all('div', class_='panel paper')
        papers = []

        for div in paper_divs:
            try:
                # 获取标题
                title_tag = div.find('h2', class_='title')
                if title_tag:
                    title_link = title_tag.find('a', class_='title-link')
                    title = title_link.text.strip() if title_link else title_tag.text.strip()
                else:
                    continue

                # 获取 PDF 链接
                pdf_tag = div.find('a', class_='title-pdf')
                if pdf_tag:
                    pdf_url = pdf_tag.get('href') or pdf_tag.get('data')
                    if pdf_url and not pdf_url.startswith('http'):
                        pdf_url = 'https://openaccess.thecvf.com/' + pdf_url.lstrip('/')
                else:
                    pdf_url = None

                # 获取作者信息
                author_tag = div.find('p', class_='metainfo authors')
                authors = author_tag.text.replace("Authors:", "").strip() if author_tag else "Unknown"

                # 摘要
                summary_tag = div.find('p', class_='summary')
                summary = summary_tag.text.strip() if summary_tag else "No abstract available."

                # 保存论文元数据
                papers.append({
                    'title': title,
                    'pdf_url': pdf_url,
                    'authors': authors,
                    'summary': summary
                })
            except Exception as e:
                self.log(f"Error parsing paper entry: {e}")
                continue

        self.log(f"Found {len(papers)} papers.")
        return papers

    def fetch_paper_list(self):
        """获取论文列表的主方法"""
        if self.use_selenium:
            papers = self.fetch_paper_list_selenium()
            # 如果Selenium失败，回退到requests
            if not papers:
                self.log("Selenium failed, falling back to requests")
                papers = self.fetch_paper_list_requests()
        else:
            papers = self.fetch_paper_list_requests()
        
        return papers

    def download_pdf(self, pdf_url, filename):
        """下载 PDF 文件"""
        try:
            response = requests.get(pdf_url, headers=self.headers, timeout=60, stream=True)
            response.raise_for_status()

            # 保存 PDF
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            self.log(f"Failed to download PDF from {pdf_url}: {e}")
            return False

    def clean_filename(self, filename):
        """清理文件名，移除非法字符"""
        return ''.join(c if c.isalnum() or c in (' ', '.', '_', '-') else '_' for c in filename).strip()[:150]

    def download_all_papers(self, papers):
        """下载所有论文的 PDF"""
        self.log("Starting to download PDFs...")
        results = {'success': [], 'failed': []}

        for paper in tqdm(papers, desc="Downloading PDFs"):
            title = paper['title']
            pdf_url = paper['pdf_url']
            
            if not pdf_url:
                self.log(f"No PDF URL found for paper: {title}")
                results['failed'].append(paper)
                continue

            # 安全生成文件名
            safe_title = self.clean_filename(title)
            pdf_filename = os.path.join(self.save_dir, "pdfs", f"{safe_title}.pdf")

            if os.path.exists(pdf_filename):
                self.log(f"PDF already exists: {title}")
                results['success'].append(paper)
                continue

            # 下载 PDF
            if self.download_pdf(pdf_url, pdf_filename):
                self.log(f"Successfully downloaded: {title}")
                results['success'].append(paper)
            else:
                self.log(f"Failed to download: {title}")
                results['failed'].append(paper)

        return results

    def save_metadata(self, papers, filename):
        """保存论文元数据"""
        filepath = os.path.join(self.save_dir, "metadata", filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(papers, f, ensure_ascii=False, indent=2)
            self.log(f"Metadata saved to {filepath}")
        except Exception as e:
            self.log(f"Failed to save metadata: {e}")

    def run(self):
        """运行下载器"""
        try:
            papers = self.fetch_paper_list()
            if not papers:
                self.log("No papers found. Exiting...")
                return

            # 保存论文元数据
            self.save_metadata(papers, "papers_metadata.json")
            
            # 下载所有论文
            results = self.download_all_papers(papers)

            # 保存下载结果
            if results['success']:
                self.save_metadata(results['success'], "downloaded_papers.json")
            if results['failed']:
                self.save_metadata(results['failed'], "failed_papers.json")

            # 打印统计信息
            self.log(f"Download completed! Success: {len(results['success'])}, Failed: {len(results['failed'])}")
        
        finally:
            # 确保关闭Selenium驱动
            if self.use_selenium:
                self.close_selenium()


def main():
    parser = argparse.ArgumentParser(description="CVPR PDF Downloader")
    parser.add_argument('-y', type=int, default=2024, help="CVPR年份 (默认: 2024)")
    args = parser.parse_args()

    base_url = f"https://papers.cool/venue/CVPR.{args.y}?group=Oral"
    save_dir = f"cvpr_{args.y}_papers"

    downloader = CVPRPDFDownloader(
        base_url=base_url,
        save_dir=save_dir,
    )
    downloader.run()


if __name__ == "__main__":
    main()