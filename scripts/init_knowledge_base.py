#!/usr/bin/env python3
"""
知识库初始化脚本 — 首次运行或指南更新后执行。

功能：
1. 加载所有骨科康复指南文档（.md）到向量库
2. 加载所有评估量表（.json）到向量库
3. 验证检索功能正常

用法：
    python scripts/init_knowledge_base.py
    python scripts/init_knowledge_base.py --force  # 强制重建
"""

import os
import sys
import argparse
import logging

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.rag.vector_store import build_knowledge_base

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="初始化骨科康复知识库")
    parser.add_argument("--force", action="store_true", help="强制重建知识库（清空已有数据）")
    args = parser.parse_args()

    guidelines_dir = os.getenv("KNOWLEDGE_GUIDELINES_DIR", "./knowledge/guidelines")
    scales_dir = os.getenv("KNOWLEDGE_SCALES_DIR", "./knowledge/scales")

    # 确保路径相对于项目根目录
    if not os.path.isabs(guidelines_dir):
        guidelines_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            guidelines_dir.lstrip("./"),
        )
    if not os.path.isabs(scales_dir):
        scales_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            scales_dir.lstrip("./"),
        )

    if args.force:
        import chromadb
        import shutil
        chroma_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        if not os.path.isabs(chroma_dir):
            chroma_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                chroma_dir.lstrip("./"),
            )
        if os.path.exists(chroma_dir):
            shutil.rmtree(chroma_dir)
            logger.info("已清空旧向量库: %s", chroma_dir)

    logger.info("开始构建知识库...")
    logger.info("  指南目录: %s", guidelines_dir)
    logger.info("  量表目录: %s", scales_dir)

    store = build_knowledge_base(guidelines_dir, scales_dir)

    # 验证检索
    test_queries = [
        "TKA术后疼痛管理",
        "THA防脱位注意事项",
        "ACL重建术后多久可以跑步",
        "DVT预防措施",
    ]

    logger.info("\n知识库构建完成，执行检索验证：")
    for q in test_queries:
        results = store.search(q, n_results=3)
        logger.info(f"\n  Query: {q}")
        for r in results:
            logger.info(f"    [{r['metadata'].get('source', '?')}] {r['metadata'].get('section', '?')} (distance={r.get('distance', '?')})")
        if not results:
            logger.warning(f"    ⚠️ 无结果！")

    logger.info("\n✅ 知识库初始化完成")


if __name__ == "__main__":
    main()
