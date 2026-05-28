#!/usr/bin/env python3
"""
修复 platforms/chatgpt/payment.py 中缺少的 Account 导入。

上游 bug: payment.py 引用了 Account 类型注解，但仅保留了注释掉的旧导入。
修复: 在正确位置添加 `from core.base_platform import Account`

Usage:
    python3 fix_payment_import.py [--dry-run]

Options:
    --dry-run   只检查，不修改
"""

import sys
from pathlib import Path

PAYMENT_PY = Path(__file__).parent.parent / "platforms/chatgpt/payment.py"

def fix_payment_import(dry_run: bool = False) -> bool:
    """修复 payment.py 中的 Account 导入问题."""
    
    if not PAYMENT_PY.exists():
        print(f"❌ 文件不存在: {PAYMENT_PY}")
        return False
    
    content = PAYMENT_PY.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    
    # 检查是否已经修复
    if "from core.base_platform import Account" in content:
        print("✅ 导入已存在，无需修复")
        return True
    
    # 查找插入位置（在 "# from ..database.models import Account" 后）
    target = "# from ..database.models import Account  # removed: external dep\n"
    target_idx = None
    
    for i, line in enumerate(lines):
        if line.strip().startswith("# from ..database.models import Account"):
            target_idx = i
            break
    
    if target_idx is None:
        print("❌ 未找到目标导入语句位置")
        print("   请手动添加: from core.base_platform import Account")
        return False
    
    # 检查下一行是否已有修复
    if target_idx + 1 < len(lines) and "from core.base_platform import Account" in lines[target_idx + 1]:
        print("✅ 导入已存在（在注释后）")
        return True
    
    if dry_run:
        print(f"📝 [DRY-RUN] 将在第 {target_idx + 1} 行后添加:")
        print("    from core.base_platform import Account")
        return True
    
    # 执行修复
    insert_pos = target_idx + 1
    new_line = "from core.base_platform import Account\n"
    
    # 确保插入位置后有一个空行（保持 PEP8）
    if insert_pos < len(lines) and not lines[insert_pos].strip():
        new_line = new_line.rstrip('\n') + '\n'
    
    lines.insert(insert_pos, new_line)
    
    new_content = ''.join(lines)
    PAYMENT_PY.write_text(new_content, encoding="utf-8")
    
    print(f"✅ 已修复: 在第 {insert_pos + 1} 行添加导入")
    print(f"   文件: {PAYMENT_PY}")
    return True

def verify_fix() -> bool:
    """验证修复是否成功."""
    try:
        # 尝试导入模块
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from platforms.chatgpt.payment import fetch_subscription_status_details
        print("✅ 模块导入验证通过")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 验证异常: {e}")
        return False

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    
    print("=" * 60)
    print("payment.py Account 导入修复工具")
    print("=" * 60)
    
    success = fix_payment_import(dry_run=dry_run)
    
    if success and not dry_run:
        print("\n验证修复...")
        verify_fix()
    
    sys.exit(0 if success else 1)
