from base import ConferencePDFDownloader
from cvpr import CVPRPDFDownloader
import argparse


def pipeline():
    print("Running default pipeline...")
    # 1. cvpr 2024
    cvpr_downloader = CVPRPDFDownloader(
        base_url="https://papers.cool/venue/CVPR.2024?group=Oral",
        save_dir="cvpr_2024_papers"
    )
    cvpr_downloader.run(event_types=["oral"], max_workers=2)
    # 2. cvpr 2025
    conf_downloader = ConferencePDFDownloader(
        base_url="https://icml.cc",
        year=2024,
        save_dir="icml_2024_papers"
    )
    conf_downloader.run(event_types=["oral"], max_workers=2)
    # 3. iclr 2024
    conf_downloader = ConferencePDFDownloader(
        base_url="https://iclr.cc",
        year=2024,
        save_dir="iclr_2024_papers"
    )
    conf_downloader.run(event_types=["oral"], max_workers=2)
    # 4. icml 2025
    conf_downloader = ConferencePDFDownloader(
        base_url="https://icml.cc",
        year=2025,
        save_dir="icml_2025_papers"
    )
    conf_downloader.run(event_types=["oral"], max_workers=2)
    # 5. neurips 2023
    conf_downloader = ConferencePDFDownloader(
        base_url="https://neurips.cc",
        year=2023,
        save_dir="neurips_2023_papers"
    )
    conf_downloader.run(event_types=["oral"], max_workers=2)
    # 6. neurips 2024
    conf_downloader = ConferencePDFDownloader(
        base_url="https://neurips.cc",
        year=2024,
        save_dir="neurips_2024_papers"
    )
    conf_downloader.run(event_types=["oral"], max_workers=2)


def main():
    parser = argparse.ArgumentParser(description="Conference Paper Downloader")
    parser.add_argument('-c', type=str, required=True, help='Conference shortname (neurips/iclr/icml) or base URL (e.g., https://icml.cc)')
    parser.add_argument('-y', type=int, required=True, help='Year of the conference')
    parser.add_argument('--event_types', nargs='+', default=["oral"], help='Event types to download (e.g., oral, poster)')
    parser.add_argument('--max_workers', type=int, default=2, help='Maximum number of parallel downloads (建议1-2)')
    
    args = parser.parse_args()

    if args.c is None and args.y is None:
        pipeline()
        return
        
    # 根据会议类型选择下载器
    if args.c == 'cvpr':
        base_url = f"https://papers.cool/venue/CVPR.{args.y}?group=Oral"

        downloader = CVPRPDFDownloader(
            base_url=base_url,
            save_dir=f"cvpr_{args.y}_papers"
        )
    else:
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