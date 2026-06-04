"""
向量库封装 — ChromaDB + BGE Embedding。

修复点：
- _split_by_sections 正则在原方案中无法捕获第一个标题前的内容和末尾内容。
  这里重写为按行解析，更可靠。
- 添加 .query() 返回格式兼容不同 ChromaDB 版本的逻辑。
- 添加 load_scales() 方法，将 JSON 量表也入库。
- 改为惰性加载 embedding 模型，节省启动内存。
"""

import os
import re
import json
import glob
import logging
from typing import List, Dict, Any, Optional

import chromadb
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ChromaDB 客户端全局单例
_chroma_client: Optional[chromadb.PersistentClient] = None


def _get_chroma_client() -> chromadb.PersistentClient:
    global _chroma_client
    if _chroma_client is None:
        persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
        os.makedirs(persist_dir, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


class OrthoVectorStore:
    """骨科知识向量库，封装 ChromaDB + BGE 中文 Embedding。"""

    COLLECTION_NAME = "ortho_knowledge"

    def __init__(self):
        self.chroma_client = _get_chroma_client()
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        # Embedding API 客户端（惰性初始化）
        self._api_client: Optional[OpenAI] = None
        self._embedding_model_name: Optional[str] = None

    def _get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """通过百川 Embedding API 获取向量（兼容 OpenAI 格式）。"""
        if self._api_client is None:
            base_url = os.getenv("LLM_BASE_URL", "https://api.baichuan-ai.com/v1")
            api_key = os.getenv("LLM_API_KEY", "EMPTY")
            self._embedding_model_name = os.getenv("EMBEDDING_MODEL", "Baichuan-Text-Embedding")
            self._api_client = OpenAI(base_url=base_url, api_key=api_key)
            logger.info("Using embedding API: %s @ %s", self._embedding_model_name, base_url)

        all_embeddings = []
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._api_client.embeddings.create(
                model=self._embedding_model_name,
                input=batch,
            )
            all_embeddings.extend([r.embedding for r in resp.data])
        return all_embeddings

    # ── 文档入库 ─────────────────────────────────────────

    def add_documents(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ):
        """添加文档到向量库。返回入库数量。"""
        if not documents:
            return 0

        embeddings = self._get_embeddings(documents)
        if ids is None:
            ids = [f"doc_{i}_{abs(hash(d)) % 100000}" for i, d in enumerate(documents)]
        if metadatas is None:
            metadatas = [{}] * len(documents)

        self.collection.add(
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        logger.info("Added %d documents to vector store", len(documents))
        return len(documents)

    # ── 检索 ─────────────────────────────────────────────

    def search(self, query: str, n_results: int = 5, surgery_type: str = "") -> List[Dict[str, Any]]:
        """检索最相似的 n_results 条文档。可选按手术类型过滤。"""
        if self.collection.count() == 0:
            logger.warning("Vector store is empty, no results")
            return []

        query_embedding = self._get_embeddings([query])

        # 手术类型过滤
        where_filter = None
        if surgery_type:
            where_filter = {"surgery_type": surgery_type}

        results = self.collection.query(
            query_embeddings=query_embedding,
            n_results=min(n_results, self.collection.count()),
            where=where_filter,
        )

        documents = []
        for i in range(len(results.get("documents", [[]])[0])):
            doc_content = results["documents"][0][i]
            metadata = results.get("metadatas", [[{}]])[0][i] if results.get("metadatas") else {}
            distance = results.get("distances", [[None]])[0][i] if results.get("distances") else None
            documents.append({
                "content": doc_content,
                "metadata": metadata,
                "distance": distance,
            })
        return documents

    # ── 从目录加载 ───────────────────────────────────────

    def load_guidelines_from_directory(self, directory: str):
        """加载目录中所有 .md 指南文档，按章节分段入库。"""
        md_files = glob.glob(f"{directory}/*.md")
        total_sections = 0
        for file_path in md_files:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            sections = self._split_by_sections(content)
            source_name = os.path.basename(file_path)
            # 从文件名推断手术类型
            surgery = self._detect_surgery_type(source_name)
            for section in sections:
                self.add_documents(
                    documents=[section["content"]],
                    metadatas=[{
                        "source": source_name,
                        "section": section["title"],
                        "type": "guideline",
                        "surgery_type": surgery,
                    }],
                )
            total_sections += len(sections)
        logger.info("Loaded %d sections from %d guideline files", total_sections, len(md_files))

    @staticmethod
    def _detect_surgery_type(filename: str) -> str:
        """从文件名推断手术类型。"""
        name_lower = filename.lower()
        if "tka" in name_lower or "膝关节" in name_lower or "knee" in name_lower:
            return "TKA"
        elif "tha" in name_lower or "髋关节" in name_lower or "hip" in name_lower:
            return "THA"
        elif "acl" in name_lower or "前交叉" in name_lower or "anterior_cruciate" in name_lower:
            return "ACL"
        return "通用"

    def load_scales_from_directory(self, directory: str):
        """加载目录中所有 JSON 评估量表。"""
        json_files = glob.glob(f"{directory}/*.json")
        total = 0
        for file_path in json_files:
            with open(file_path, "r", encoding="utf-8") as f:
                scale = json.load(f)
            # 每个量表作为一个文档
            text_repr = json.dumps(scale, ensure_ascii=False, indent=2)
            self.add_documents(
                documents=[text_repr],
                metadatas=[{
                    "source": os.path.basename(file_path),
                    "scale_name": scale.get("scale_name", ""),
                    "scale_id": scale.get("scale_id", ""),
                    "type": "scale",
                }],
            )
            total += 1
        logger.info("Loaded %d scales", total)

    @staticmethod
    def _split_by_sections(content: str) -> List[Dict[str, str]]:
        """
        按 Markdown 标题分段（# 或 ## 级别）。
        修复了原方案的正则缺陷——现在能正确处理：
        1. 第一个标题前的内容（作为"前言"）
        2. 最后一个标题后的内容
        3. 单 # 和双 ## 标题
        """
        sections: List[Dict[str, str]] = []
        lines = content.split("\n")
        current_title = "前言"
        current_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            # 匹配一级或二级标题
            if re.match(r"^#{1,2}\s+", stripped):
                # 保存上一段
                body = "\n".join(current_lines).strip()
                if body:
                    sections.append({"title": current_title, "content": body})
                current_title = re.sub(r"^#+\s*", "", stripped)
                current_lines = []
            else:
                current_lines.append(line)

        # 最后的段落
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"title": current_title, "content": body})

        return sections


def build_knowledge_base(
    guidelines_dir: Optional[str] = None,
    scales_dir: Optional[str] = None,
) -> OrthoVectorStore:
    """
    一键构建知识库：加载所有指南文档和评估量表。
    首次运行或文件更新后调用。
    返回已填充的向量库实例。
    """
    guidelines_dir = guidelines_dir or os.getenv("KNOWLEDGE_GUIDELINES_DIR", "./knowledge/guidelines")
    scales_dir = scales_dir or os.getenv("KNOWLEDGE_SCALES_DIR", "./knowledge/scales")

    store = OrthoVectorStore()
    store.load_guidelines_from_directory(guidelines_dir)
    store.load_scales_from_directory(scales_dir)
    return store
