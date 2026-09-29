#!/usr/bin/env python3
"""
VoiceCloner 打包脚本
打包 docker 服务部署和 CLI 客户端所需的必要文件。
"""

import argparse
import os
import shutil
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

# VoiceCloner 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 打包清单：docker 服务部署所需文件
DOCKER_SERVICE_FILES = [
    "docker/",
    "src/",
    "config.yaml",
    "model-profiles.yaml",
    "requirements.txt",
]

# 打包清单：CLI 客户端所需文件
CLI_CLIENT_FILES = [
    "clone-voice-v4.py",
    "samples/",
    "requirements.txt",
]

# 打包清单：所有必要文件
ALL_FILES = sorted(set(DOCKER_SERVICE_FILES + CLI_CLIENT_FILES + ["tools/package.py"]))


def _collect_files(file_list: List[str]) -> List[Path]:
    """解析文件清单，返回存在的文件路径列表。"""
    collected = []
    for pattern in file_list:
        path = PROJECT_ROOT / pattern
        if path.exists():
            collected.append(path)
        else:
            print(f"  [WARN] 文件不存在，已跳过: {pattern}")
    return collected


def _tar_archive(file_paths: List[Path], output_path: Path):
    """打包为 tar.gz。"""
    with tarfile.open(str(output_path), "w:gz") as tar:
        for fp in file_paths:
            arcname = fp.relative_to(PROJECT_ROOT)
            tar.add(str(fp), arcname=str(arcname))
            print(f"  [ADD]  {arcname}")


def _zip_archive(file_paths: List[Path], output_path: Path):
    """打包为 zip。"""
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in file_paths:
            arcname = fp.relative_to(PROJECT_ROOT)
            if fp.is_dir():
                for root, dirs, files in os.walk(str(fp)):
                    for fn in files:
                        full = Path(root) / fn
                        rel = full.relative_to(PROJECT_ROOT)
                        zf.write(str(full), str(rel))
                        print(f"  [ADD]  {rel}")
            else:
                zf.write(str(fp), str(arcname))
                print(f"  [ADD]  {arcname}")


def main():
    parser = argparse.ArgumentParser(
        description="VoiceCloner 打包脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 打包所有必要文件为 zip
  python tools/package.py -o voicecloner-package.zip

  # 只打包 docker 服务文件
  python tools/package.py --docker-only -o voicecloner-docker.tar.gz

  # 只打包 CLI 客户端文件
  python tools/package.py --cli-only -o voicecloner-cli.zip
        """,
    )

    parser.add_argument(
        "-o", "--output",
        default=None,
        help="输出包路径（默认: dist/voicecloner-<timestamp>.tar.gz）",
    )
    parser.add_argument(
        "--format",
        choices=["tar.gz", "zip"],
        default="tar.gz",
        help="打包格式 (default: tar.gz)",
    )
    parser.add_argument(
        "--docker-only",
        action="store_true",
        default=False,
        help="只打包 docker 服务部署文件",
    )
    parser.add_argument(
        "--cli-only",
        action="store_true",
        default=False,
        help="只打包 CLI 客户端文件",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="仅列出要打包的文件，不实际打包",
    )

    args = parser.parse_args()

    # 确定文件清单
    if args.docker_only:
        file_list = DOCKER_SERVICE_FILES
        mode = "docker"
    elif args.cli_only:
        file_list = CLI_CLIENT_FILES
        mode = "cli"
    else:
        file_list = ALL_FILES
        mode = "full"

    file_paths = _collect_files(file_list)
    if not file_paths:
        print("错误：没有找到任何可打包的文件。")
        return 1

    print(f"\nVoiceCloner 打包工具")
    print(f"{'=' * 50}")
    print(f"  模式:     {mode}")
    print(f"  文件数:   {len(file_paths)}")

    if args.dry_run:
        print(f"\n  待打包文件清单:")
        for fp in file_paths:
            rel = fp.relative_to(PROJECT_ROOT)
            if fp.is_dir():
                count = sum(1 for _ in fp.rglob("*")) if fp.exists() else 0
                print(f"    📁 {rel}/  ({count} 个文件)")
            else:
                size = fp.stat().st_size
                print(f"    📄 {rel}  ({size:,} bytes)")
        return 0

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        dist_dir = PROJECT_ROOT / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = dist_dir / f"voicecloner-{mode}-{timestamp}.{args.format.replace('/', '.')}"

    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  打包中...")
    if args.format == "zip":
        _zip_archive(file_paths, output_path)
    else:
        _tar_archive(file_paths, output_path)

    size = output_path.stat().st_size
    print(f"\n  ✅ 打包完成: {output_path}")
    print(f"  📦 大小: {size:,} bytes ({size / 1024 / 1024:.1f} MB)")

    return 0


if __name__ == "__main__":
    exit(main())