"""
向量存储系统

基于ChromaDB的向量存储和检索功能
"""

import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from loguru import logger
import json


class VectorStore:
    """向量存储管理器"""
    
    def __init__(self, config=None):
        """
        初始化向量存储
        
        Args:
            config: 配置对象
        """
        self.config = config
        self.model_name = getattr(config, 'embedding_model', 'all-MiniLM-L6-v2')
        self.collection_name = getattr(config, 'collection_name', 'c_code_symbols')
        
        # 初始化嵌入模型
        logger.info(f"正在加载嵌入模型: {self.model_name}")
        try:
            self.embedding_model = SentenceTransformer(self.model_name)
            self.embedding_dimension = self.embedding_model.get_sentence_embedding_dimension()
            logger.info(f"嵌入模型加载完成，维度: {self.embedding_dimension}")
        except Exception as e:
            logger.error(f"嵌入模型加载失败: {e}")
            raise
        
        # 初始化ChromaDB
        self._init_chromadb()
    
    def _init_chromadb(self):
        """初始化ChromaDB客户端和集合"""
        try:
            # 设置数据目录
            data_dir = getattr(self.config, 'chroma_data_dir', './data/chroma')
            Path(data_dir).mkdir(parents=True, exist_ok=True)
            
            # 创建ChromaDB客户端
            self.chroma_client = chromadb.PersistentClient(
                path=data_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            try:
                self.collection = self.chroma_client.get_collection(
                    name=self.collection_name
                )
                logger.info(f"加载现有集合: {self.collection_name}")
            except Exception:
                self.collection = self.chroma_client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "C代码符号向量索引"}
                )
                logger.info(f"创建新集合: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"ChromaDB初始化失败: {e}")
            raise
    
    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        """
        添加文档到向量存储
        
        Args:
            documents: 文档文本列表
            metadatas: 元数据列表
            ids: 文档ID列表
        """
        if not documents:
            logger.warning("没有文档需要添加")
            return
        
        logger.info(f"开始添加 {len(documents)} 个文档到向量存储")
        
        try:
            # 生成嵌入向量
            embeddings = self.embedding_model.encode(
                documents, 
                convert_to_tensor=False,
                show_progress_bar=True
            ).tolist()
            
            # 批量添加到ChromaDB
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                end_idx = min(i + batch_size, len(documents))
                
                batch_documents = documents[i:end_idx]
                batch_embeddings = embeddings[i:end_idx]
                batch_metadatas = metadatas[i:end_idx]
                batch_ids = ids[i:end_idx]
                
                # 检查是否已存在，如果存在则更新，否则添加
                existing_ids = set()
                try:
                    existing_results = self.collection.get(ids=batch_ids)
                    existing_ids = set(existing_results['ids'])
                except Exception:
                    pass
                
                # 分离新增和更新的数据
                new_documents = []
                new_embeddings = []
                new_metadatas = []
                new_ids = []
                
                update_documents = []
                update_embeddings = []
                update_metadatas = []
                update_ids = []
                
                for j, doc_id in enumerate(batch_ids):
                    if doc_id in existing_ids:
                        update_documents.append(batch_documents[j])
                        update_embeddings.append(batch_embeddings[j])
                        update_metadatas.append(batch_metadatas[j])
                        update_ids.append(doc_id)
                    else:
                        new_documents.append(batch_documents[j])
                        new_embeddings.append(batch_embeddings[j])
                        new_metadatas.append(batch_metadatas[j])
                        new_ids.append(doc_id)
                
                # 添加新文档
                if new_documents:
                    self.collection.add(
                        documents=new_documents,
                        embeddings=new_embeddings,
                        metadatas=new_metadatas,
                        ids=new_ids
                    )
                
                # 更新现有文档
                if update_documents:
                    self.collection.update(
                        documents=update_documents,
                        embeddings=update_embeddings,
                        metadatas=update_metadatas,
                        ids=update_ids
                    )
                
                logger.info(f"批次 {i//batch_size + 1}: 新增 {len(new_documents)} 个，更新 {len(update_documents)} 个")
            
            logger.info("文档添加完成")
            
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise
    
    def _format_similarity(self, distance: float) -> float:
        # 兼容不同距离度量，确保相似度在(0,1]范围
        try:
            if distance is None:
                return 0.0
            if 0.0 <= distance <= 1.0:
                return max(0.0, 1.0 - float(distance))
            return 1.0 / (1.0 + float(distance))
        except Exception:
            return 0.0
    
    def search(self, query: str, n_results: int = 10, filter_dict: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        语义搜索
        
        Args:
            query: 查询文本
            n_results: 返回结果数量
            filter_dict: 过滤条件
            
        Returns:
            搜索结果列表
        """
        try:
            # 生成查询向量
            query_embedding = self.embedding_model.encode([query], convert_to_tensor=False).tolist()
            
            # 构建过滤条件
            where_filter = None
            if filter_dict:
                where_filter = {}
                for key, value in filter_dict.items():
                    if isinstance(value, str):
                        where_filter[key] = {"$eq": value}
                    elif isinstance(value, list):
                        where_filter[key] = {"$in": value}
                    else:
                        where_filter[key] = {"$eq": value}
            
            # 执行搜索
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=n_results,
                where=where_filter,
                include=['documents', 'metadatas', 'distances']
            )
            
            # 格式化结果
            formatted_results = []
            if results['ids'] and len(results['ids']) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    distance = results['distances'][0][i] if results.get('distances') else None
                    result = {
                        'id': doc_id,
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': distance,
                        'similarity': self._format_similarity(distance)
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return []
    
    def search_by_symbol_type(self, symbol_type: str, n_results: int = 10, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        按符号类型搜索
        
        Args:
            symbol_type: 符号类型 (function, structure, variable, macro)
            n_results: 返回结果数量
            limit: 可选的结果限制
            
        Returns:
            搜索结果列表
        """
        count = limit if (limit is not None) else n_results
        filter_dict = {"type": symbol_type}
        return self.search("", n_results=count, filter_dict=filter_dict)
    
    def search_by_file(self, file_path: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        按文件路径搜索
        
        Args:
            file_path: 文件路径
            n_results: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        filter_dict = {"file_path": file_path}
        return self.search("", n_results=n_results, filter_dict=filter_dict)
    
    def get_symbol_by_name(self, symbol_name: str) -> List[Dict[str, Any]]:
        """
        按符号名称精确查找
        
        Args:
            symbol_name: 符号名称
            
        Returns:
            匹配的符号列表
        """
        filter_dict = {"name": symbol_name}
        return self.search("", n_results=100, filter_dict=filter_dict)
    
    def get_all_symbols(self, symbol_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取所有符号
        
        Args:
            symbol_type: 可选的符号类型过滤
            
        Returns:
            符号列表
        """
        try:
            # 构建过滤条件
            where_filter = None
            if symbol_type:
                where_filter = {"type": {"$eq": symbol_type}}
            
            # 获取所有数据
            results = self.collection.get(
                where=where_filter,
                include=['documents', 'metadatas']
            )
            
            # 格式化结果
            formatted_results = []
            if results['ids']:
                for i, doc_id in enumerate(results['ids']):
                    result = {
                        'id': doc_id,
                        'document': results['documents'][i] if results['documents'] else '',
                        'metadata': results['metadatas'][i] if results['metadatas'] else {}
                    }
                    formatted_results.append(result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"获取符号失败: {e}")
            return []
    
    def delete_by_project(self, project_path: str):
        """
        删除指定项目的所有数据
        
        Args:
            project_path: 项目路径
        """
        try:
            # 查找该项目的所有文档
            results = self.collection.get(
                where={"project_path": {"$eq": project_path}},
                include=['ids']
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"已删除项目 {project_path} 的 {len(results['ids'])} 个文档")
            else:
                logger.info(f"项目 {project_path} 没有找到任何文档")
                
        except Exception as e:
            logger.error(f"删除项目数据失败: {e}")
            raise
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取存储统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 获取总数量
            all_results = self.collection.get(include=['metadatas'])
            total_count = len(all_results['ids']) if all_results['ids'] else 0
            
            # 按类型统计
            type_counts = {}
            if all_results['metadatas']:
                for metadata in all_results['metadatas']:
                    symbol_type = metadata.get('type', 'unknown')
                    type_counts[symbol_type] = type_counts.get(symbol_type, 0) + 1
            
            # 按项目统计
            project_counts = {}
            if all_results['metadatas']:
                for metadata in all_results['metadatas']:
                    project = metadata.get('project_path', 'unknown')
                    project_counts[project] = project_counts.get(project, 0) + 1
            
            return {
                'total_symbols': total_count,
                'symbols_by_type': type_counts,
                'symbols_by_project': project_counts,
                'embedding_dimension': self.embedding_dimension,
                'model_name': self.model_name
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def reset_collection(self):
        """重置集合（删除所有数据）"""
        try:
            self.chroma_client.delete_collection(name=self.collection_name)
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name,
                metadata={"description": "C代码符号向量索引"}
            )
            logger.info("集合已重置")
        except Exception as e:
            logger.error(f"重置集合失败: {e}")
            raise
    
    def get_dimension(self) -> int:
        """获取向量维度"""
        return self.embedding_dimension
    
    def close(self):
        """关闭连接"""
        # ChromaDB会自动持久化，无需特殊关闭操作
        logger.info("向量存储连接已关闭") 