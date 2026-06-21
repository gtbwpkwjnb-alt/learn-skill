"""抖音/TikTok 视频提取 → Markdown 一条龙
用法: python douyin2md.py <视频链接> [--frames] [--out 输出目录]
"""
import sys
from pathlib import Path

# 确保 tiktok_extractor 包可导入
sys.path.insert(0, str(Path(__file__).parent / "tiktok-extractor"))

from tiktok_extractor.pipeline import run_pipeline
from tiktok_extractor.downloader import DownloadError
from tiktok_extractor.preflight import MissingDependencyError


def main():
    if len(sys.argv) < 2:
        print("用法: python douyin2md.py <视频链接> [--frames] [--out 输出目录]")
        print("示例: python douyin2md.py https://v.douyin.com/xxx/")
        print("      python douyin2md.py https://v.douyin.com/xxx/ --frames --out ./output")
        sys.exit(1)

    url = sys.argv[1]
    with_frames = "--frames" in sys.argv
    
    # 找 --out 参数
    out_dir = Path("output")
    if "--out" in sys.argv:
        idx = sys.argv.index("--out")
        if idx + 1 < len(sys.argv):
            out_dir = Path(sys.argv[idx + 1])

    try:
        summary_path = run_pipeline(url, out_dir, with_frames=with_frames)
    except MissingDependencyError as e:
        print(f"缺少依赖: {e}", file=sys.stderr)
        sys.exit(1)
    except DownloadError as e:
        print(f"下载失败: {e}", file=sys.stderr)
        sys.exit(2)

    print(f"✅ 完成 → {summary_path}")


if __name__ == "__main__":
    main()
