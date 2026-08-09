"""智序者引擎 —— 基因层，可开源

全局版本号唯一来源（Single Source of Truth）。
所有展示智序者版本的地方（Web 页面、CLI 横幅、配置文件注释、日志）
必须引用本常量，禁止硬编码字符串，避免版本漂移。
升级版本号时只需修改此处，并在 CHANGELOG.md 顶部登记对应变更。
"""

__version__ = "1.3.3"
VERSION = __version__
