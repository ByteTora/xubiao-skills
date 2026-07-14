#!/usr/bin/env python3
"""
统计分析脚本
对清洗后的消息做词频、句长、emoji、时间、话题等统计

用法:
    python3 analyze_style.py [--input clean_messages.jsonl] [--output stats.json] [--top 100]
"""

import json
import re
import argparse
import math
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime

DEFAULT_INPUT = Path(__file__).resolve().parent.parent / "references" / "clean_messages.jsonl"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "references" / "stats.json"

# 停用词（常见无意义词）
STOPWORDS = set('的了是在有我和你就也不都而 but the that this is are was were 嗯 哦 啊 呢 吧 呀 哈 哼 额 啦 嘛 哎 唉 嘛 被 把 让 给 向 往 从 对 于 以 为 与 及 或 又 其 这 那 个 之 已 所 只 更 最 真 非常挺 太比较还虽然但是不过然后而且因为所以如果就一边一方面只是其实其实其实可可看看来起来出去回来上去下来过来进去出来过来一直已经正在将要刚刚忽然突然其实其实其实其实慢慢逐渐终于偶尔偶尔经常常常往往一再重新再又也又也又又又')

# 英文停用词
EN_STOPWORDS = {'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
                'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can',
                'a', 'an', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
                'we', 'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its',
                'our', 'their', 'and', 'but', 'or', 'not', 'no', 'so', 'if', 'then', 'else',
                'when', 'where', 'how', 'what', 'which', 'who', 'whom', 'why', 'all', 'each',
                'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such', 'only', 'own',
                'same', 'than', 'too', 'very', 'just', 'about', 'above', 'after', 'again'}


def load_messages(path):
    """加载 JSONL 消息"""
    msgs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                msgs.append(json.loads(line))
            except:
                continue
    return msgs


def basic_stats(msgs):
    """基本统计"""
    lengths = [len(m['msg']) for m in msgs]
    cn_counts = [len(re.findall(r'[\u4e00-\u9fff]', m['msg'])) for m in msgs]
    en_counts = [len(re.findall(r'[a-zA-Z]+', m['msg'])) for m in msgs]
    
    return {
        'total_messages': len(msgs),
        'total_chars': sum(lengths),
        'avg_length': round(sum(lengths) / len(lengths), 1),
        'median_length': sorted(lengths)[len(lengths) // 2],
        'max_length': max(lengths),
        'min_length': min(lengths),
        'avg_cn_chars': round(sum(cn_counts) / len(cn_counts), 1),
        'avg_en_words': round(sum(en_counts) / len(en_counts), 1),
        'length_distribution': {
            'very_short_1_5': sum(1 for l in lengths if 1 <= l <= 5),
            'short_6_10': sum(1 for l in lengths if 6 <= l <= 10),
            'medium_11_20': sum(1 for l in lengths if 11 <= l <= 20),
            'long_21_50': sum(1 for l in lengths if 21 <= l <= 50),
            'very_long_51_plus': sum(1 for l in lengths if l > 50),
        }
    }


def word_frequency(msgs, top_n=200):
    """词频统计（基于字符和词组）"""
    # 单字频次
    char_counter = Counter()
    # 双字组
    bigram_counter = Counter()
    # 英文单词
    en_counter = Counter()
    # 数字/字母开头的技术词
    tech_counter = Counter()
    
    for m in msgs:
        text = m['msg']
        
        # 中文字符
        cn_chars = re.findall(r'[\u4e00-\u9fff]', text)
        char_counter.update(cn_chars)
        
        # 双字组
        cn_text = ''.join(re.findall(r'[\u4e00-\u9fff]+', text))
        for i in range(len(cn_text) - 1):
            bigram = cn_text[i:i+2]
            bigram_counter[bigram] += 1
        
        # 英文单词
        en_words = re.findall(r'[a-zA-Z]+', text.lower())
        for w in en_words:
            if w not in EN_STOPWORDS and len(w) >= 2:
                en_counter[w] += 1
        
        # 技术术语（驼峰/连字符/数字混合）
        tech = re.findall(r'[a-zA-Z]+[\d._-]+[\w]*|[\d._-]+[a-zA-Z]+[\w]*', text)
        for t in tech:
            tech_counter[t.lower()] += 1
    
    # 过滤停用字
    filtered_chars = [(c, n) for c, n in char_counter.most_common(top_n * 2) if c not in STOPWORDS]
    
    return {
        'top_chars': filtered_chars[:top_n],
        'top_bigrams': bigram_counter.most_common(top_n),
        'top_english': en_counter.most_common(top_n),
        'top_tech_terms': tech_counter.most_common(top_n),
    }


def punctuation_stats(msgs):
    """标点符号统计"""
    total = len(msgs)
    punct_counts = Counter()
    punct_by_msg = defaultdict(int)
    
    for m in msgs:
        text = m['msg']
        # 各类标点
        periods = text.count('。')
        commas = text.count('，')
        exclams = text.count('！')
        questions = text.count('？')
        ellipsis = text.count('…') + text.count('...')
        semicolons = text.count('；')
        colons = text.count('：')
        dashes = text.count('—') + text.count('-')
        hashtags = text.count('#')
        at_signs = text.count('@')
        brackets = text.count('[') + text.count('(')
        
        counts = {
            'period': periods, 'comma': commas, 'exclam': exclams,
            'question': questions, 'ellipsis': ellipsis, 'semicolon': semicolons,
            'colon': colons, 'dash': dashes, 'hashtag': hashtags,
            'at': at_signs, 'bracket': brackets
        }
        
        for k, v in counts.items():
            punct_counts[k] += v
            if v > 0:
                punct_by_msg[k] += 1
    
    return {
        'total_counts': dict(punct_counts.most_common()),
        'usage_rate': {k: round(v / total * 100, 1) for k, v in sorted(punct_by_msg.items(), key=lambda x: -x[1])}
    }


def emoji_stats(msgs):
    """Emoji 统计"""
    #微信自定义表情 [xxx] 和 Unicode emoji
    custom_emoji = Counter()
    unicode_emoji = Counter()
    
    emoji_pattern = re.compile(
        r'\[([^\[\]]+)\]|'
        r'[\U0001F300-\U0001F9FF]|'
        r'[\U00002600-\U000027BF]|'
        r'[\U0001F600-\U0001F64F]|'
        r'[\U0001F680-\U0001F6FF]'
    )
    
    for m in msgs:
        text = m['msg']
        for match in emoji_pattern.finditer(text):
            if match.group(1):
                custom_emoji[match.group(1)] += 1
            else:
                unicode_emoji[match.group(0)] += 1
    
    return {
        'custom_emoji_top': custom_emoji.most_common(50),
        'unicode_emoji_top': unicode_emoji.most_common(50),
        'total_custom': sum(custom_emoji.values()),
        'total_unicode': sum(unicode_emoji.values()),
    }


def time_stats(msgs):
    """时间模式统计"""
    hours = Counter()
    weekdays = Counter()
    months = Counter()
    years = Counter()
    
    for m in msgs:
        ts = m.get('ts', 0)
        if ts <= 0:
            continue
        dt = datetime.fromtimestamp(ts)
        hours[dt.hour] += 1
        weekdays[dt.weekday()] += 1
        months[dt.month] += 1
        years[dt.year] += 1
    
    # 时间段分类
    time_slots = {
        'late_night': sum(hours.get(h, 0) for h in range(0, 6)),    # 0-5
        'morning': sum(hours.get(h, 0) for h in range(6, 12)),       # 6-11
        'afternoon': sum(hours.get(h, 0) for h in range(12, 18)),    # 12-17
        'evening': sum(hours.get(h, 0) for h in range(18, 24)),     # 18-23
    }
    
    # 计算回复间隔（模拟：按时间排序后的差值）
    # 这里只统计活跃时段
    
    return {
        'hour_distribution': dict(sorted(hours.items())),
        'time_slots': time_slots,
        'weekday_distribution': {k: v for k, v in sorted(weekdays.items())},
        'weekday_names': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
        'month_distribution': dict(sorted(months.items())),
        'year_distribution': dict(sorted(years.items())),
        'peak_hour': max(hours, key=hours.get) if hours else None,
        'peak_weekday': max(weekdays, key=weekdays.get) if weekdays else None,
    }


def sentence_patterns(msgs):
    """句式分析"""
    patterns = Counter()
    
    for m in msgs:
        text = m['msg'].strip()
        if not text:
            continue
        
        # 以问号结尾 → 问句
        if text.endswith('？') or text.endswith('?'):
            patterns['question'] += 1
        # 以感叹号结尾 → 感叹句
        elif text.endswith('！') or text.endswith('!'):
            patterns['exclamation'] += 1
        # 以句号结尾 → 陈述句
        elif text.endswith('。'):
            patterns['statement_period'] += 1
        # 无标点/其他
        else:
            patterns['no_punct'] += 1
        
        # 特殊句式
        if text.startswith('我'):
            patterns['start_with_wo'] += 1
        if text.startswith('你'):
            patterns['start_with_ni'] += 1
        if '？' in text and text.index('？') < len(text) - 1:
            patterns['multi_question'] += 1
        if re.search(r'(.{2,})\1{2,}', text):
            patterns['repetition'] += 1  # 啊啊啊啊
        if re.search(r'(.)\1{4,}', text):
            patterns['char_repeat'] += 1  # 哈哈哈哈哈
        if text.count('，') >= 3:
            patterns['long_sentence'] += 1
    
    total = len(msgs)
    return {
        'counts': dict(patterns.most_common()),
        'rates': {k: round(v / total * 100, 1) for k, v in patterns.most_common()}
    }


def topic_keywords(msgs):
    """话题关键词（简单 TF 方法）"""
    # 预定义话题类别
    topic_words = {
        'work': ['工作', '项目', '公司', '老板', '同事', '工资', '加班', '出差', '汇报', '开会', '方案', '客户', '产品', '需求', '开发', '测试', '上线', '架构', '代码', '技术', '算法', '模型', '服务器', '数据库', '部署', '接口', '优化', 'bug', '修复', '评审', '进度', '排期', 'kpi', 'okr', '年终', '晋升', '面试', '简历', '跳槽', '涨薪', 'offer', 'hr', 'github', 'python', 'java', 'llm', 'ai', 'api', 'mcp', 'agent', 'rag'],
        'life': ['吃', '喝', '玩', '睡', '觉', '饭', '外卖', '做饭', '买菜', '超市', '健身', '跑步', '运动', '体检', '医院', '药', '头发', '衣服', '鞋', '搬家', '装修', '租房', '房贷', '公积金', '社保', '驾照', '买车', '打车', '地铁', '公交', '快递', '退货', '淘宝', '京东', '拼多多', '抖音'],
        'social': ['朋友', '同学', '老师', '师哥', '师姐', '师弟', '师妹', '宿舍', '班级', '导师', '实验室', '课题组', '论文', '毕业', '答辩', '考研', '考公', '体制内', '编制', '教师', '公务员', '事业编', '国企', '银行'],
        'emotion': ['开心', '高兴', '快乐', '兴奋', '感动', '舒服', '爽', '棒', '赞', '牛', '厉害', '哈哈', '666', '哈哈哈', '哈哈哈哈', '牛逼', '卧槽', '我去', '哎呀', '无语', '烦', '累', '崩溃', '焦虑', '压力', '抑郁', '孤独', '寂寞', 'emo', '摆烂', '躺平', '佛系', '死', '哭', '难受'],
        'relationship': ['恋爱', '对象', '男票', '女票', '老公', '老婆', '相亲', '催婚', '结婚', '离婚', '单身', '脱单', '表白', '分手', '复合', '暗恋', '暧昧', '喜欢', '爱', '想你了', '约会', '打扮', '漂亮', '帅'],
        'money': ['钱', '工资', '收入', '支出', '存款', '理财', '基金', '股票', '亏损', '涨了', '跌了', '贷款', '还款', '利息', '月供', '房租', '水电', '话费', '红包', '转账', '借钱', '还钱', '账', '欠', '税', '报销', '发票'],
        'tech': ['模型', '训练', '微调', 'finetune', 'lora', 'gpu', 'cuda', 'pytorch', 'tensorflow', 'huggingface', 'transformers', 'bert', 'gpt', 'llama', 'qwen', 'deepseek', 'claude', 'openai', 'embedding', 'vector', 'rag', 'agent', 'mcp', 'prompt', 'token', 'context', 'inference', 'deploy', 'api'],
    }
    
    topic_counts = {}
    for topic, words in topic_words.items():
        count = 0
        for m in msgs:
            text = m['msg'].lower()
            if any(w in text for w in words):
                count += 1
        topic_counts[topic] = count
    
    total = len(msgs)
    return {k: {'count': v, 'rate': round(v / total * 100, 1)} for k, v in sorted(topic_counts.items(), key=lambda x: -x[1])}


def high_frequency_phrases(msgs, top_n=100):
    """高频短语/口头禅（4字以内重复模式）"""
    phrase_counter = Counter()
    
    for m in msgs:
        text = m['msg'].strip()
        cn_parts = re.findall(r'[\u4e00-\u9fff]+', text)
        for part in cn_parts:
            # 2-4 字片段
            for length in range(2, min(5, len(part) + 1)):
                for i in range(len(part) - length + 1):
                    phrase = part[i:i+length]
                    if phrase not in STOPWORDS:
                        phrase_counter[phrase] += 1
    
    # 过滤低频和单字
    return [(p, c) for p, c in phrase_counter.most_common(top_n * 3) if c >= 10 and len(p) >= 2][:top_n]


def main():
    parser = argparse.ArgumentParser(description='聊天风格统计分析')
    parser.add_argument('--input', type=str, default=str(DEFAULT_INPUT))
    parser.add_argument('--output', type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument('--top', type=int, default=200)
    parser.add_argument('--pretty', action='store_true', help='打印可读报告')
    args = parser.parse_args()
    
    msgs = load_messages(args.input)
    print(f"📊 加载消息: {len(msgs):,}")
    
    print("🔍 基本统计...")
    stats = {
        'basic': basic_stats(msgs),
        'word_freq': word_frequency(msgs, args.top),
        'punctuation': punctuation_stats(msgs),
        'emoji': emoji_stats(msgs),
        'time': time_stats(msgs),
        'sentence': sentence_patterns(msgs),
        'topics': topic_keywords(msgs),
        'phrases': high_frequency_phrases(msgs, args.top),
    }
    
    # 输出 JSON
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 统计输出: {output_path}")
    
    if args.pretty:
        print("\n" + "=" * 60)
        print("📊 聊天风格统计报告")
        print("=" * 60)
        b = stats['basic']
        print(f"\n📏 消息规模")
        print(f"  总条数: {b['total_messages']:,}")
        print(f"  平均长度: {b['avg_length']} 字 | 中位: {b['median_length']} 字")
        print(f"  中文密度: {b['avg_cn_chars']} 字/条 | 英文: {b['avg_en_words']} 词/条")
        
        print(f"\n📏 长度分布")
        for k, v in b['length_distribution'].items():
            pct = round(v / b['total_messages'] * 100, 1)
            bar = '█' * int(pct / 2)
            print(f"  {k}: {v:>6,} ({pct}%) {bar}")
        
        print(f"\n📝 高频词（TOP 20）")
        for w, c in stats['word_freq']['top_bigrams'][:20]:
            print(f"  {w}: {c}")
        
        print(f"\n🎯 话题分布")
        for t, v in stats['topics'].items():
            bar = '█' * int(v['rate'] / 2)
            print(f"  {t}: {v['rate']}% {bar}")
        
        print(f"\n⏰ 活跃时段")
        t = stats['time']
        for slot, count in t['time_slots'].items():
            pct = round(count / b['total_messages'] * 100, 1)
            print(f"  {slot}: {pct}%")
        print(f"  高峰小时: {t['peak_hour']}时")


if __name__ == '__main__':
    main()
