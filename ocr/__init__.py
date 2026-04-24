"""OCR处理包 - 包含不同的OCR后端实现"""

from .paddle import process_with_paddle
from .api import process_with_api

# 简单的注册表 - 就是个字典
_BACKENDS = {
    "paddle": process_with_paddle,
    "api": process_with_api,
}

def get_backend(name):
    """获取OCR后端函数"""
    if name not in _BACKENDS:
        raise ValueError(f"未知的OCR后端: {name}，可用: {list(_BACKENDS.keys())}")
    return _BACKENDS[name]

def register_backend(name, func):
    """注册新的OCR后端"""
    _BACKENDS[name] = func

def list_backends():
    """列出所有可用后端"""
    return list(_BACKENDS.keys())

__all__ = ["process_with_paddle", "process_with_api", "get_backend", "register_backend", "list_backends"]
