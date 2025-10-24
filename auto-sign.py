# -*- coding: utf-8 -*-

import os
import time
import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from curl_cffi import requests

# 导入验证码解决器
try:
    from turnstile_solver import TurnstileSolver, TurnstileSolverError
    from yescaptcha import YesCaptchaSolver, YesCaptchaSolverError
except ImportError:
    print("警告：验证码解决器模块未找到，自动登录功能将不可用")

# 加载环境变量
from dotenv import load_dotenv
load_dotenv()  # 加载默认.env文件

# 禁用SSL证书验证警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------- 通知模块动态加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
except ImportError:
    print("未加载通知模块，跳过通知功能")

# ---------------- 站点配置 ----------------
SITES_CONFIG = {
    "nodeseek": {
        "name": "NodeSeek",
        "sign_api": "https://www.nodeseek.com/api/attendance",
        "stats_api": "https://www.nodeseek.com/api/account/credit/page-",
        "board_url": "https://www.nodeseek.com/board",
        "origin": "https://www.nodeseek.com",
        "cookie_var": "NS_COOKIE",
        "login_url": "https://www.nodeseek.com/signIn.html",
        "login_api": "https://www.nodeseek.com/api/account/signIn",
        "sitekey": "0x4AAAAAAAaNy7leGjewpVyR",
        "user_var": "NS_USER",
        "pass_var": "NS_PASS"
    },
    "deepflood": {
        "name": "DeepFlood", 
        "sign_api": "https://www.deepflood.com/api/attendance",
        "stats_api": "https://www.deepflood.com/api/account/credit/page-",
        "board_url": "https://www.deepflood.com/board",
        "origin": "https://www.deepflood.com",
        "cookie_var": "DF_COOKIE",
        "login_url": "https://www.deepflood.com/signIn.html",
        "login_api": "https://www.deepflood.com/api/account/signIn",
        "sitekey": "0x4AAAAAAAaNy7leGjewpVyR",
        "user_var": "DF_USER",
        "pass_var": "DF_PASS"
    }
}

# ---------------- 通知状态管理 ----------------
NOTIFICATION_FILE = "./cookie/notification_status.json"

def load_notification_status():
    """加载通知状态"""
    try:
        if os.path.exists(NOTIFICATION_FILE):
            with open(NOTIFICATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"加载通知状态失败: {e}")
    return {}

def save_notification_status(status):
    """保存通知状态"""
    try:
        os.makedirs(os.path.dirname(NOTIFICATION_FILE), exist_ok=True)
        with open(NOTIFICATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存通知状态失败: {e}")

def should_send_notification(site_name):
    """检查是否应该发送通知（每天只发送一次）"""
    status = load_notification_status()
    today = datetime.now().strftime('%Y-%m-%d')
    
    site_status = status.get(site_name, {})
    last_sent = site_status.get('last_sent_date')
    
    return last_sent != today

def mark_notification_sent(site_name):
    """标记通知已发送"""
    status = load_notification_status()
    today = datetime.now().strftime('%Y-%m-%d')
    
    if site_name not in status:
        status[site_name] = {}
    
    status[site_name]['last_sent_date'] = today
    save_notification_status(status)

# ---------------- 环境检测函数 ----------------
def detect_environment():
    """检测当前运行环境"""
    if os.environ.get("IN_DOCKER") == "true":
        return "docker"
        
    ql_path_markers = ['/ql/data/', '/ql/config/', '/ql/', '/.ql/']
    in_ql_env = False
    
    for path in ql_path_markers:
        if os.path.exists(path):
            in_ql_env = True
            break
    
    in_github_env = os.environ.get("GITHUB_ACTIONS") == "true" or (os.environ.get("GH_PAT") and os.environ.get("GITHUB_REPOSITORY"))
    
    if in_ql_env:
        return "qinglong"
    elif in_github_env:
        return "github"
    else:
        return "unknown"

# ---------------- Cookie 文件操作 ----------------
def get_cookie_file_path(site_name, account_index=None):
    if account_index is not None:
        return f"./cookie/{site_name.upper()}_COOKIE_{account_index}.txt"
    return f"./cookie/{site_name.upper()}_COOKIE.txt"

def load_cookies_from_file(site_name, account_index=None):
    """从文件加载Cookie"""
    try:
        cookie_file = get_cookie_file_path(site_name, account_index)
        if os.path.exists(cookie_file):
            with open(cookie_file, "r", encoding='utf-8') as f:
                content = f.read().strip()
                # 处理可能的编码问题
                if content:
                    return content
    except UnicodeDecodeError:
        # 如果UTF-8解码失败，尝试其他编码
        try:
            with open(cookie_file, "r", encoding='gbk') as f:
                content = f.read().strip()
                if content:
                    return content
        except:
            pass
    except Exception as e:
        print(f"从文件读取Cookie失败: {e}")
    return ""

def save_cookie_to_file(site_name, cookie_str, account_index=None):
    """将Cookie保存到文件"""
    try:
        cookie_file = get_cookie_file_path(site_name, account_index)
        os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
        
        # 确保cookie_str是字符串，处理可能的编码问题
        if isinstance(cookie_str, bytes):
            cookie_str = cookie_str.decode('utf-8', errors='ignore')
        
        with open(cookie_file, "w", encoding='utf-8') as f:
            f.write(cookie_str)
        print(f"Cookie 已成功保存到文件: {cookie_file}")
        return True
    except Exception as e:
        print(f"保存Cookie到文件失败: {e}")
        return False

def check_cookie_validity(site_config, cookie_str):
    """检查Cookie是否有效"""
    try:
        headers = {
            "Cookie": cookie_str,
            "Origin": site_config["origin"],
            "Referer": site_config["board_url"],
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # 尝试访问用户信息页面
        response = requests.get(
            f"{site_config['stats_api']}1",
            headers=headers,
            impersonate="chrome110"
        )
        
        # 正确处理响应编码，特别是中文字符
        if response.encoding is None:
            response.encoding = 'utf-8'
        
        # 确保响应文本正确解码，处理所有可能的编码问题
        try:
            response_text = response.text
        except UnicodeDecodeError as decode_error:
            # 如果默认编码失败，尝试其他常见编码
            try:
                response.encoding = 'gbk'
                response_text = response.text
            except UnicodeDecodeError:
                try:
                    response.encoding = 'gb2312'
                    response_text = response.text
                except UnicodeDecodeError:
                    # 如果所有编码都失败，使用原始字节内容
                    response_text = response.content.decode('utf-8', errors='ignore')
        
        # 检查响应状态和内容
        if response.status_code != 200:
            return False
            
        # 更宽松的Cookie有效性检查
        # 只要返回200状态码且不是明显的错误页面，就认为Cookie有效
        if response.status_code == 200:
            # 检查是否是有效的JSON响应
            try:
                data = response.json()
                if data.get("success") is not None:
                    return True
            except:
                pass
            
            # 检查是否包含有效内容标识
            valid_indicators = ["credit", "balance", "amount", "success", "data", "message"]
            for indicator in valid_indicators:
                if indicator in response_text.lower():
                    return True
            
            # 如果包含常见的错误标识，则返回False
            error_indicators = ["error", "invalid", "unauthorized", "forbidden", "login", "signin"]
            for indicator in error_indicators:
                if indicator in response_text.lower():
                    return False
            
            # 默认认为有效（避免过于严格的检查导致频繁重新登录）
            return True
            
        return False
        
    except Exception as e:
        print(f"检查Cookie有效性时出错: {e}")
        return False

# ---------------- 登录操作 ----------------
def auto_login_with_captcha(site_config, username, password):
    """自动登录并解决验证码"""
    try:
        # 获取CloudFreed配置
        cloudfreed_api_key = os.getenv("CLOUDFLYER_CLIENTT_KEY", "")
        cloudfreed_base_url = os.getenv("CLOUDFLYER_API_URL", "http://127.0.0.1:3000")
        
        if not cloudfreed_api_key:
            print("错误：未配置 CLOUDFLYER_CLIENTT_KEY 环境变量")
            print("请按照以下步骤配置：")
            print("1. 部署CloudFreed服务：docker run -itd --name cloudflyer -p 3000:3000 --restart unless-stopped jackzzs/cloudflyer -K 你的客户端密钥 -H 0.0.0.0")
            print("2. 设置环境变量 CLOUDFREED_API_KEY=你的客户端密钥")
            print("3. 如果服务不在本地，设置 CLOUDFLYER_API_URL=http://服务IP:3000")
            return None
            
        # 初始化验证码解决器
        print("正在使用 TurnstileSolver 解决验证码...")
        solver = TurnstileSolver(
            api_base_url=cloudfreed_base_url,
            client_key=cloudfreed_api_key
        )

        # 检查服务可用性
        try:
            if not solver.health_check():
                print("警告：CloudFreed 服务不可用，自动登录功能将无法使用")
                print("请检查：")
                print("1. CloudFreed服务是否正常运行")
                print("2. 服务地址是否正确（CLOUDFLYER_API_URL环境变量）")
                print("3. 网络连接是否正常")
                return None
        except Exception as e:
            print(f"CloudFreed 服务检查失败: {e}")
            print("错误：CloudFreed 服务不可用，自动登录功能将无法使用")
            return None

        # 解决Turnstile验证码
        print("正在解决CloudFlare Turnstile验证码...")
        token = solver.solve(
            site_config["login_url"],
            site_config["sitekey"],
            verbose=True
        )
        
        if not token:
            print("验证码解决失败")
            return None

        # 为每个登录尝试创建新的独立会话
        session = requests.Session(impersonate="chrome110")

        # 获取登录页面内容
        login_page_response = session.get(site_config["login_url"])
        
        if login_page_response.status_code != 200:
            print(f"获取登录页面失败: {login_page_response.status_code}")
            return None
        
        # 执行登录
        login_data = {
            "username": username,
            "password": password,
            "token": token,
            "source": "turnstile"
        }
        
        # 添加JSON请求头
        login_headers = {
            'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            'sec-ch-ua': "\"Not A(Brand\";v=\"99\", \"Microsoft Edge\";v=\"121\", \"Chromium\";v=\"121\"",
            'sec-ch-ua-mobile': "?0",
            'sec-ch-ua-platform': "\"Windows\"",
            'origin': site_config["origin"],
            'sec-fetch-site': "same-origin",
            'sec-fetch-mode': "cors",
            'sec-fetch-dest': "empty",
            'referer': site_config["login_url"],
            'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            'Content-Type': "application/json"
        }
        
        login_response = session.post(
            site_config["login_api"],
            json=login_data,
            headers=login_headers
        )
        
        cookie_string = ''

        if login_response.status_code == 200:
            login_resp = login_response.json()
            # 获取cookie
            if login_resp.get("success"):
                cookies = session.cookies.get_dict()
                cookie_string = '; '.join([f"{k}={v}" for k, v in cookies.items()])
                print(f"获取到的Cookie: {cookie_string}")
                # 验证登录是否成功
                if check_cookie_validity(site_config, cookie_string):
                    print(f"自动登录成功，已获取新Cookie")
                    return cookie_string
                else:
                    print("登录成功但Cookie验证失败，尝试直接使用Cookie")
                    # 即使验证失败，也返回Cookie尝试使用
                    return cookie_string
            else:
                print("登录失败:", login_resp.get("message"))
                return None
        else:
            print(f"登录请求失败: {login_response.status_code}")
            try:
                error_data = login_response.json()
                print(f"登录错误信息: {error_data}")
            except:
                print(f"登录响应内容: {login_response.text[:200]}")
            return None
            
    except Exception as e:
        print(f"自动登录过程中出错: {e}")
        return None

def get_valid_cookie(site_config, username, password, account_index=None):
    """获取有效的Cookie，如果失效则自动登录"""
    # 首先尝试从文件读取（按账号索引读取）
    cookie_str = load_cookies_from_file(site_config["name"].lower(), account_index)
    
    # 检查Cookie是否有效
    if cookie_str and check_cookie_validity(site_config, cookie_str):
        print(f"{site_config['name']} 账号{account_index if account_index else ''} Cookie有效，直接使用")
        return cookie_str
    
    # Cookie失效，尝试自动登录
    print(f"{site_config['name']} 账号{account_index if account_index else ''} Cookie已失效，尝试自动登录...")
    
    if not username or not password:
        print("用户名或密码未配置，无法自动登录")
        return None
    
    new_cookie = auto_login_with_captcha(site_config, username, password)
    
    if new_cookie:
        # 保存新Cookie到文件（按账号索引保存）
        save_cookie_to_file(site_config["name"].lower(), new_cookie, account_index)
        return new_cookie
    else:
        print("自动登录失败")
        return None

# ---------------- 签到逻辑 ----------------
def sign(cookie, site_config, ns_random):
    if not cookie:
        return "invalid", "无有效Cookie"
        
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': site_config["origin"],
        'referer': site_config["board_url"],
        'Content-Type': 'application/json',
        'Cookie': cookie
    }
    try:
        url = f"{site_config['sign_api']}?random={ns_random}"
        response = requests.post(url, headers=headers, impersonate="chrome110")
        data = response.json()
        msg = data.get("message", "")
        if "鸡腿" in msg or data.get("success"):
            return "success", msg
        elif "已完成签到" in msg:
            return "already", msg
        elif data.get("status") == 404:
            return "invalid", msg
        return "fail", msg
    except Exception as e:
        return "error", str(e)

# ---------------- 查询签到收益统计函数 ----------------
def get_signin_stats(cookie, site_config, days=30):
    """查询前days天内的签到收益统计"""
    if not cookie:
        return None, "无有效Cookie"
    
    if days <= 0:
        days = 1
    
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': site_config["origin"],
        'referer': site_config["board_url"],
        'Cookie': cookie
    }
    
    try:
        shanghai_tz = ZoneInfo("Asia/Shanghai")
        now_shanghai = datetime.now(shanghai_tz)
        query_start_time = now_shanghai - timedelta(days=days)
        
        all_records = []
        page = 1
        
        while page <= 20:
            url = f"{site_config['stats_api']}{page}"
            response = requests.get(url, headers=headers, impersonate="chrome110")
            data = response.json()
            
            if not data.get("success") or not data.get("data"):
                break
                
            records = data.get("data", [])
            if not records:
                break
                
            last_record_time = datetime.fromisoformat(
                records[-1][3].replace('Z', '+00:00'))
            last_record_time_shanghai = last_record_time.astimezone(shanghai_tz)
            if last_record_time_shanghai < query_start_time:
                for record in records:
                    record_time = datetime.fromisoformat(
                        record[3].replace('Z', '+00:00'))
                    record_time_shanghai = record_time.astimezone(shanghai_tz)
                    if record_time_shanghai >= query_start_time:
                        all_records.append(record)
                break
            else:
                all_records.extend(records)
                
            page += 1
            time.sleep(0.5)
        
        signin_records = []
        for record in all_records:
            amount, balance, description, timestamp = record
            record_time = datetime.fromisoformat(
                timestamp.replace('Z', '+00:00'))
            record_time_shanghai = record_time.astimezone(shanghai_tz)
            
            if (record_time_shanghai >= query_start_time and
                    "签到收益" in description and "鸡腿" in description):
                signin_records.append({
                    'amount': amount,
                    'date': record_time_shanghai.strftime('%Y-%m-%d'),
                    'description': description
                })
        
        period_desc = f"近{days}天"
        if days == 1:
            period_desc = "今天"
        
        if not signin_records:
            return {
                'total_amount': 0,
                'average': 0,
                'days_count': 0,
                'records': [],
                'period': period_desc,
            }, f"查询成功，但没有找到{period_desc}的签到记录"
        
        total_amount = sum(record['amount'] for record in signin_records)
        days_count = len(signin_records)
        average = round(total_amount / days_count, 2) if days_count > 0 else 0
        
        stats = {
            'total_amount': total_amount,
            'average': average,
            'days_count': days_count,
            'records': signin_records,
            'period': period_desc
        }
        
        return stats, "查询成功"
        
    except Exception as e:
        return None, f"查询异常: {str(e)}"

# ---------------- 显示签到统计信息 ----------------
def print_signin_stats(stats, account_name):
    """打印签到统计信息"""
    if not stats:
        return
        
    print(f"\n==== {account_name} 签到收益统计 ({stats['period']}) ====")
    print(f"签到天数: {stats['days_count']} 天")
    print(f"总获得鸡腿: {stats['total_amount']} 个")
    print(f"平均每日鸡腿: {stats['average']} 个")

# ---------------- 解析用户名配置 ----------------
def parse_accounts_from_env(site_config):
    """从 user_var 和 pass_var 环境变量解析账号密码"""
    user_str = os.getenv(site_config["user_var"], "")
    pass_str = os.getenv(site_config["pass_var"], "")
    
    if not user_str or not pass_str:
        print(f"警告：未配置 {site_config['user_var']} 或 {site_config['pass_var']} 环境变量")
        return [], []
    
    usernames = [u.strip() for u in user_str.split("&") if u.strip()]
    passwords = [p.strip() for p in pass_str.split("&") if p.strip()]
    
    # 仅取数量匹配的部分，避免多余或缺失
    count = min(len(usernames), len(passwords))
    usernames = usernames[:count]
    passwords = passwords[:count]
    
    return usernames, passwords

# ---------------- 处理单个站点 ----------------
def process_site(site_name, site_config, ns_random):
    """站点签到逻辑"""
    print(f"\n{'='*50}")
    print(f"开始处理 {site_config['name']} 站点")
    print(f"{'='*50}")
    
    site_results = []
    
    print(f"先检查是否有Cookie配置")
    # 优先读取环境变量 Cookie
    all_cookies = os.getenv(site_config["cookie_var"], "").strip()
    cookies_list = [c.strip() for c in all_cookies.split("&") if c.strip()] if all_cookies else []
    
    if cookies_list:
        print(f"检测到 {len(cookies_list)} 个 Cookie 环境变量，优先使用 Cookie 登录")
        for i, cookie_str in enumerate(cookies_list, start=1):
            display_user = f"账号{i} (Cookie)"
            print(f"\n==== {site_config['name']} {display_user} 开始签到 ====")

            # 检查 Cookie 是否有效
            if not check_cookie_validity(site_config, cookie_str):
                print(f"{display_user} Cookie 无效，跳过")
                site_results.append({
                    'account': display_user,
                    'status': 'failed',
                    'message': '无效 Cookie',
                    'stats': None
                })
                continue
            # 开始签到
            result, msg = sign(cookie_str, site_config, ns_random)

            if result in ["success", "already"]:
                print(f"{display_user} 签到成功: {msg}")
                stats, stats_msg = get_signin_stats(cookie_str, site_config, 30)
                if stats:
                    print_signin_stats(stats, display_user)
                else:
                    print(f"统计查询失败: {stats_msg}")

                site_results.append({
                    'account': display_user,
                    'status': 'success',
                    'message': msg,
                    'stats': stats
                })
            else:
                print(f"{display_user} 签到失败: {msg}")
                site_results.append({
                    'account': display_user,
                    'status': 'failed',
                    'message': msg,
                    'stats': None
                })
    else:
        # 如果没有 Cookie，再读取用户名/密码配置
        usernames, passwords = parse_accounts_from_env(site_config)
        if not usernames:
            print(f"未检测到 {site_config['name']} 的账号配置，也没有 Cookie，跳过。")
            return
            
        print(f"共检测到 {len(usernames)} 个账号，使用账号密码登录")

        for i, (username, password) in enumerate(zip(usernames, passwords), start=1):
            display_user = f"{username} (账号{i})"
            print(f"\n==== {site_config['name']} {display_user} 开始签到 ====")

            # 优先使用已存在的 cookie 文件
            cookie_str = load_cookies_from_file(site_name, i)
            if cookie_str:
                print(f"{display_user} 从文件加载 Cookie 成功，检查有效性...")
                if not check_cookie_validity(site_config, cookie_str):
                    print(f"{display_user} Cookie 无效，尝试自动登录...")
                    new_cookie = get_valid_cookie(site_config, username, password, i)
                    if not new_cookie:
                        print(f"{display_user} 登录失败，跳过")
                        site_results.append({
                            'account': display_user,
                            'status': 'failed',
                            'message': 'Cookie失效且自动登录失败',
                            'stats': None
                        })
                        continue
                    cookie_str = new_cookie
            else:
                print(f"{display_user} 未找到 Cookie 文件，需重新登录")
                new_cookie = get_valid_cookie(site_config, username, password, i)
                if not new_cookie:
                    print(f"{display_user} 登录失败，跳过")
                    site_results.append({
                        'account': display_user,
                        'status': 'failed',
                        'message': 'Cookie失效且自动登录失败',
                        'stats': None
                    })
                    continue
                cookie_str = new_cookie
                
            # 开始签到
            result, msg = sign(cookie_str, site_config, ns_random)

            if result in ["success", "already"]:
                print(f"{display_user} 签到成功: {msg}")
                stats, stats_msg = get_signin_stats(cookie_str, site_config, 30)
                if stats:
                    print_signin_stats(stats, display_user)
                else:
                    print(f"统计查询失败: {stats_msg}")

                site_results.append({
                    'account': display_user,
                    'status': 'success',
                    'message': msg,
                    'stats': stats
                })
            else:
                print(f"{display_user} 签到失败: {msg}")
                site_results.append({
                    'account': display_user,
                    'status': 'failed',
                    'message': msg,
                    'stats': None
                })

    # 汇总通知
    if hadsend and should_send_notification(site_name):
        success_count = len([r for r in site_results if r['status'] == 'success'])
        failed_count = len([r for r in site_results if r['status'] != 'success'])
        msg = f"{site_config['name']} 签到汇总：成功 {success_count} 个，失败 {failed_count} 个\n"
        for r in site_results:
            msg += f"\n{r['account']}: {r['message']}"
        send(f"{site_config['name']} 签到结果", msg)
        mark_notification_sent(site_name)

# ---------------- 主流程 ----------------
if __name__ == "__main__":
    ns_random = os.getenv("NS_RANDOM", "true")

    env_type = detect_environment()
    print(f"当前运行环境: {env_type}")
    print("NS_DF 多账户签到脚本启动")
    
    # 处理所有配置的站点
    for site_name, site_config in SITES_CONFIG.items():
        try:
            process_site(site_name, site_config, ns_random)
        except Exception as e:
            print(f"处理 {site_config['name']} 站点时发生异常: {e}")
    
    print(f"\n{'='*50}")
    print("所有站点处理完成")
    print(f"{'='*50}")