#!/usr/bin/env python3
"""
build_batches.py - 全量采样：26 批时间均匀分布（~100% 覆盖）

策略:
  - 按时间排序所有消息
  - 均匀分为 26 批，每批 ~2000 条
  - 不重叠，批批相接
  
输出: raw_data/batch_01.txt ~ batch_26.txt
"""

import json
import random
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
CLEAN_DATA = SKILL_DIR / "references" / "clean_messages.jsonl"
RAW_DIR = SKILL_DIR / "raw_data"


def load_messages(path):
    msgs = []
    with open(path, 'r') as f:
        for line in f:
            try:
                msgs.append(json.loads(line))
            except:
                continue
    return msgs


def main():
    msgs = load_messages(CLEAN_DATA)
    print(f"📊 总消息: {len(msgs):,}")
    
    random.seed(42)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # 按时间排序
    msgs_sorted = sorted(msgs, key=lambda x: x.get('ts', 0))
    
    # 分为 26 批
    n_batches = 26
    batch_size = len(msgs_sorted) // n_batches
    remainder = len(msgs_sorted) % n_batches
    
    print(f"📦 批次: {n_batches}, 每批约 {batch_size} 条")
    
    start = 0
    total_assigned = 0
    
    for i in range(1, n_batches + 1):
        # 最后几批多分配余数
        size = batch_size + (1 if i <= remainder else 0)
        batch_msgs = msgs_sorted[start:start + size]
        start += size
        
        # 打乱批次内顺序（避免时间顺序影响 LLM 分析）
        random.shuffle(batch_msgs)
        
        # 写入
        batch_file = RAW_DIR / f"batch_{i:02d}.txt"
        with open(batch_file, 'w') as f:
            for m in batch_msgs:
                f.write(m['msg'] + '\n')
        
        total_assigned += len(batch_msgs)
        print(f"  批次 {i:02d}: {len(batch_msgs)} 条 -> {batch_file.name}")
    
    coverage = total_assigned / len(msgs) * 100
    print(f"\n{'='*50}")
    print(f"📊 总计: {total_assigned:,} / {len(msgs):,} = {coverage:.1f}%")
    print(f"📁 批次文件: {RAW_DIR}")
    print(f"✅ 全量采样完成")


if __name__ == '__main__':
    main()
