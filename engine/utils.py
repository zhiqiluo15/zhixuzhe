"""引擎通用工具函数"""

from pathlib import Path


def load_dotenv(root: Path) -> dict[str, str]:
    """加载指定目录下的 .env 文件，返回键值对字典。

    不引入 python-dotenv 依赖。用法：
        from engine.utils import load_dotenv
        env = load_dotenv(Path(__file__).resolve().parent.parent.parent)
        api_key = env.get("DEEPSEEK_API_KEY")
    """
    env_file = root / ".env"
    if not env_file.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values
