import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

_load_env()


CHROMA_PATH = str(ROOT_DIR / "chroma_db")
CHROMA_COLLECTION = "study_abroad_kb"


DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_MODEL = "deepseek-chat"


EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIM = 1024

# 检索配置
RETRIEVAL_TOP_K = 15
RETRIEVAL_TOP_K_LARGE = 30  # 召回阶段使用，保证覆盖面
SIMILARITY_THRESHOLD = 0.08

# 多路融合权重
FUSION_VECTOR_WEIGHT = 0.6
FUSION_RULE_WEIGHT = 0.4

# 大学数据
UNIVERSITIES_PATH = str(ROOT_DIR / "data" / "universities.json")
