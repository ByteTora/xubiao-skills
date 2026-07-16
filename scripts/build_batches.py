#!/usr/bin/env python3
"""
build_batches.py - 生成 12 批不重叠分层采样（全量方案）

策略:
  - 批次 01-08: 时间 × 长度分层（每季度均等 × 短/中/长 = 各 33%）
  - 批次 09-10: 长消息重点采样（>50 字）
  - 批次 11-12: 高情绪消息（含多表情/情绪词）
  
输出: raw_data/batch_01.txt ~ batch_12.txt（各 2000 条，不重叠）
"""

import json
import random
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# 路径
SKILL_DIR = Path(__file__).resolve().parent.parent
CLEAN_DATA = SKILL_DIR / "references" / "clean_messages.jsonl"
RAW_DIR = SKILL_DIR / "raw_data"

# 情绪词（用于高情绪采样）
EMOTION_WORDS = {"烦","累","难受","伤心","痛苦","委屈","生气","愤怒","失望","绝望",
                 "开心","高兴","快乐","兴奋","感动","舒服","爽","棒","赞",
                 "哈哈","哈哈哈","哈哈哈哈","牛逼","卧槽","我靠","我去",
                 "焦虑","压力","崩溃","孤独","emo","摆烂","躺平","哭"}

# 表情符号模式
EMOJI_RE = re.compile(r'\[[\u4e00-\u9fff\w]+\]')


def load_messages(path):
    msgs = []
    with open(path, 'r') as f:
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


def emotion_score(msg):
    """计算情绪分数（情绪词 + 表情密度）"""
    text = msg['msg']
    score = 0
    # 情绪词
    for w in EMOTION_WORDS:
        score += text.count(w) * 2
    # 表情
    emoji_count = len(EMOJI_RE.findall(text))
    score += emoji_count * 3
    # 重复字符（啊啊啊啊 哈哈哈哈哈）
    repeats = len(re.findall(r'(.)\1{3,}', text))
    score += repeats * 2
    return score


def main():
    msgs = load_messages(CLEAN_DATA)
    print(f"📊 总消息: {len(msgs):,}")
    
    random.seed(42)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    used_ids = set()  # 记录已分配消息 ID
    batch = 1
    
    # 预先为阶段 2（长消息）和阶段 3（高情绪）预留消息
    long_ids = {i for i, m in enumerate(msgs) if len(m['msg']) > 50}
    scored_list = [(i, m, emotion_score(m)) for i, m in enumerate(msgs)]
    scored_list.sort(key=lambda x: -x[2])
    high_emotion_ids = {x[0] for x in scored_list[:4000]}  # 预留 4000 条高情绪
    
    reserved_for_long = set(random.sample(list(long_ids), min(4000, len(long_ids))))
    reserved = reserved_for_long | (high_emotion_ids - reserved_for_long)
    reserved = set(list(reserved)[:6000])  # 最多预留 6000 条
    
    print(f"📌 预留: {len(reserved)} 条（长消息+高情绪）")
    
    # === 阶段 1: 批次 01-06，时间×长度分层（跳过预留）===
    print("\n=== 阶段 1: 时间×长度分层（批次 01-06）===")
    
    # 按季度分组
    by_quarter = defaultdict(list)
    for idx, m in enumerate(msgs):
        if idx in reserved:
            continue  # 跳过预留
        q = quarter_key(m.get('ts', 0))
        by_quarter[q].append((idx, m))
    
    # 每个季度内再按长度分桶
    for batch_n in range(1, 7):
        sampled = []
        for q, qmsgs in sorted(by_quarter.items()):
            available = [(i, m) for i, m in qmsgs if i not in used_ids]
            if not available:
                continue
            
            short = [(i, m) for i, m in available if len(m['msg']) <= 10]
            med = [(i, m) for i, m in available if 10 < len(m['msg']) <= 30]
            long = [(i, m) for i, m in available if len(m['msg']) > 30]
            
            per_quarter = max(1, 2000 // (len(by_quarter) * 3))
            for pool in [short, med, long]:
                n = min(per_quarter, len(pool))
                if pool and n > 0:
                    picked = random.sample(pool, n)
                    sampled.extend(picked)
        
        remaining = [(i, m) for i, m in enumerate(msgs) if i not in used_ids 
                     and i not in reserved and (i, m) not in sampled]
        random.shuffle(remaining)
        needed = 2000 - len(sampled)
        if needed > 0 and remaining:
            sampled.extend(remaining[:needed])
        
        sampled.sort(key=lambda x: x[1].get('ts', 0))
        
        batch_file = RAW_DIR / f"batch_{batch:02d}.txt"
        with open(batch_file, 'w') as f:
            for idx, m in sampled:
                f.write(m['msg'] + '\n')
                used_ids.add(idx)
        
        print(f"  批次 {batch:02d}: {len(sampled)} 条 -> {batch_file.name}")
        batch += 1
    
    print(f"\n✅ 阶段 1 完成: {len(used_ids):,} 条已分配")
    
    # === 阶段 2: 长消息 + 高情绪混合采样（批次 07-08, 09-10）===
    # 先用长消息填充，不够的用高情绪补齐，再不够用随机补齐
    print("\n=== 阶段 2: 长消息+高情绪混合采样（批次 07-10）===")
    
    # 优先长消息，混合高情绪
    mixed_pool = list(reserved - used_ids)
    # 排序：长消息优先，其次高情绪分
    mixed = [(i, msgs[i], emotion_score(msgs[i])) for i in mixed_pool]
    long_first = sorted(mixed, key=lambda x: (
        -len(x[1]['msg']) if x[2] > 0 else 0,  # 长消息优先
        -x[2]  # 再按情绪分
    ))
    
    for _ in range(3):
        if not long_first:
            break
        picked = long_first[:2000]
        long_first = long_first[2000:]
        
        picked_items = [(i, m) for i, m, s in picked]
        picked_items.sort(key=lambda x: x[1].get('ts', 0))
        
        batch_file = RAW_DIR / f"batch_{batch:02d}.txt"
        with open(batch_file, 'w') as f:
            for idx, m in picked_items:
                f.write(m['msg'] + '\n')
                used_ids.add(idx)
        
        print(f"  批次 {batch:02d}: {len(picked_items)} 条（长消息+高情绪）-> {batch_file.name}")
        batch += 1
    
    # === 阶段 3: 补齐到 12 批（随机）===
    print("\n=== 阶段 3: 补齐剩余批次 ===")
    
    while batch <= 12:
        available = [(i, m) for i, m in enumerate(msgs) if i not in used_ids]
        random.shuffle(available)
        picked = available[:2000]
        if not picked:
            break
        
        picked.sort(key=lambda x: x[1].get('ts', 0))
        
        batch_file = RAW_DIR / f"batch_{batch:02d}.txt"
        with open(batch_file, 'w') as f:
            for idx, m in picked:
                f.write(m['msg'] + '\n')
                used_ids.add(idx)
        
        print(f"  批次 {batch:02d}: {len(picked)} 条（补齐）-> {batch_file.name}")
        batch += 1
    
    # 统计
    coverage = len(used_ids) / len(msgs) * 100
    print(f"\n{'='*50}")
    print(f"📊 总计: {len(used_ids):,} / {len(msgs):,} = {coverage:.1f}%")
    print(f"📁 批次文件: {RAW_DIR}")
    print(f"✅ 完成")


if __name__ == '__main__':
    main()
