#!/usr/bin/env python3
"""
merge_analysis.py - 合并 12 份 LLM mini 报告为综合报告 + 置信度评分

输入: raw_data/mini_report_01.md ~ 12.md
输出: raw_data/merged_report.md

合并逻辑:
  - 语言特征: 跨批次统计出现率 → 置信度标签
  - 人格/价值: 按批次间一致性排序
  - 对话模式: 聚类合并高频模式
  - 边缘特征: 标注为低置信度
"""

import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

RAW_DIR = Path(__file__).resolve().parent.parent / "raw_data"


def parse_reports():
    """解析所有 mini_report_NN.md 为结构化数据"""
    reports = []
    
    for i in range(1, 27):  # 26 batches
        path = RAW_DIR / f"mini_report_{i:02d}.md"
        if not path.exists():
            print(f"  ⚠️  {path.name} 不存在，跳过")
            continue
        
        text = path.read_text(encoding='utf-8')
        report = {'batch': i, 'raw': text}
        
        # 按 ## 分节
        sections = re.split(r'^## ', text, flags=re.MULTILINE)
        
        for sec in sections:
            if not sec.strip():
                continue
            lines = sec.strip().split('\n')
            section_name = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
            
            if '语言特征' in section_name:
                report['language'] = _parse_list(content)
            elif '人格' in section_name or '价值观' in section_name:
                report['personality'] = _parse_bullets(content)
            elif '对话' in section_name:
                report['patterns'] = _parse_bullets(content)
            elif '高频短语' in section_name:
                report['phrases'] = _parse_list(content)
            elif '情绪' in section_name:
                report['emotion'] = content
        
        reports.append(report)
    
    return reports


def _parse_list(text):
    """解析编号列表 (1. xxx)"""
    items = []
    for line in text.split('\n'):
        line = line.strip()
        # 匹配 "1. 特征 - 描述" 或 "1. 特征"
        m = re.match(r'\d+\.\s+(.+?)(?:\s*[-–—]\s*(.+))?$', line)
        if m:
            feature = m.group(1).strip()
            detail = m.group(2).strip() if m.group(2) else ''
            items.append(f"{feature} {detail}".strip())
    return items


def _parse_bullets(text):
    """解析子弹点列表 (- xxx)"""
    items = []
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('- '):
            items.append(line[2:])
    return items


def _get_feature_name(text):
    """提取纯特征名（去掉数字、次数、标点）"""
    for sep in [' - ', ':', '：', '（', '(', '～', '~']:
        text = text.split(sep)[0]
    text = text.strip()
    text = re.sub(r'\d+[\+\-~]?次?$', '', text)
    text = re.sub(r'约\d+', '', text)
    text = re.sub(r'出现\d+', '', text)
    return text.strip()


def normalize(text):
    """标准化文本用于跨批次匹配 - 保留中文+英文单词"""
    text = _get_feature_name(text)
    cn = re.findall(r'[\u4e00-\u9fff]+', text)
    en = re.findall(r'[a-zA-Z]+', text)
    combined = ''.join(cn) + ' '.join(en).lower()
    return combined[:8]


def merge_language(reports):
    """合并语言特征，计算跨批次出现率"""
    feature_counter = Counter()
    feature_details = defaultdict(list)
    feature_canonical = {}  # 保存最长的原始表述
    
    for r in reports:
        seen_features = set()
        for item in r.get('language', []):
            # 提取特征名
            raw_feature = _get_feature_name(item)
            if raw_feature and len(raw_feature) >= 2:
                key = normalize(raw_feature)
                if not key:
                    continue
                seen_features.add(key)
                # 保留最简洁的原始表述作为展示名
                if key not in feature_canonical or len(raw_feature) < len(feature_canonical[key]):
                    feature_canonical[key] = raw_feature
                if item not in feature_details[key]:
                    feature_details[key].append(item)
        
        for f in seen_features:
            feature_counter[f] += 1
    
    total = len(reports)
    ranked = []
    
    for key, count in feature_counter.most_common():
        feature = feature_canonical.get(key, key)
        confidence = '高' if count >= total * 0.5 else ('中' if count >= total * 0.25 else '低')
        details = feature_details[key][:3]
        ranked.append({
            'feature': feature[:50],
            'batches': count,
            'total': total,
            'confidence': confidence,
            'details': details
        })
    
    return ranked


def merge_personality(reports):
    """合并人格/价值观片段，按出现次数排序"""
    pattern_counter = Counter()
    pattern_evidence = defaultdict(list)
    pattern_canonical = {}
    
    for r in reports:
        seen = set()
        for item in r.get('personality', []):
            # 提取核心观点
            core = item.split('——')[0].split('。')[0].strip()
            if core and len(core) >= 4:
                key = normalize(core)
                seen.add(key)
                if key not in pattern_canonical or len(core) > len(pattern_canonical[key]):
                    pattern_canonical[key] = core
                pattern_evidence[key].append(item)
        
        for k in seen:
            pattern_counter[k] += 1
    
    total = len(reports)
    ranked = []
    
    for key, count in pattern_counter.most_common():
        pattern = pattern_canonical.get(key, key)
        confidence = '高' if count >= total * 0.6 else ('中' if count >= total * 0.3 else '低')
        ranked.append({
            'pattern': pattern[:60],
            'batches': count,
            'total': total,
            'confidence': confidence,
            'evidence': pattern_evidence[key][:2]
        })
    
    return ranked


def merge_patterns(reports):
    """合并对话模式"""
    pattern_counter = Counter()
    pattern_canonical = {}
    
    for r in reports:
        seen = set()
        for item in r.get('patterns', []):
            core = item.split('——')[0].split('。')[0].strip()
            if core and len(core) >= 4:
                key = normalize(core)
                seen.add(key)
                if key not in pattern_canonical or len(core) > len(pattern_canonical[key]):
                    pattern_canonical[key] = core
        
        for k in seen:
            pattern_counter[k] += 1
    
    total = len(reports)
    ranked = []
    
    for key, count in pattern_counter.most_common():
        pattern = pattern_canonical.get(key, key)
        confidence = '高' if count >= total * 0.6 else ('中' if count >= total * 0.3 else '低')
        ranked.append({
            'pattern': pattern,
            'batches': count,
            'total': total,
            'confidence': confidence
        })
    
    return ranked


def merge_phrases(reports):
    """合并高频短语"""
    phrase_counter = Counter()
    phrase_canonical = {}
    
    for r in reports:
        for item in r.get('phrases', []):
            phrase = item.split(' - ')[0].split('(')[0].strip()
            if phrase and len(phrase) >= 2:
                key = normalize(phrase)
                phrase_counter[key] += 1
                if key not in phrase_canonical or len(phrase) > len(phrase_canonical[key]):
                    phrase_canonical[key] = phrase
    
    total = len(reports)
    return [{'phrase': phrase_canonical.get(p, p)[:30],
             'batches': c,
             'total': total,
             'confidence': '高' if c >= total * 0.6 else ('中' if c >= total * 0.3 else '低')}
            for p, c in phrase_counter.most_common(50)]


def merge_emotion(reports):
    """合并情绪倾向摘要"""
    summaries = []
    for r in reports:
        if r.get('emotion'):
            summaries.append(r['emotion'][:200])
    return summaries


def write_merged(merged, output_path):
    """写入合并报告"""
    lines = []
    lines.append("# 全量合并分析报告\n")
    lines.append(f"> 基于 {merged['total_reports']}/{merged['total_generated']} 批次分析\n")
    lines.append(f"> 覆盖消息: ~{merged['total_messages']:,} 条\n")
    lines.append("---\n")
    
    # 语言特征
    lines.append("## 语言特征（按置信度排序）\n")
    lines.append("| 特征 | 出现批次 | 置信度 |\n")
    lines.append("|------|---------|--------|\n")
    for item in merged['language'][:60]:
        bar = '█' * item['batches']
        lines.append(f"| {item['feature'][:40]} | {item['batches']}/{item['total']} {bar} | {item['confidence']} |\n")
    
    # 人格/价值观
    lines.append("\n---\n## 人格画像（按置信度排序）\n")
    for item in merged['personality'][:30]:
        conf_tag = {'高': '✅', '中': '📌', '低': '⚠️'}.get(item['confidence'], '')
        lines.append(f"\n### {conf_tag} [{item['confidence']}] {item['pattern'][:60]}\n")
        lines.append(f"- 出现批次: {item['batches']}/{item['total']}\n")
        for ev in item['evidence'][:2]:
            lines.append(f"- 证据: {ev[:100]}\n")
    
    # 对话模式
    lines.append("\n---\n## 对话模式\n")
    for item in merged['patterns'][:20]:
        conf_tag = {'高': '✅', '中': '📌', '低': '⚠️'}.get(item['confidence'], '')
        lines.append(f"- {conf_tag} [{item['confidence']}] {item['pattern'][:60]} ({item['batches']}/{item['total']})\n")
    
    # 高频短语
    lines.append("\n---\n## 高频短语 TOP 30\n")
    for item in merged['phrases'][:30]:
        lines.append(f"- {item['phrase'][:30]} ({item['batches']}/{item['total']}, {item['confidence']})\n")
    
    # 情绪倾向汇总
    lines.append("\n---\n## 情绪倾向汇总\n")
    for s in merged['emotion'][:5]:
        lines.append(f"- {s[:150]}\n")
    
    # 置信度说明
    lines.append("\n---\n## 置信度说明\n")
    lines.append("| 标签 | 含义 |\n")
    lines.append("|------|------|\n")
    lines.append("| ✅ 高 | 出现在 75-100% 批次中 — 稳定特征 |\n")
    lines.append("| 📌 中 | 出现在 40-74% 批次中 — 常见但非普适 |\n")
    lines.append("| ⚠️ 低 | 出现在 <40% 批次中 — 需进一步验证 |\n")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ 合并报告写入: {output_path}")
    print(f"📊 语言特征: {len(merged['language'])} 项")
    print(f"📊 人格画像: {len(merged['personality'])} 项")
    print(f"📊 对话模式: {len(merged['patterns'])} 项")
    print(f"📊 高频短语: {len(merged['phrases'])} 项")


def main():
    print("🔍 解析 mini 报告...")
    reports = parse_reports()
    print(f"📄 报告数: {len(reports)}")
    
    if not reports:
        print("⚠️  没有可用的报告，跳过合并")
        return
    
    merged = {
        'total_reports': len(reports),
        'total_generated': 12,
        'total_messages': 0,  # filled below
        'language': merge_language(reports),
        'personality': merge_personality(reports),
        'patterns': merge_patterns(reports),
        'phrases': merge_phrases(reports),
        'emotion': merge_emotion(reports),
    }
    
    # 估算总消息覆盖
    # 每批 ~2000 条 × 报告数
    merged['total_messages'] = len(reports) * 2000
    
    output_path = RAW_DIR / "merged_report.md"
    write_merged(merged, output_path)
    
    # 统计置信度分布
    conf_stats = defaultdict(int)
    for item in merged['language']:
        conf_stats[item['confidence']] += 1
    print(f"\n📊 置信度分布（语言特征）:")
    for level in ['高', '中', '低']:
        print(f"  {level}: {conf_stats.get(level, 0)} 项")


if __name__ == '__main__':
    main()
