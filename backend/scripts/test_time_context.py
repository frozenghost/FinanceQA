"""测试时间上下文功能"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompts.loader import load_system_prompt
from core.agent.coordinator import get_time_context


def test_time_context():
    """测试时间上下文生成"""
    print("=" * 60)
    print("测试协调器时间上下文")
    print("=" * 60)
    context = get_time_context()
    print(context)
    print()


def test_system_prompt():
    """测试系统提示中的时间信息"""
    print("=" * 60)
    print("测试系统提示（前500字符）")
    print("=" * 60)
    prompt = load_system_prompt(strict=True)
    print(prompt[:500])
    print("\n...\n")
    print("=" * 60)
    print(f"完整提示长度: {len(prompt)} 字符")
    print("=" * 60)


if __name__ == "__main__":
    test_time_context()
    print()
    test_system_prompt()
