#!/usr/bin/env python3
"""
微信聊天记录清洗脚本 v3 (corrected)
从原始 message_*.db 提取「我」发的单人纯文本消息

识别逻辑（基于 extract_messages.py 验证）:
- 原始 DB 的 Name2Id 表: rowid → username
- 我的 wxid: wxid_wkzdhxukyjk622, Name2Id rowid=5
- 我的消息: real_sender_id == my_Name2Id_rowid
- type=1 明文 / type=21474836529 需 ZSTD 解压

用法:
    python3 build_dataset.py [--output clean_messages.jsonl]
"""

import sqlite3
import re
import json
import argparse
import hashlib
import zstandard
from pathlib import Path
from datetime import datetime

# 路径配置
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # she-love-me/
DECRYPTED_DIR = PROJECT_ROOT / "vendor" / "wechat-decrypt" / "decrypted"
CONSOLIDATED_DB = PROJECT_ROOT / "vendor" / "wechat-decrypt" / "consolidated" / "consolidated.db"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "references" / "clean_messages.jsonl"

ZSTD_MAGIC = b'\x28\xb5\x2f\xfd'

# 正则预编译
RE_PHONE = re.compile(r'1[3-9]\d{9}')
RE_ID_CARD = re.compile(r'\d{17}[\dXx]|\d{15}')
RE_BANK_CARD = re.compile(r'\d{16,19}')
RE_URL = re.compile(r'(https?://[^\s]+)')
RE_WXID = re.compile(r'wxid_\w+')
RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

MY_WXID = 'wxid_wkzdhxukyjk622'


def md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def get_own_wxid():
    """从 config.json 提取自己的 wxid"""
    config_path = PROJECT_ROOT / "vendor" / "wechat-decrypt" / "config.json"
    if config_path.exists():
        try:
            with open(config_path, encoding='utf-8') as f:
                cfg = json.load(f)
            db_dir = cfg.get("db_dir", "")
            if db_dir:
                m = re.search(r'wxid_[a-zA-Z0-9]+', db_dir.replace('\\', '/'))
                if m:
                    return m.group(0)
        except:
            pass
    return MY_WXID  # fallback


def load_contacts_from_consolidated(conn):
    """从 consolidated.db 加载联系人信息"""
    c = conn.cursor()
    
    # 群聊 room_id → md5
    c.execute("SELECT room_id FROM rooms")
    group_md5s = {md5(r[0]) for r in c.fetchall()}
    
    # 个人好友 username → md5 (local_type=3 = 真实个人好友)
    c.execute("""
        SELECT username FROM contacts 
        WHERE local_type IN (3, 0, 1)
          AND verify_flag != 8
          AND username NOT LIKE 'gh_%'
          AND username NOT LIKE '%@openim'
    """)
    contact_md5s = {md5(r[0]) for r in c.fetchall()}
    
    # 企业/公众号（排除）
    c.execute("""
        SELECT username FROM contacts 
        WHERE local_type IN (5, 6, 7) 
           OR verify_flag = 8
           OR username LIKE 'gh_%'
           OR username LIKE '%@openim'
    """)
    biz_usernames = {r[0] for r in c.fetchall()}
    biz_md5s = {md5(u) for u in biz_usernames}
    
    return group_md5s, contact_md5s, biz_md5s


def load_name2id(conn):
    """从 Name2Id 表加载 real_sender_id → username 映射"""
    mapping = {}
    try:
        for rowid, username in conn.execute("SELECT rowid, user_name FROM Name2Id"):
            if username:
                mapping[rowid] = username
    except sqlite3.OperationalError:
        pass
    return mapping


def decompress_content(content, ct):
    """
    ZSTD 解压
    ct == 4 表示 ZSTD 压缩（WCDB 框架的标准）
    有些无 WCDB_CT_message_content 列的旧版数据库直接存 ZSTD 帧
    """
    if not content:
        return b''
    if isinstance(content, str):
        return content.encode('utf-8')
    
    # Method 1: WCDB_CT_message_content == 4
    if ct == 4:
        try:
            dctx = zstandard.ZstdDecompressor()
            return dctx.decompress(content)
        except:
            pass
    
    # Method 2: 检测 ZSTD magic
    if len(content) >= 4 and content[:4] == ZSTD_MAGIC:
        try:
            dctx = zstandard.ZstdDecompressor()
            return dctx.decompress(content)
        except:
            pass
    
    return content


def is_text_content(text):
    """判断是否为有效纯文本（排除 XML/voip/系统消息）"""
    if not text:
        return False
    
    text = text.strip()
    if len(text) < 2:
        return False
    
    # XML 根结构 → 结构化消息
    if text.startswith('<msg>') or text.startswith('<?xml') or text.startswith('<voip'):
        return False
    
    # 系统消息
    if '以上是打招呼的消息' in text or '已添加了' in text:
        return False
    
    # XML 标签占比过高
    tag_chars = len(re.findall(r'<[^>]+>', text))
    if len(text) > 0 and tag_chars / len(text) > 0.3:
        return False
    
    # 最少有 2 个中文字 或 3+ 英文字母词
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    if cn_chars < 2 and not re.search(r'[a-zA-Z]{3,}', text):
        return False
    
    return True


def desensitize(text):
    """脱敏处理"""
    if not text:
        return text
    
    text = RE_PHONE.sub('[电话]', text)
    text = RE_ID_CARD.sub('[证件]', text)
    text = RE_BANK_CARD.sub('[银行卡]', text)
    text = RE_EMAIL.sub('[邮箱]', text)
    text = RE_WXID.sub('[微信号]', text)
    
    def trunc_url(m):
        from urllib.parse import urlparse
        try:
            return f"[{urlparse(m.group(1)).netloc}]"
        except:
            return '[链接]'
    text = RE_URL.sub(trunc_url, text)
    
    return text


def main():
    parser = argparse.ArgumentParser(description='微信聊天记录清洗 v3')
    parser.add_argument('--output', type=str, default=str(DEFAULT_OUTPUT))
    parser.add_argument('--min-self', type=int, default=20, help='会话中我的消息最少条数')
    parser.add_argument('--limit', type=int, default=0, help='最多输出条数')
    parser.add_argument('--stats-only', action='store_true')
    args = parser.parse_args()
    
    own_wxid = get_own_wxid()
    print(f"👤 我的 wxid: {own_wxid}")
    
    # 加载群聊/联系人 md5 集合
    conn = sqlite3.connect(str(CONSOLIDATED_DB))
    group_md5s, contact_md5s, biz_md5s = load_contacts_from_consolidated(conn)
    conn.close()
    
    print(f"👥 群聊(md5): {len(group_md5s)}")
    print(f"👤 联系人(md5): {len(contact_md5s)}")
    print(f"🏢 排除企业(md5): {len(biz_md5s)}")
    
    # 扫描原始 message_*.db
    message_dir = DECRYPTED_DIR / 'message'
    message_dbs = sorted(message_dir.glob('message_*.db'))
    print(f"📂 原始数据库: {len(message_dbs)} 个")
    
    results = []
    conv_stats = {}
    total_my_msgs = 0
    
    for db_path in message_dbs:
        if 'biz' in db_path.name:
            continue  # 跳过企业消息库
        
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        
        # 加载 Name2Id 映射
        name2id = load_name2id(conn)
        my_sender_ids = {rid for rid, uid in name2id.items() if uid == own_wxid}
        
        if not my_sender_ids:
            conn.close()
            continue
        
        # 获取所有 Msg 表
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'")
        tables = [r[0] for r in c.fetchall()]
        
        for table in tables:
            conv_md5 = table[4:]  # 去掉 'Msg_' 前缀
            
            # 过滤群聊
            if conv_md5 in group_md5s:
                continue
            # 过滤企业/公众号
            if conv_md5 in biz_md5s:
                continue
            # 只保留 1-on-1（联系人集合中）
            if conv_md5 not in contact_md5s:
                continue
            
            # 提取我的消息
            try:
                # Check if WCDB_CT_message_content column exists
                cols = [row[1] for row in c.execute(f'PRAGMA table_info(\"{table}\")').fetchall()]
                has_wcdb = 'WCDB_CT_message_content' in cols
                
                if has_wcdb:
                    rows = c.execute(
                        f'SELECT real_sender_id, local_type, message_content, '
                        f'WCDB_CT_message_content, create_time FROM \"{table}\"'
                    ).fetchall()
                else:
                    rows = c.execute(
                        f'SELECT real_sender_id, local_type, message_content, '
                        f'NULL as wcdb_ct, create_time FROM \"{table}\"'
                    ).fetchall()
            except Exception as e:
                print(f"  [!] 读取 {table} 失败: {e}")
                continue
            
            conv_self = 0
            conv_total = len(rows)
            
            for row in rows:
                real_sender_id = row[0]
                local_type = row[1]
                content = row[2]
                wcdb_ct = row[3]
                create_time = row[4]
                
                # 只处理我的消息
                if real_sender_id not in my_sender_ids:
                    continue
                
                # 只处理文本消息
                # local_type=1: 文本（可能压缩或不压缩）
                # local_type=21474836529(0x80000001): 已发送文本（ZSTD压缩）
                base_type = local_type & 0x7FFFFFFF
                if base_type != 1:
                    continue
                
                if not content:
                    continue
                
                # 解压
                if isinstance(content, bytes):
                    raw = decompress_content(content, wcdb_ct if has_wcdb else 0)
                    if raw == content:
                        # 解压后无变化，尝试直接解码
                        try:
                            text = content.decode('utf-8', errors='replace')
                        except:
                            continue
                    else:
                        try:
                            text = raw.decode('utf-8', errors='replace')
                        except:
                            continue
                elif isinstance(content, str):
                    text = content
                else:
                    continue
                
                text = text.strip()
                
                # 过滤非纯文本
                if not is_text_content(text):
                    continue
                
                # 脱敏
                text = desensitize(text)
                if len(text) < 2:
                    continue
                
                ts = create_time if create_time else 0
                results.append({
                    'msg': text,
                    'conv': conv_md5[:8],
                    'ts': ts,
                    'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d') if ts > 0 else 'unknown'
                })
                conv_self += 1
                total_my_msgs += 1
            
            conv_stats[conv_md5[:8]] = {'total': conv_total, 'self': conv_self}
        
        conn.close()
    
    print(f"✅ 我的消息总计: {total_my_msgs:,}")
    
    # 过滤：我的消息 >= min_self 的会话
    if args.min_self > 0:
        final = [r for r in results if conv_stats.get(r['conv'], {}).get('self', 0) >= args.min_self]
        removed = len(results) - len(final)
        if removed > 0:
            print(f"🚫 剔除 < {args.min_self} 条自己的会话: {removed:,}")
        results = final
    
    if args.limit > 0:
        results = results[:args.limit]
    
    # 输出
    if args.stats_only:
        dates = [r['date'] for r in results if r['date'] != 'unknown']
        print(f"\n📊 消息数: {len(results):,}")
        print(f"📊 会话数: {len(set(r['conv'] for r in results))}")
        if dates:
            print(f"📅 日期: {min(dates)} ~ {max(dates)}")
        return
    
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    
    print(f"\n✅ 输出: {output_path}")
    print(f"📊 消息数: {len(results):,}")
    print(f"📊 会话数: {len(set(r['conv'] for r in results))}")
    
    dates = [r['date'] for r in results if r['date'] != 'unknown']
    if dates:
        print(f"📅 日期: {min(dates)} ~ {max(dates)}")
        year_counts = {}
        for d in dates:
            year_counts[d[:4]] = year_counts.get(d[:4], 0) + 1
        print("\n📈 年份:")
        mc = max(year_counts.values()) if year_counts else 1
        for yr in sorted(year_counts.keys()):
            bar = '█' * (year_counts[yr] // max(1, mc // 40))
            print(f"  {yr}: {year_counts[yr]:>6,} {bar}")


if __name__ == '__main__':
    main()
