#!/usr/bin/env python3
"""
采样脚本 - 为 LLM 深度分析准备代表性样本

采样策略：
1. 时间均匀覆盖（按年季度分层）
2. 长度多样性（短/中/长）
3. 高频话题覆盖
4. 随机补充

用法:
    python3 sample_for_llm.py [--input clean_messages.jsonl] [--output sample.jsonl] [--size 5000]
"""

import json
import random
import argparse
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "references" / "clean_messages.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "references" / "sample_for_llm.jsonl"


def load_messages(path):
    msgs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                msgs.append(json.loads(line))
            except:
                continue
    return msgs


def quarter_key(ts):
    if ts <= 0:
        return 'unknown'
    dt = datetime.fromtimestamp(ts)
    return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"


def sample_stratified(msgs, target_size=5000):
    """分层采样"""
    random.seed(42)
    
    # 按季度分组
    by_quarter = defaultdict(list)
    for m in msgs:
        q = quarter_key(m.get('ts', 0))
        by_quarter[q].append(m)
    
    # 每季度均匀采样
    n_quarters = len(by_quarter)
    per_quarter = target_size // n_quarters
    
    samples = []
    
    # 1. 时间分层（70%）
    for q, qmsgs in sorted(by_quarter.items()):
        n_sample = min(per_quarter, len(qmsgs))
        # 再按长度分层
        short = [m for m in qmsgs if len(m['msg']) <= 10]
        medium = [m for m in qmsgs if 10 < len(m['msg']) <= 30]
        long = [m for m in qmsgs if len(m['msg']) > 30]
        
        n_short = min(len(short), n_sample // 3)
        n_medium = min(len(medium), n_sample // 3)
        n_long = min(len(long), n_sample - n_short - n_medium)
        
        if short:
            samples.extend(random.sample(short, n_short))
        if medium:
            samples.extend(random.sample(medium, n_medium))
        if long:
            samples.extend(random.sample(long, n_long))
    
    # 2. 如果不够，随机补充
    existing_ids = {id(m) for m in samples}
    remaining = [m for m in msgs if id(m) not in existing_ids]
    
    if len(samples) < target_size and remaining:
        extra = random.sample(remaining, min(target_size - len(samples), len(remaining)))
        samples.extend(extra)
    
    # 3. 如果超了，随机裁剪
    if len(samples) > target_size:
        samples = random.sample(samples, target_size)
    
    # 按时间排序
    samples.sort(key=lambda x: x.get('ts', 0))
    return samples


def main():
    parser = argparse.ArgumentParser(description='采样用于 LLM 分析的消息')
    parser.add_argument('--input', type=str, default=str(DEFAULT_INPUT))
    parser.add_argument('--output', type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument('--size', type=int, default=5000)
    args = parser.parse_args()
    
    msgs = load_messages(args.input)
    print(f"📊 总消息: {len(msgs):,}")
    
    samples = sample_stratified(msgs, args.size)
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for m in samples:
            f.write(json.dumps(m, ensure_ascii=False) + '\n')
    
    print(f"✅ 采样: {len(msgs):,} → {len(samples):,}")
    print(f"📁 输出: {output_path}")
    
    # 分布统计
    years = defaultdict(int)
    lengths = defaultdict(int)
    for m in samples:
        ts = m.get('ts', 0)
        if ts > 0:
            y = datetime.fromtimestamp(ts).year
            years[y] += 1
        l = len(m['msg'])
        if l <= 5:
            lengths['1-5'] += 1
        elif l <= 20:
            lengths['6-20'] += 1
        else:
            lengths['20+'] += 1
    
    print(f"\n📈 年份分布: {dict(sorted(years.items()))}")
    print(f"📏 长度分布: {dict(sorted(lengths.items()))}")


if __name__ == '__main__':
    main()
