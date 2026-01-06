"""
Milvus向量数据库服务
支持嵌入式部署，无需外部Docker服务
"""

from typing import Any, Dict, List
from datetime import datetime
from pathlib import Path

try:
    from pymilvus import MilvusClient, DataType
    PYMILVUS_AVAILABLE = True
except ImportError:
    PYMILVUS_AVAILABLE = False
    # 创建占位符类
    MilvusClient = None
    DataType = None

import logging

# 简化日志配置
logger = logging.getLogger(__name__)

class MilvusVectorService:
    """Milvus向量存储服务"""
    
    def __init__(self, uri: str = "data/milvus/milvus_demo.db", token: str = ""):
        if not PYMILVUS_AVAILABLE:
            logger.warning("pymilvus不可用，MilvusVectorService将以降级模式运行")
            self.client = None
            return
            
        """
        初始化Milvus服务
        
        Args:
            uri: Milvus服务URI
            token: Milvus服务Token
        """
        self.uri = uri
        self.token = token
        self.client = None
        self.collections = {
            "embedding_cache": "embedding_cache_collection",
            "task_embeddings": "task_embeddings_collection"
        }
        
        # 确保数据目录存在
        Path(uri).parent.mkdir(parents=True, exist_ok=True)
        
    async def initialize(self):
        """初始化Milvus客户端和集合"""
        try:
            logger.info(f"🚀 初始化Milvus Lite: {self.uri}")
            
            # 创建Milvus Lite客户端
            milvus_client = MilvusClient
            if milvus_client is None:
                logger.warning("MilvusClient不可用，跳过初始化")
                return False
            self.client = milvus_client(uri=self.uri)
            
            # 创建集合
            await self._create_collections()
            
            logger.info("✅ Milvus初始化完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ Milvus初始化失败: {e}")
            return False
    
    async def _create_collections(self):
        """创建所需的集合"""
        
        # 1. 创建embedding_cache集合
        await self._create_embedding_cache_collection()
        
        # 2. 创建task_embeddings集合
        await self._create_task_embeddings_collection()
    
    async def _create_embedding_cache_collection(self):
        """创建嵌入缓存集合"""
        if self.client is None or MilvusClient is None or DataType is None:
            return
        client = self.client
        milvus_client = MilvusClient
        data_type = DataType
        collection_name = self.collections["embedding_cache"]
        
        if client.has_collection(collection_name):
            logger.info(f"集合 {collection_name} 已存在")
            return
        
        # 定义字段
        schema = milvus_client.create_schema(
            auto_id=True,
            enable_dynamic_field=False
        )
        
        # 添加字段
        schema.add_field(field_name="id", datatype=data_type.INT64, is_primary=True)
        schema.add_field(field_name="text_hash", datatype=data_type.VARCHAR, max_length=64)
        schema.add_field(field_name="embedding", datatype=data_type.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="model", datatype=data_type.VARCHAR, max_length=50)
        schema.add_field(field_name="created_at", datatype=data_type.INT64)
        schema.add_field(field_name="access_count", datatype=data_type.INT64)
        schema.add_field(field_name="last_accessed", datatype=data_type.INT64)
        
        # 创建集合
        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            metric_type="COSINE",  # 余弦相似度
            consistency_level="Strong"
        )
        
        # 创建索引 (适配Milvus Lite)
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",  # Lite版本支持的索引类型
            metric_type="COSINE",
            params={"nlist": 128}  # IVF_FLAT参数
        )
        
        client.create_index(
            collection_name=collection_name,
            index_params=index_params
        )
        
        logger.info(f"✅ 创建集合: {collection_name}")
    
    async def _create_task_embeddings_collection(self):
        """创建任务嵌入集合"""
        if self.client is None or MilvusClient is None or DataType is None:
            return
        client = self.client
        milvus_client = MilvusClient
        data_type = DataType
        collection_name = self.collections["task_embeddings"]
        
        if client.has_collection(collection_name):
            logger.info(f"集合 {collection_name} 已存在")
            return
        
        # 定义字段
        schema = milvus_client.create_schema(
            auto_id=True,
            enable_dynamic_field=False
        )
        
        # 添加字段
        schema.add_field(field_name="id", datatype=data_type.INT64, is_primary=True)
        schema.add_field(field_name="task_id", datatype=data_type.INT64)
        schema.add_field(field_name="embedding", datatype=data_type.FLOAT_VECTOR, dim=1024)
        schema.add_field(field_name="model", datatype=data_type.VARCHAR, max_length=50)
        schema.add_field(field_name="created_at", datatype=data_type.INT64)
        schema.add_field(field_name="updated_at", datatype=data_type.INT64)
        
        # 创建集合
        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            metric_type="COSINE",
            consistency_level="Strong"
        )
        
        # 创建索引 (适配Milvus Lite)
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="IVF_FLAT",  # Lite版本支持的索引类型
            metric_type="COSINE",
            params={"nlist": 128}  # IVF_FLAT参数
        )
        
        client.create_index(
            collection_name=collection_name,
            index_params=index_params
        )
        
        logger.info(f"✅ 创建集合: {collection_name}")
    
    async def store_embedding_cache(
        self, 
        text_hash: str, 
        embedding: List[float], 
        model: str
    ) -> bool:
        """存储嵌入缓存"""
        try:
            if self.client is None:
                return False
            client = self.client
            collection_name = self.collections["embedding_cache"]
            
            data = [{
                "text_hash": text_hash,
                "embedding": embedding,
                "model": model,
                "created_at": int(datetime.now().timestamp()),
                "access_count": 1,
                "last_accessed": int(datetime.now().timestamp())
            }]
            
            client.insert(
                collection_name=collection_name,
                data=data
            )
            
            logger.info(f"✅ 存储嵌入缓存: {text_hash[:16]}...")
            return True
            
        except Exception as e:
            logger.error(f"❌ 存储嵌入缓存失败: {e}")
            return False
    
    async def store_task_embedding(
        self,
        task_id: int,
        embedding: List[float], 
        model: str
    ) -> bool:
        """存储任务嵌入"""
        try:
            if self.client is None:
                return False
            client = self.client
            collection_name = self.collections["task_embeddings"]
            
            data = [{
                "task_id": task_id,
                "embedding": embedding,
                "model": model,
                "created_at": int(datetime.now().timestamp()),
                "updated_at": int(datetime.now().timestamp())
            }]
            
            client.insert(
                collection_name=collection_name,
                data=data
            )
            
            logger.info(f"✅ 存储任务嵌入: task_id={task_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 存储任务嵌入失败: {e}")
            return False
    
    async def search_embedding_cache(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        score_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """搜索嵌入缓存"""
        try:
            if self.client is None:
                return []
            client = self.client
            collection_name = self.collections["embedding_cache"]
            
            search_params = {"metric_type": "COSINE", "params": {"ef": 100}}
            
            results = client.search(
                collection_name=collection_name,
                data=[query_embedding],
                limit=top_k,
                search_params=search_params,
                output_fields=["text_hash", "model", "created_at", "access_count"]
            )
            
            # 过滤结果
            filtered_results = []
            for hits in results:
                for hit in hits:
                    if hit["distance"] >= score_threshold:
                        filtered_results.append({
                            "text_hash": hit["entity"]["text_hash"],
                            "model": hit["entity"]["model"],
                            "score": hit["distance"],
                            "created_at": hit["entity"]["created_at"],
                            "access_count": hit["entity"]["access_count"]
                        })
            
            logger.info(f"🔍 嵌入缓存搜索: 找到 {len(filtered_results)} 个结果")
            return filtered_results
            
        except Exception as e:
            logger.error(f"❌ 嵌入缓存搜索失败: {e}")
            return []
    
    async def search_similar_tasks(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """搜索相似任务"""
        try:
            if self.client is None:
                return []
            client = self.client
            collection_name = self.collections["task_embeddings"]
            
            search_params = {"metric_type": "COSINE", "params": {"ef": 100}}
            
            results = client.search(
                collection_name=collection_name,
                data=[query_embedding],
                limit=top_k,
                search_params=search_params,
                output_fields=["task_id", "model", "created_at"]
            )
            
            # 过滤结果
            filtered_results = []
            for hits in results:
                for hit in hits:
                    if hit["distance"] >= score_threshold:
                        filtered_results.append({
                            "task_id": hit["entity"]["task_id"],
                            "model": hit["entity"]["model"],
                            "score": hit["distance"],
                            "created_at": hit["entity"]["created_at"]
                        })
            
            logger.info(f"🔍 相似任务搜索: 找到 {len(filtered_results)} 个结果")
            return filtered_results
            
        except Exception as e:
            logger.error(f"❌ 相似任务搜索失败: {e}")
            return []
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            if self.client is None:
                return {}
            client = self.client
            stats = {}
            
            for collection_type, collection_name in self.collections.items():
                if client.has_collection(collection_name):
                    # 获取集合信息
                    info = client.describe_collection(collection_name)
                    
                    # 获取记录数量
                    query_result = client.query(
                        collection_name=collection_name,
                        expr="id >= 0",
                        output_fields=["count(*)"]
                    )
                    
                    stats[collection_type] = {
                        "collection_name": collection_name,
                        "schema": info,
                        "record_count": len(query_result) if query_result else 0
                    }
            
            return stats
            
        except Exception as e:
            logger.error(f"❌ 获取集合统计失败: {e}")
            return {}
    
    async def close(self):
        """关闭连接"""
        if self.client:
            # Milvus Lite 会自动管理连接
            logger.info("🔌 Milvus连接已关闭")


# 全局Milvus服务实例
_milvus_service = None

async def get_milvus_service() -> MilvusVectorService:
    """获取Milvus服务实例（单例模式）"""
    global _milvus_service
    
    if _milvus_service is None:
        _milvus_service = MilvusVectorService()
        await _milvus_service.initialize()
    
    return _milvus_service
