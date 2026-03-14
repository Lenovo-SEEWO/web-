from flask import Flask, request, jsonify, session, redirect, url_for, make_response
import hmac
import hashlib
import base64
import json
import time

def generate_token(data, secret_key, expires_in=None):
    """生成签名令牌"""
    payload = data.copy()
    if expires_in:
        payload['exp'] = time.time() + expires_in
    
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
    
    signature = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode()
    
    return "{}.{}".format(payload_b64, signature_b64)

def verify_token(token, secret_key):
    """验证令牌，返回数据或None"""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None, None
        
        payload_b64, signature_b64 = parts
        
        expected_signature = hmac.new(secret_key.encode(), payload_b64.encode(), hashlib.sha256).digest()
        expected_signature_b64 = base64.urlsafe_b64encode(expected_signature).decode()
        
        if not hmac.compare_digest(signature_b64, expected_signature_b64):
            return None, None
        
        payload_json = base64.urlsafe_b64decode(payload_b64.encode()).decode()
        payload = json.loads(payload_json)
        
        if 'exp' in payload:
            if time.time() > payload['exp']:
                return None, 'expired'
        
        return payload, None
    except Exception:
        return None, None
from flask_socketio import SocketIO, emit
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess
import logging
import threading
from datetime import datetime, timedelta
import os
import socket
import time
import psutil
import json
import uuid
import webbrowser
import signal
import sys
import select
import random
import re
from functools import wraps

# 用户数据文件
USERS_DATA_FILE = "users.json"
# 用户计数器文件
USER_COUNTER_FILE = "user_counter.json"
# 可用用户名池文件
AVAILABLE_USERNAMES_FILE = "available_usernames.json"
# 每日注册次数限制文件
REGISTER_COUNT_FILE = "register_count.json"
# 每天最大注册次数
MAX_DAILY_REGISTRATION = 3
# 线程锁
user_lock = threading.Lock()
register_count_lock = threading.Lock()

# 控制台刷新配置
console_refresh_enabled = True
console_refresh_interval = 20  # 秒
console_refresh_thread = None
console_last_refresh = None

# 申请理由配置
MAX_REASON_LENGTH = 200

def load_user_counter():
    """加载用户计数器，返回下一个可用的用户序号"""
    try:
        if os.path.exists(USER_COUNTER_FILE):
            with open(USER_COUNTER_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('next_id', 1)
    except Exception as e:
        logger.error("加载用户计数器失败: {}".format(e))
    return 1

def save_user_counter(next_id):
    """保存用户计数器"""
    try:
        with open(USER_COUNTER_FILE, 'w', encoding='utf-8') as f:
            json.dump({'next_id': next_id}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("保存用户计数器失败: {}".format(e))

def get_next_username():
    """获取下一个可用的用户名（仅生成，不保存）"""
    with user_lock:
        try:
            if os.path.exists(USER_COUNTER_FILE):
                with open(USER_COUNTER_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    next_id = data.get('next_id', 1)
            else:
                next_id = 1
            
            if next_id > 999999999:
                raise RuntimeError("用户数量已达上限")
            
            username = "用户{:09d}".format(next_id)
            return username, next_id
        except Exception as e:
            logger.error("获取下一个用户名失败: {}".format(e))
            return None, None

def increment_user_counter():
    """增加用户计数器（注册成功后调用）"""
    with user_lock:
        try:
            if os.path.exists(USER_COUNTER_FILE):
                with open(USER_COUNTER_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    next_id = data.get('next_id', 1) + 1
            else:
                next_id = 2
            
            with open(USER_COUNTER_FILE, 'w', encoding='utf-8') as f:
                json.dump({'next_id': next_id}, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error("增加用户计数器失败: {}".format(e))
            return False

def load_available_usernames():
    """加载可用用户名池"""
    try:
        if os.path.exists(AVAILABLE_USERNAMES_FILE):
            with open(AVAILABLE_USERNAMES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error("加载可用用户名池失败: {}".format(e))
    return []

def save_available_usernames(usernames):
    """保存可用用户名池"""
    try:
        with open(AVAILABLE_USERNAMES_FILE, 'w', encoding='utf-8') as f:
            json.dump(usernames, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("保存可用用户名池失败: {}".format(e))

def load_register_count():
    """加载当日注册计数"""
    try:
        if os.path.exists(REGISTER_COUNT_FILE):
            with open(REGISTER_COUNT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                today = datetime.now().strftime('%Y-%m-%d')
                if data.get('date') == today:
                    return data.get('count', 0)
                else:
                    return 0
    except Exception as e:
        logger.error("加载注册计数失败: {}".format(e))
    return 0

def save_register_count(count):
    """保存当日注册计数"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        with open(REGISTER_COUNT_FILE, 'w', encoding='utf-8') as f:
            json.dump({'date': today, 'count': count}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("保存注册计数失败: {}".format(e))

def allocate_username():
    """分配一个新用户名（优先从可用池取，否则计数器生成）"""
    with user_lock:
        available = load_available_usernames()
        if available:
            username = available.pop(0)
            save_available_usernames(available)
            logger.info("从可用池分配用户名: {}".format(username))
            return username
        
        next_id = load_user_counter()
        if next_id > 999999999:
            raise RuntimeError("用户数量已达上限")
        username = "用户{:09d}".format(next_id)
        save_user_counter(next_id + 1)
        logger.info("新生成用户名: {}".format(username))
        return username

def recycle_username(username):
    """回收用户名（放入可用池）"""
    global ADMIN_USERNAME
    if username == ADMIN_USERNAME:
        return
    
    with user_lock:
        available = load_available_usernames()
        if username not in available:
            available.append(username)
            save_available_usernames(available)
            logger.info("回收用户名: {}".format(username))

def load_users():
    """加载所有用户数据"""
    try:
        if os.path.exists(USERS_DATA_FILE):
            with open(USERS_DATA_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
                for user in users:
                    if 'is_admin' not in user:
                        user['is_admin'] = False
                return users
    except Exception as e:
        logger.error("加载用户数据失败: {}".format(e))
    return []

def save_users(users):
    """保存用户数据"""
    try:
        with open(USERS_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error("保存用户数据失败: {}".format(e))
        return False

def register_user(username, password, ip):
    """注册新用户（线程安全）"""
    try:
        users = load_users()
        
        for user in users:
            if user['username'] == username:
                logger.warning("注册失败：用户名 {} 已存在（二次检查）".format(username))
                return False, "用户名已存在"
        
        password_hash = generate_password_hash(password)
        
        new_user = {
            'username': username,
            'password_hash': password_hash,
            'register_time': datetime.now().isoformat(),
            'register_ip': ip,
            'last_login': None,
            'last_ip': None,
            'banned': False,
            'ban_expire': None,
            'banned_reason': None,
            'is_admin': False
        }
        users.append(new_user)
        
        if save_users(users):
            logger.info("用户注册成功: {}, IP: {}".format(username, ip))
            return True, "注册成功"
        else:
            logger.error("保存用户失败: {}".format(username))
            return False, "保存用户失败"
    except Exception as e:
        logger.error("注册用户异常: {}".format(e))
        return False, "注册异常: {}".format(str(e))

def verify_user(username, password):
    """验证用户登录"""
    users = load_users()
    for user in users:
        if user['username'] == username:
            if user.get('banned', False):
                expire = user.get('ban_expire')
                reason = user.get('banned_reason', '无')
                if expire and expire > time.time():
                    return False, "账号已被封禁，解封时间：{}，原因：{}".format(datetime.fromtimestamp(expire).strftime('%Y-%m-%d %H:%M:%S'), reason)
                elif expire is None:
                    return False, "账号已被永久封禁，原因：{}".format(reason)
                else:
                    user['banned'] = False
                    user['ban_expire'] = None
                    user['banned_reason'] = None
                    save_users(users)
            
            if check_password_hash(user['password_hash'], password):
                user['last_login'] = datetime.now().isoformat()
                user['last_ip'] = request.remote_addr
                save_users(users)
                return True, user
            else:
                return False, "密码错误"
    return False, "用户名不存在"

def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """管理员验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查是否已登录（普通用户或管理员页面登录）
        if 'user_id' not in session and not session.get(ADMIN_SESSION_KEY, False):
            return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401
        # 检查是否是管理员
        is_admin = session.get('is_admin', False)
        is_admin_page = session.get(ADMIN_SESSION_KEY, False)
        if not is_admin and not is_admin_page:
            return jsonify({'success': False, 'message': '需要管理员权限', 'code': 403}), 403
        return f(*args, **kwargs)
    return decorated_function

def clear_console():
    """清除控制台（跨平台）"""
    if os.name == 'nt':  # Windows
        os.system('cls')
    else:  # Linux/Mac
        os.system('clear')

def format_time_remaining(request_time):
    """格式化剩余时间"""
    elapsed = (datetime.now() - request_time).seconds
    remaining = max(0, CONFIRM_TIMEOUT - elapsed)
    mins = remaining // 60
    secs = remaining % 60
    return f"{mins:02d}:{secs:02d}"

def get_pending_requests_count():
    """获取待处理请求数量"""
    count = 0
    for confirm_id, info in force_reboot_requests.items():
        if not info['confirmed']:
            count += 1
    return count

def open_admin_page_in_browser():
    """自动打开默认浏览器访问管理页面"""
    try:
        # 构造管理页面URL
        admin_url = f"http://{LOCAL_IP}:5000/admin/force-reboot-confirm"
        
        # 记录尝试打开浏览器
        logger.info(f"尝试打开浏览器访问管理页面: {admin_url}")
        
        # 方法1: 使用webbrowser模块（最标准的方法）
        try:
            # 尝试使用默认浏览器打开，在新标签页中打开
            webbrowser.open(admin_url, new=1, autoraise=True)
            logger.info("使用webbrowser模块打开浏览器成功")
            return True
        except Exception as e1:
            logger.warning(f"使用webbrowser模块失败: {e1}")
            
            # 方法2: 根据操作系统使用不同的命令
            import platform
            os_name = platform.system()
            
            if os_name == "Windows":
                # Windows系统
                try:
                    # 使用start命令打开默认浏览器
                    subprocess.run(f'start {admin_url}', shell=True, check=True)
                    logger.info("使用Windows start命令打开浏览器成功")
                    return True
                except Exception as e2:
                    logger.error(f"Windows start命令失败: {e2}")
                    
                    # 尝试直接调用explorer
                    try:
                        subprocess.run(['explorer', admin_url], check=True)
                        logger.info("使用explorer命令打开浏览器成功")
                        return True
                    except Exception as e3:
                        logger.error(f"explorer命令失败: {e3}")
                        
            elif os_name == "Darwin":  # macOS
                try:
                    subprocess.run(['open', admin_url], check=True)
                    logger.info("使用macOS open命令打开浏览器成功")
                    return True
                except Exception as e2:
                    logger.error(f"macOS open命令失败: {e2}")
                    
            elif os_name == "Linux":
                try:
                    # 尝试使用xdg-open（大多数Linux桌面环境）
                    subprocess.run(['xdg-open', admin_url], check=True)
                    logger.info("使用Linux xdg-open命令打开浏览器成功")
                    return True
                except Exception as e2:
                    logger.error(f"Linux xdg-open命令失败: {e2}")
                    
                    # 尝试使用其他常见命令
                    for browser_cmd in ['google-chrome', 'chromium-browser', 'firefox']:
                        try:
                            subprocess.run([browser_cmd, admin_url], check=True)
                            logger.info(f"使用{browser_cmd}命令打开浏览器成功")
                            return True
                        except Exception:
                            continue
            
            # 所有方法都失败了
            logger.error("所有浏览器打开方法都失败了")
            return False
            
    except Exception as e:
        logger.error(f"打开浏览器时发生未知错误: {e}")
        return False


def display_console_dashboard():
    """显示控制台仪表板"""
    # 清除控制台
    clear_console()
    
    # 获取当前状态
    pending_count = get_pending_requests_count()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 显示标题
    print("=" * 80)
    print(" " * 30 + "🖥️  虚拟机远程控制系统")
    print("=" * 80)
    print(f"服务器时间: {current_time}")
    print(f"服务器IP: {LOCAL_IP}")
    print(f"Web界面: http://{LOCAL_IP}:5000")
    print(f"重启管理: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
    print("-" * 80)
    
    # 虚拟机状态
    vm_state = "✅ 运行中" if vm_status.get('is_running', False) else "❌ 已停止"
    if vm_status.get('is_rebooting', False):
        vm_state = "🔄 重启中"
    
    print(f"虚拟机状态: {vm_state}")
    print(f"虚拟机名称: {vm_status.get('vm_name', '未知')}")
    print("-" * 80)
    
    # 重启请求状态
    print(f"🚨 待处理重启请求: {pending_count}")
    print("-" * 80)
    
    if pending_count > 0:
        # 显示待处理请求
        print("编号 | 用户名          | 确认ID           | 客户端IP        | 请求时间  | 剩余时间 | 申请理由")
        print("-" * 80)
        
        i = 1
        for confirm_id, info in force_reboot_requests.items():
            if not info['confirmed']:
                request_time = info['request_time'].strftime("%H:%M:%S")
                remaining = format_time_remaining(info['request_time'])
                client_ip = info['client_ip'][:15] if len(info['client_ip']) > 15 else info['client_ip']
                confirm_id_short = confirm_id[:8] + "..." if len(confirm_id) > 8 else confirm_id
                username = info.get('username', '未知用户')[:12]
                
                # 获取申请理由，截断显示
                reason = info.get('reason', '无')
                reason_display = reason[:15] + "..." if len(reason) > 15 else reason
                
                print(f"{i:3d} | {username:14s} | {confirm_id_short:16s} | {client_ip:15s} | {request_time:9s} | {remaining:8s} | {reason_display}")
                i += 1
        
        print("-" * 80)
        print("操作指南:")
        print("  1. 访问管理页面: http://" + LOCAL_IP + ":5000/admin/force-reboot-confirm")
        print("  2. 输入确认ID并选择 '允许' 或 '拒绝'")
        print("  3. 查看申请理由并做出决定")
        print("  4. 或等待剩余时间为 00:00 自动拒绝")
        print()
    else:
        print("📭 当前没有待处理的重启请求")
        print()
        print("最近处理的请求:")
        print("-" * 80)
        
        # 显示最近处理的请求（最近5条）
        recent_requests = []
        for confirm_id, info in force_reboot_requests.items():
            if info['confirmed']:
                recent_requests.append({
                    'confirm_id': confirm_id,
                    'info': info,
                    'time': info.get('confirm_time', info['request_time'])
                })
        
        # 按时间排序，显示最近的5条
        recent_requests.sort(key=lambda x: x['time'], reverse=True)
        
        for i, req in enumerate(recent_requests[:5]):
            info = req['info']
            confirm_id_short = req['confirm_id'][:8] + "..." if len(req['confirm_id']) > 8 else req['confirm_id']
            client_ip = info['client_ip'][:15] if len(info['client_ip']) > 15 else info['client_ip']
            action = "✅ 允许" if info['approved'] else "❌ 拒绝"
            if info.get('timeout', False):
                action = "⏰ 超时拒绝"
            
            reject_reason_display = ""
            if not info['approved'] and info.get('reject_reason'):
                reject_reason_display = " (理由: {}...)".format(info['reject_reason'][:20])
            
            confirm_time = info.get('confirm_time', info['request_time'])
            if isinstance(confirm_time, datetime):
                time_str = confirm_time.strftime("%H:%M:%S")
            else:
                time_str = str(confirm_time)[11:19] if len(str(confirm_time)) > 19 else str(confirm_time)
            
            reason = info.get('reason', '无')
            reason_display = reason[:20] + "..." if len(reason) > 20 else reason
            
            print("{}. {} | {} | {} | {}{} | {}".format(i+1, confirm_id_short, client_ip, time_str, action, reject_reason_display, reason_display))
    
    print("-" * 80)
    print(f"自动刷新: {'✅ 开启' if console_refresh_enabled else '❌ 关闭'} (每{console_refresh_interval}秒)")
    print("按 Ctrl+C 停止程序")
    print("=" * 80)

def start_console_refresh():
    """启动控制台自动刷新线程"""
    global console_refresh_thread, console_refresh_enabled
    
    if console_refresh_enabled and console_refresh_thread is None:
        def refresh_loop():
            global console_last_refresh
            while console_refresh_enabled:
                try:
                    display_console_dashboard()
                    console_last_refresh = datetime.now()
                    time.sleep(console_refresh_interval)
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"控制台刷新错误: {e}")
                    time.sleep(console_refresh_interval)
        
        console_refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        console_refresh_thread.start()
        print("控制台自动刷新已启动...")
    elif not console_refresh_enabled:
        print("控制台自动刷新已禁用")

def stop_console_refresh():
    """停止控制台自动刷新"""
    global console_refresh_enabled, console_refresh_thread
    console_refresh_enabled = False
    if console_refresh_thread:
        console_refresh_thread.join(timeout=2)
        console_refresh_thread = None

def force_refresh_console():
    """强制立即刷新控制台"""
    if console_refresh_enabled:
        display_console_dashboard()
        return True
    return False

# 添加一个简单的控制台命令处理器
def handle_console_commands():
    """处理控制台命令"""
    import sys
    
    print("\n控制台命令:")
    print("  refresh  - 立即刷新显示")
    print("  clear    - 清除控制台")
    print("  status   - 显示详细状态")
    print("  help     - 显示帮助")
    print("  exit     - 退出程序")
    
    while True:
        try:
            cmd = input("\n输入命令 (help 查看帮助): ").strip().lower()
            
            if cmd == 'refresh' or cmd == 'r':
                force_refresh_console()
            elif cmd == 'clear' or cmd == 'c':
                clear_console()
                display_console_dashboard()
            elif cmd == 'status' or cmd == 's':
                print("\n详细状态信息:")
                print(f"  - 待处理请求: {get_pending_requests_count()}")
                print(f"  - 虚拟机状态: {'运行中' if vm_status.get('is_running', False) else '停止'}")
                print(f"  - 自动刷新: {'开启' if console_refresh_enabled else '关闭'}")
            elif cmd == 'help' or cmd == 'h':
                print("\n可用命令:")
                print("  refresh/r  - 立即刷新控制台显示")
                print("  clear/c    - 清除控制台并刷新")
                print("  status/s   - 显示详细状态信息")
                print("  help/h     - 显示帮助信息")
                print("  exit/q     - 退出程序")
            elif cmd == 'exit' or cmd == 'quit' or cmd == 'q':
                print("正在停止程序...")
                stop_console_refresh()
                sys.exit(0)
            else:
                print("未知命令，输入 'help' 查看可用命令")
        
        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，正在停止程序...")
            stop_console_refresh()
            sys.exit(0)
        except EOFError:
            print("\n输入结束，返回主循环...")
            break

# 信号处理器
def signal_handler(sig, frame):
    """处理Ctrl+C信号"""
    print('\n\n检测到 Ctrl+C，正在停止程序...')
    stop_console_refresh()
    sys.exit(0)

# 在启动前注册信号处理器
signal.signal(signal.SIGINT, signal_handler)

app = Flask(__name__)
app.secret_key = 'vm_control_system_secret_key_2025'  # 用于session管理
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
socketio = SocketIO(app, cors_allowed_origins="*")  # SocketIO初始化

# 在 app = Flask(__name__) 之后添加错误处理器
@app.errorhandler(500)
def internal_server_error(e):
    """处理500错误"""
    logger.error(f"服务器内部错误: {e}")
    logger.error(f"请求路径: {request.path}")
    logger.error(f"请求方法: {request.method}")
    logger.error(f"请求IP: {request.remote_addr}")
    
    # 记录堆栈跟踪
    import traceback
    logger.error(f"错误堆栈:\n{traceback.format_exc()}")
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>服务器错误</title>
        <style>
            body { font-family: Arial; padding: 50px; background: #f5f5f5; }
            .error-box { max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); text-align: center; }
            h1 { color: #dc3545; }
            .btn { display: inline-block; margin: 10px; padding: 10px 20px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; }
            pre { background: #f8f9fa; padding: 15px; border-radius: 5px; text-align: left; font-size: 12px; overflow: auto; }
        </style>
    </head>
    <body>
        <div class="error-box">
            <h1>⚠️ 服务器内部错误</h1>
            <p>抱歉，服务器遇到了一个内部错误。</p>
            <p>请稍后重试，或联系管理员。</p>
            <a href="/" class="btn">返回首页</a>
            <a href="javascript:location.reload()" class="btn" style="background: #28a745;">重新加载</a>
        </div>
    </body>
    </html>
    ''', 500

# 在 app = Flask(__name__) 之后添加一个全局变量来存储申请理由
force_reboot_reasons = {}

# 获取本机IP地址
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# VMware配置
VMRUN_PATH = r"C:\VM\vmrun.exe"
VMWARE_EXE_PATH = r"C:\VM\vmware.exe"
VMX_PATH = r"E:\Hypv\战神CF极致高帧版（W10）.vmx"

# VNC配置 - 修改为自动获取本机IP
VNC_HOST = LOCAL_IP  # 修改为自动获取本机IP
VNC_PORT = 5900
NOVNC_PATH = r"D:\Program Files\noVNC-master"
PUBLIC_URL = "https://4ed98fcf.vip.cpolar.top"

# 虚拟机状态跟踪
vm_status = {
    'last_start_time': None,
    'is_running': False,
    'last_error': None,
    'vm_name': '战神Windows10',
    'vmware_opened': False,
    'is_rebooting': False  # 新增：重启状态跟踪
}

# 全局变量用于确认状态
force_reboot_requests = {}
CONFIRM_TIMEOUT = 180  # 3分钟超时，超时后自动拒绝

# 反馈数据存储
FEEDBACK_FILE = "feedback_data.json"

# 新增：敏感词配置
SENSITIVE_WORDS = ["傻逼", "混蛋", "垃圾", "白痴", "脑残", "弱智", "废物", "蠢货", "操你妈", "fuck", "shit"]  # 敏感词列表

# 新增：管理员配置
ADMIN_USERNAME = "admin剠歼刭"
ADMIN_PASSWORD = "134679"  # 管理员密码
ADMIN_SESSION_KEY = 'admin_logged_in'  # 管理员登录状态键
admin_feedback_delete_logs = []  # 管理员反馈删除日志

# 新增：VNC连接用户管理
vnc_connected_users = {}
vnc_users_lock = threading.Lock()

# 新增：页面访问用户管理
page_connected_users = {}
page_users_lock = threading.Lock()
page_user_count = 0
MAX_PAGE_USERS = 10  # 最大页面访问人数限制

class VNCProxy:
    def __init__(self, vnc_host, vnc_port, web_port=6080, novnc_path=None, public_url=None):
        self.vnc_host = vnc_host
        self.vnc_port = vnc_port
        self.web_port = web_port
        self.novnc_path = novnc_path
        self.websockify_process = None
        self.public_url = public_url
        self.is_running = False
        # 新增：VNC连接统计
        self.connection_count = 0
        self.max_connections = 0
        
    def check_novnc(self):
        """检查noVNC目录是否存在且完整"""
        if not self.novnc_path or not os.path.exists(self.novnc_path):
            logger.warning(f"noVNC目录不存在: {self.novnc_path}")
            return False
            
        required_files = ["vnc.html", "app", "core"]
        for file in required_files:
            file_path = os.path.join(self.novnc_path, file)
            if not os.path.exists(file_path):
                logger.warning(f"noVNC文件不完整，缺少: {file}")
                return False
                
        logger.info(f"noVNC目录检查通过: {self.novnc_path}")
        return True
    
    def start_websockify(self):
        """启动WebSockify代理"""
        try:
            if not self.check_novnc():
                return False, "noVNC目录检查失败"
                
            # 构建websockify命令
            cmd = [
                'websockify',
                f'0.0.0.0:{self.web_port}',
                f'{self.vnc_host}:{self.vnc_port}',
                '--web', self.novnc_path
            ]
            
            logger.info(f"启动WebSockify代理: {self.vnc_host}:{self.vnc_port} -> 0.0.0.0:{self.web_port}")
            
            self.websockify_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.is_running = True
            
            # 重置连接统计
            self.connection_count = 0
            self.max_connections = 0
            
            # 启动连接监控线程
            self.start_connection_monitor()
            
            return True, "VNC代理启动成功"
        except Exception as e:
            error_msg = f"启动WebSockify失败: {e}"
            logger.error(error_msg)
            return False, error_msg
    
    def start_connection_monitor(self):
        """启动VNC连接监控线程"""
        def monitor():
            while self.is_running:
                try:
                    # 获取当前VNC连接数
                    current_count = self.get_current_vnc_connections()
                    
                    # 更新统计
                    with vnc_users_lock:
                        old_count = self.connection_count
                        self.connection_count = current_count
                        if current_count > self.max_connections:
                            self.max_connections = current_count
                    
                    # 如果连接数有变化，广播更新
                    if old_count != current_count:
                        logger.info(f"VNC连接数变化: {old_count} -> {current_count}")
                        socketio.emit('vnc_user_count_update', {
                            'current': current_count,
                            'max': self.max_connections,
                            'is_running': self.is_running
                        })
                    
                    time.sleep(5)  # 每5秒检查一次
                    
                except Exception as e:
                    logger.error(f"VNC连接监控错误: {e}")
                    time.sleep(10)
        
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
    
    def get_current_vnc_connections(self):
        """获取当前VNC连接数"""
        try:
            # 方法1: 检查Websockify连接
            if self.websockify_process and self.is_running:
                # 使用netstat检查6080端口的连接数
                result = subprocess.run(
                    ['netstat', '-an'], 
                    capture_output=True, 
                    text=True, 
                    encoding='utf-8',
                    errors='ignore'
                )
                
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    # 统计ESTABLISHED状态的连接
                    vnc_connections = 0
                    for line in lines:
                        if f':{self.web_port}' in line and 'ESTABLISHED' in line:
                            vnc_connections += 1
                    
                    return vnc_connections
            
            # 方法2: 检查VNC服务器连接
            try:
                result = subprocess.run(
                    ['netstat', '-an'], 
                    capture_output=True, 
                    text=True, 
                    encoding='utf-8',
                    errors='ignore'
                )
                
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    # 统计VNC端口的连接
                    vnc_server_connections = 0
                    for line in lines:
                        if f':{self.vnc_port}' in line and 'ESTABLISHED' in line:
                            vnc_server_connections += 1
                    
                    return vnc_server_connections
            except:
                pass
                
            return 0
            
        except Exception as e:
            logger.error(f"获取VNC连接数失败: {e}")
            return 0
    
    def stop_websockify(self):
        """停止WebSockify代理"""
        if self.websockify_process:
            self.websockify_process.terminate()
            self.websockify_process = None
            self.is_running = False
            self.connection_count = 0
            logger.info("VNC代理已停止")
    
    def get_access_urls(self):
        """获取访问URL"""
        urls = {
            'local': f"http://127.0.0.1:{self.web_port}/vnc.html",
            'network': f"http://{LOCAL_IP}:{self.web_port}/vnc.html"
        }
        
        if self.public_url:
            urls['public'] = f"{self.public_url}/vnc.html"
            
        return urls
    
    def get_connection_stats(self):
        """获取连接统计"""
        return {
            'current': self.connection_count,
            'max': self.max_connections,
            'is_running': self.is_running
        }

# 创建VNC代理实例
vnc_proxy = VNCProxy(
    vnc_host=VNC_HOST,
    vnc_port=VNC_PORT,
    novnc_path=NOVNC_PATH,
    public_url=PUBLIC_URL
)

def filter_sensitive_content(content, author="用户"):
    """检查并处理敏感词内容 - 增强兼容性"""
    if not content:
        return content, author, False
    
    # 检查是否有敏感词
    has_sensitive = False
    filtered_content = content
    
    for word in SENSITIVE_WORDS:
        if word in content:
            has_sensitive = True
            
            # 将敏感词中的随机一个字符替换为*
            for match in re.finditer(re.escape(word), content):
                matched_word = match.group()
                if len(matched_word) > 1:
                    # 随机选择要替换的位置
                    replace_pos = random.randint(0, len(matched_word) - 1)
                    
                    # 构建替换后的词
                    if matched_word == "傻逼":
                        # 特殊处理"傻逼"：随机替换成"傻*"或"*逼"
                        if random.choice([True, False]):
                            replacement = "傻*"
                        else:
                            replacement = "*逼"
                    else:
                        replacement = matched_word[:replace_pos] + "*" + matched_word[replace_pos + 1:]
                    
                    # 在词语最后面加上警告
                    replacement_with_warning = f"{replacement}（警告一次，网络不是违法之地，必要时小心惹祸上身）"
                    
                    # 替换内容中的敏感词
                    filtered_content = filtered_content.replace(matched_word, replacement_with_warning)
    
    # 如果有敏感词，修改作者名称
    if has_sensitive:
        author = "缺德人士（请文明用语）"
    
    return filtered_content, author, has_sensitive

def convert_feedback_data_format(data):
    """将旧格式的反馈数据转换为新格式"""
    if not isinstance(data, dict):
        return {"feedbacks": []}
    
    if "feedbacks" not in data:
        return {"feedbacks": []}
    
    converted_feedbacks = []
    for feedback in data["feedbacks"]:
        # 确保每个反馈都有必要的字段
        converted_feedback = {
            'id': feedback.get('id', str(uuid.uuid4())),
            'content': feedback.get('content', ''),
            'author': feedback.get('author', '用户'),
            'timestamp': feedback.get('timestamp', datetime.now().isoformat()),
            'replies': feedback.get('replies', [])
        }
        
        # 处理新格式的字段（如果有）
        if 'original_content' in feedback:
            converted_feedback['original_content'] = feedback['original_content']
        
        if 'has_sensitive' in feedback:
            converted_feedback['has_sensitive'] = feedback['has_sensitive']
        
        if 'client_ip' in feedback:
            converted_feedback['client_ip'] = feedback['client_ip']
        
        converted_feedbacks.append(converted_feedback)
    
    return {"feedbacks": converted_feedbacks}

def load_feedback_data():
    """加载反馈数据 - 添加数据格式兼容性处理"""
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 数据格式兼容性处理
                return convert_feedback_data_format(data)
    except Exception as e:
        logger.error(f"加载反馈数据失败: {e}")
    return {"feedbacks": []}

def save_feedback_data(data):
    """保存反馈数据 - 确保数据格式正确"""
    try:
        # 确保数据是转换后的格式
        if not isinstance(data, dict):
            data = {"feedbacks": []}
        
        if "feedbacks" not in data:
            data = {"feedbacks": data if isinstance(data, list) else []}
        
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存反馈数据失败: {e}")
        return False

def repair_feedback_data():
    """修复反馈数据格式"""
    try:
        logger.info("开始修复反馈数据格式...")
        
        # 加载原始数据
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                raw_data = f.read()
                
                # 尝试解析JSON
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    # 如果不是有效的JSON，尝试修复
                    logger.warning("反馈数据不是有效的JSON格式，尝试修复...")
                    data = {"feedbacks": []}
                
                # 转换格式
                converted_data = convert_feedback_data_format(data)
                
                # 保存修复后的数据
                with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
                    json.dump(converted_data, f, ensure_ascii=False, indent=2)
                
                logger.info(f"反馈数据修复完成，共处理 {len(converted_data.get('feedbacks', []))} 条反馈")
                return True
        else:
            logger.info("反馈数据文件不存在，无需修复")
            return True
            
    except Exception as e:
        logger.error(f"修复反馈数据失败: {e}")
        return False

def backup_feedback_data():
    """备份反馈数据"""
    try:
        if os.path.exists(FEEDBACK_FILE):
            backup_file = FEEDBACK_FILE + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
            import shutil
            shutil.copy2(FEEDBACK_FILE, backup_file)
            logger.info(f"反馈数据已备份到: {backup_file}")
            return backup_file
    except Exception as e:
        logger.error(f"备份反馈数据失败: {e}")
    return None

def admin_required(f):
    """管理员权限验证装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 检查两种管理员session状态
        is_admin = session.get('is_admin', False)
        is_admin_page = session.get(ADMIN_SESSION_KEY, False)
        
        # 如果两种都不是管理员，则拒绝访问
        if not is_admin and not is_admin_page:
            return jsonify({'success': False, 'message': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return decorated_function

# 添加虚拟机状态缓存
last_vm_status_check = 0
vm_status_cache = None
VM_STATUS_CACHE_DURATION = 5  # 缓存5秒

def check_vm_status():
    """检查虚拟机状态 - 带缓存优化"""
    global last_vm_status_check, vm_status_cache
    
    current_time = time.time()
    
    # 如果缓存还在有效期内，直接返回缓存
    if vm_status_cache and (current_time - last_vm_status_check) < VM_STATUS_CACHE_DURATION:
        return vm_status_cache
    
    try:
        cmd = [VMRUN_PATH, 'list']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)  # 减少超时时间
        
        if result.returncode == 0:
            is_running = VMX_PATH in result.stdout
            vm_status_cache = (is_running, None)
            last_vm_status_check = current_time
            return vm_status_cache
        else:
            error_msg = f"检查虚拟机状态失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"检查虚拟机状态异常: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def start_virtual_machine():
    """启动虚拟机 - 添加详细错误处理"""
    try:
        logger.info(f"开始启动虚拟机: {VMX_PATH}")
        
        # 检查vmrun.exe是否存在
        if not os.path.exists(VMRUN_PATH):
            error_msg = f"vmrun.exe不存在: {VMRUN_PATH}"
            logger.error(error_msg)
            return False, error_msg
            
        # 检查虚拟机配置文件是否存在
        if not os.path.exists(VMX_PATH):
            error_msg = f"虚拟机配置文件不存在: {VMX_PATH}"
            logger.error(error_msg)
            return False, error_msg
        
        # 使用完整路径并加上引号（处理路径中的空格和特殊字符）
        vmx_path_quoted = f'"{VMX_PATH}"'
        
        # 构建命令 - 确保路径正确处理
        cmd = [VMRUN_PATH, 'start', vmx_path_quoted, 'nogui']
        logger.info(f"执行启动命令: {' '.join(cmd)}")
        
        # 使用shell=True确保路径正确处理（Windows需要）
        result = subprocess.run(
            ' '.join(cmd),  # 将列表转换为字符串
            shell=True,
            capture_output=True, 
            text=True, 
            encoding='utf-8', 
            errors='ignore', 
            timeout=120
        )
        
        logger.info(f"启动命令返回码: {result.returncode}")
        logger.info(f"启动命令标准输出: {result.stdout}")
        if result.stderr:
            logger.error(f"启动命令错误输出: {result.stderr}")
        
        if result.returncode == 0:
            logger.info("虚拟机启动命令执行成功")
            
            # 等待一段时间让虚拟机完全启动
            logger.info("等待10秒让虚拟机启动...")
            time.sleep(10)
            
            # 检查虚拟机是否真的启动了
            is_running, error = check_vm_status()
            if is_running:
                logger.info("虚拟机已成功启动并在运行列表中")
                
                # 自动打开VMware图形界面
                try:
                    if os.path.exists(VMWARE_EXE_PATH):
                        logger.info(f"正在自动打开VMware图形界面: {VMWARE_EXE_PATH}")
                        subprocess.Popen(
                            [VMWARE_EXE_PATH],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            shell=True
                        )
                        vm_status['vmware_opened'] = True
                        return True, "虚拟机启动成功并已自动打开VMware图形界面"
                    else:
                        logger.warning(f"VMware图形界面程序不存在: {VMWARE_EXE_PATH}")
                        return True, "虚拟机启动成功，但未找到VMware图形界面程序"
                except Exception as e:
                    logger.error(f"打开VMware图形界面失败: {e}")
                    return True, "虚拟机启动成功，但打开VMware图形界面失败"
            else:
                error_msg = "虚拟机启动命令执行成功，但虚拟机未出现在运行列表中。"
                logger.warning(error_msg)
                return False, error_msg
        else:
            # 详细分析错误
            if "Cannot open VM" in result.stderr:
                error_msg = f"无法打开虚拟机文件: {VMX_PATH}"
            elif "The file specified is not a virtual machine" in result.stderr:
                error_msg = f"指定的文件不是有效的虚拟机配置文件: {VMX_PATH}"
            elif "Incorrect username or password" in result.stderr:
                error_msg = "VMware身份验证失败，请检查VMware安装和许可证"
            elif "Unable to connect to host" in result.stderr:
                error_msg = "无法连接到VMware主机服务，请确保VMware服务正在运行"
            else:
                error_msg = f"启动失败: {result.stderr}"
            
            logger.error(error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = "启动虚拟机超时（120秒）"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"启动过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def force_shutdown_virtual_machine():
    """强制关闭虚拟机 - 修改为远程关机命令"""
    try:
        logger.info(f"开始重启虚拟机")
        
        # 构建远程关机命令
        target_ip = "192.168.81.131"
        shutdown_cmd = f'shutdown /s /m \\\\{target_ip} /t 6 /c "重启，由虚拟机管理系统发起"'
        
        logger.info(f"执行远程关机命令: {shutdown_cmd}")
        
        result = subprocess.run(
            shutdown_cmd,
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            timeout=30
        )
        
        if result.returncode == 0:
            logger.info(f"远程计算机 {target_ip} 关机命令已成功发送")
            return True, f"已向 {target_ip} 发送关机命令，计算机将在6秒后关闭"
        else:
            error_msg = f"远程关机命令执行失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"远程关机过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def force_reboot_virtual_machine():
    """重启虚拟机 - 自动打开cmd窗口执行连接和重启命令"""
    try:
        logger.info(f"开始重启虚拟机: {VMX_PATH}")
        
        # 获取申请理由
        reason = ""
        # 查找最近的重启请求中的理由
        for confirm_id, info in force_reboot_requests.items():
            if 'reason' in info and info['reason']:
                reason = info['reason']
                break
        
        # 目标计算机IP
        target_ip = "192.168.81.131"
        
        # 构建完整的批处理命令
        batch_commands = []
        
        # 1. 先建立IPC连接
        net_use_cmd = 'net use \\\\{}\\ipc$ "{}" /user:"netease"'.format(target_ip, "123456")
        batch_commands.append(f"echo 正在建立IPC连接到 {target_ip}...")
        batch_commands.append(net_use_cmd)
        
        # 2. 检查连接结果
        batch_commands.append("if %errorlevel% equ 0 (echo IPC连接成功!) else (echo IPC连接失败，但将继续尝试重启...)")
        
        # 3. 等待2秒
        batch_commands.append("timeout /t 2 /nobreak >nul")
        
        # 4. 执行远程重启命令
        shutdown_cmd = f'shutdown /r /m \\\\{target_ip} /t 10'
        
        # 如果有申请理由，添加到注释中
        if reason:
            # 限制注释长度，避免命令行过长
            reason_short = reason[:100]  # 限制为100个字符
            shutdown_cmd += f' /c "{reason_short}"'
        else:
            shutdown_cmd += ' /c "计划重启，由虚拟机管理系统发起"'
        
        batch_commands.append(f"echo 正在向 {target_ip} 发送重启命令...")
        batch_commands.append(shutdown_cmd)
        
        # 5. 检查重启命令结果
        batch_commands.append("if %errorlevel% equ 0 (echo 重启命令发送成功! 计算机将在6秒后重启。) else (echo 重启命令发送失败!)")
        
        # 6. 保持窗口打开以便查看结果
        batch_commands.append("echo.")
        batch_commands.append(f"echo 操作完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        batch_commands.append("echo 此窗口将在10秒后自动关闭...")
        batch_commands.append("timeout /t 10 /nobreak >nul")
        
        # 将命令转换为批处理字符串
        batch_content = "\n".join(batch_commands)
        
        # 创建临时批处理文件
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='gbk') as f:
            f.write(f"@echo off\n")
            f.write(f"title 虚拟机远程重启控制 - {target_ip}\n")
            f.write(f"color 0A\n")
            f.write(f"echo ============================================\n")
            f.write(f"echo         虚拟机远程重启控制系统\n")
            f.write(f"echo ============================================\n")
            f.write(f"echo 目标计算机: {target_ip}\n")
            f.write(f"echo 操作时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if reason:
                f.write(f"echo 申请理由: {reason_short}\n")
            f.write(f"echo ============================================\n")
            f.write(f"echo.\n")
            f.write(batch_content)
            batch_file = f.name
        
        logger.info(f"创建批处理文件: {batch_file}")
        logger.info(f"批处理内容:\n{batch_content}")
        
        # 使用start命令在新cmd窗口中执行批处理文件
        cmd_command = f'start "远程重启控制" cmd /c "{batch_file}"'
        
        logger.info(f"执行命令: {cmd_command}")
        
        # 在新窗口中执行批处理
        result = subprocess.run(
            cmd_command,
            shell=True,
            capture_output=False,  # 不捕获输出，让它在窗口中显示
            timeout=5  # 只等待启动窗口，不等待命令完成
        )
        
        # 立即返回成功，因为批处理会在新窗口中执行
        success_msg = f"已在新的命令窗口中启动重启流程。目标: {target_ip}"
        if reason:
            success_msg += f"\n申请理由: {reason[:50]}..."
        
        logger.info(success_msg)
        
        # 异步清理临时文件（30秒后）
        def cleanup_temp_file():
            time.sleep(35)  # 等待批处理执行完成
            try:
                if os.path.exists(batch_file):
                    os.remove(batch_file)
                    logger.info(f"已清理临时文件: {batch_file}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_temp_file, daemon=True)
        cleanup_thread.start()
        
        return True, success_msg
                
    except subprocess.TimeoutExpired:
        error_msg = "启动命令窗口超时"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"远程重启过程中发生错误: {str(e)}"
        logger.error(error_msg)
        
        # 尝试直接执行命令而不打开窗口
        try:
            logger.info("尝试直接执行命令（不打开新窗口）...")
            
            # 直接执行net use命令
            net_use_result = subprocess.run(
                'net use \\\\{}\\ipc$ "{}" /user:"netease"'.format(target_ip, "123456"),
                shell=True,
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=15
            )
            
            # 执行重启命令
            shutdown_cmd = f'shutdown /r /m \\\\{target_ip} /t 6'
            if reason:
                reason_short = reason[:100]
                shutdown_cmd += f' /c "{reason_short}"'
            
            shutdown_result = subprocess.run(
                shutdown_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=30
            )
            
            if shutdown_result.returncode == 0:
                return True, f"已直接向 {target_ip} 发送重启命令"
            else:
                return False, f"直接执行重启失败: {shutdown_result.stderr}"
                
        except Exception as e2:
            logger.error(f"备用方法失败: {e2}")
            return False, f"远程重启失败: {error_msg}"
    except Exception as e:
        error_msg = f"远程重启过程中发生错误: {str(e)}"
        logger.error(error_msg)
        
        # 尝试直接执行命令而不打开窗口
        try:
            logger.info("尝试直接执行命令（不打开新窗口）...")
            
            # 直接执行net use命令
            net_use_result = subprocess.run(
                'net use \\\\{}\\ipc$ "{}" /user:"netease"'.format(target_ip, "123456"),
                shell=True,
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=15
            )
            
            # 执行重启命令
            shutdown_cmd = f'shutdown /r /m \\\\{target_ip} /t 6'
            if reason:
                reason_short = reason[:100]
                shutdown_cmd += f' /c "{reason_short}"'
            
            shutdown_result = subprocess.run(
                shutdown_cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding='gbk',
                errors='ignore',
                timeout=30
            )
            
            if shutdown_result.returncode == 0:
                return True, f"已直接向 {target_ip} 发送重启命令"
            else:
                return False, f"直接执行重启失败: {shutdown_result.stderr}"
                
        except Exception as e2:
            logger.error(f"备用方法失败: {e2}")
            return False, f"远程重启失败: {error_msg}"


def get_system_performance():
    """获取系统性能数据 - 带缓存优化"""
    global last_performance_check, performance_cache
    
    current_time = time.time()
    
    # 如果缓存还在有效期内，直接返回缓存
    if performance_cache and (current_time - last_performance_check) < CACHE_DURATION:
        return performance_cache
    
    try:
        # CPU使用率 - 减小采样间隔
        cpu_percent = psutil.cpu_percent(interval=0.1)  # 从0.5秒减少到0.1秒
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024**3), 1)
        memory_used_gb = round(memory.used / (1024**3), 1)
        memory_percent = memory.percent
        
        # 网络IO - 缓存上次的值计算增量
        if not hasattr(get_system_performance, 'last_net_io'):
            get_system_performance.last_net_io = psutil.net_io_counters()
        
        current_net_io = psutil.net_io_counters()
        net_sent_mb = round((current_net_io.bytes_sent - get_system_performance.last_net_io.bytes_sent) / (1024**2), 2)
        net_recv_mb = round((current_net_io.bytes_recv - get_system_performance.last_net_io.bytes_recv) / (1024**2), 2)
        get_system_performance.last_net_io = current_net_io
        
        # 系统启动时间 - 这个基本不变，可以缓存更久
        if not hasattr(get_system_performance, 'boot_time_cache'):
            get_system_performance.boot_time_cache = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        
        performance_data = {
            'cpu_percent': cpu_percent,
            'memory_total_gb': memory_total_gb,
            'memory_used_gb': memory_used_gb,
            'memory_percent': memory_percent,
            'net_sent_mb': net_sent_mb,
            'net_recv_mb': net_recv_mb,
            'boot_time': get_system_performance.boot_time_cache,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
        
        # 更新缓存
        performance_cache = performance_data
        last_performance_check = current_time
        
        return performance_data
        
    except Exception as e:
        logger.error(f"获取系统性能数据失败: {str(e)}")
        return {
            'cpu_percent': 0,
            'memory_total_gb': 0,
            'memory_used_gb': 0,
            'memory_percent': 0,
            'net_sent_mb': 0,
            'net_recv_mb': 0,
            'boot_time': '未知',
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'error': str(e)
        }



@app.route('/login-page')
def login_page():
    """独立的登录/注册页面"""
    if 'user_id' in session:
        return redirect('/')
    
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 - 虚拟机远程控制系统</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 400px;
            width: 100%;
        }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #333; font-size: 24px; margin-bottom: 10px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 5px; color: #333; font-weight: 500; }
        input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 14px; }
        .btn {
            width: 100%; padding: 12px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; border: none; border-radius: 8px;
            font-size: 16px; font-weight: bold; cursor: pointer;
        }
        .btn:hover { transform: translateY(-2px); }
        .link { text-align: center; margin-top: 15px; color: #666; }
        .link a { color: #667eea; text-decoration: none; }
        .error-message { color: #dc3545; font-size: 14px; margin-top: 10px; text-align: center; }
        .info-box { background: #e8f4fd; padding: 10px; border-radius: 5px; margin-bottom: 15px; text-align: center; }
        .admin-link { margin-top: 20px; text-align: center; border-top: 1px solid #eee; padding-top: 20px; }
        .admin-link a { color: #667eea; text-decoration: none; font-weight: bold; }
        .admin-link a:hover { text-decoration: underline; }
        
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .container { animation: fadeInUp 0.6s ease-out; }
        
        input:focus {
            outline: none;
            border-color: #667eea !important;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
            transform: scale(1.02);
            transition: all 0.2s ease;
        }
        
        .btn {
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🔐 用户登录</h1>
        <p>请登录后使用系统</p>
    </div>
    
    <div class="admin-link" style="margin-bottom: 20px;">
        <a href="/admin/login" target="_blank">管理员登录</a>
    </div>
    
    <div id="loginForm">
        <div class="form-group">
            <label for="loginUsername">用户名</label>
            <input type="text" id="loginUsername" placeholder="请输入用户名">
        </div>
        <div class="form-group">
            <label for="loginPassword">密码</label>
            <input type="password" id="loginPassword" placeholder="请输入密码">
        </div>
        <button type="button" class="btn" onclick="doLogin()">登录</button>
        <div class="link">
            还没有账号？ <a href="#" onclick="showRegister()">立即注册</a> | 
            <a href="/forgot-password">找回密码</a>
        </div>
    </div>
    
    <div id="registerForm" style="display:none;">
        <div class="info-box">系统将为您分配一个唯一用户名</div>
        <div class="form-group">
            <label for="registerPassword">密码</label>
            <input type="password" id="registerPassword" placeholder="至少6位">
        </div>
        <div class="form-group">
            <label for="registerConfirm">确认密码</label>
            <input type="password" id="registerConfirm" placeholder="再次输入密码">
        </div>
        <button type="button" class="btn" onclick="doRegister()">注册</button>
        <div class="link">
            已有账号？ <a href="#" onclick="showLogin()">去登录</a>
        </div>
    </div>
    
    <div id="errorMessage" class="error-message"></div>
</div>

<script>
function showRegister() {
    document.getElementById('loginForm').style.display = 'none';
    document.getElementById('registerForm').style.display = 'block';
}

function showLogin() {
    document.getElementById('registerForm').style.display = 'none';
    document.getElementById('loginForm').style.display = 'block';
    document.getElementById('errorMessage').innerHTML = '';
}

function showError(msg) {
    document.getElementById('errorMessage').innerHTML = msg;
}

var isEvading = false;
var shouldSkipLogin = false;
var loginBtn = null;

function initEvadeButton() {
    if (!loginBtn) {
        loginBtn = document.querySelector('#loginForm .btn');
    }
}

function activateEvadeMode() {
    if (isEvading) return;
    isEvading = true;
    initEvadeButton();
    if (loginBtn) {
        var btnWidth = loginBtn.offsetWidth;
        var btnHeight = loginBtn.offsetHeight;
        loginBtn.style.width = btnWidth + 'px';
        loginBtn.style.height = btnHeight + 'px';
        loginBtn.style.position = 'fixed';
        loginBtn.style.zIndex = '9999';
        loginBtn.style.transition = 'all 0.2s ease';
    }
    showError('由于登录失败，登录按钮现在会躲避您的点击。请刷新页面后重试。');
}

function moveButtonRandomly() {
    if (!loginBtn) initEvadeButton();
    if (!loginBtn) return;
    var viewportWidth = window.innerWidth;
    var viewportHeight = window.innerHeight;
    var btnWidth = loginBtn.offsetWidth;
    var btnHeight = loginBtn.offsetHeight;
    var maxLeft = viewportWidth - btnWidth;
    var maxTop = viewportHeight - btnHeight;
    var left = Math.random() * maxLeft;
    var top = Math.random() * maxTop;
    loginBtn.style.left = left + 'px';
    loginBtn.style.top = top + 'px';
}

document.addEventListener('DOMContentLoaded', function() {
    initEvadeButton();
    if (loginBtn) {
        loginBtn.addEventListener('mouseenter', function(e) {
            if (isEvading) { moveButtonRandomly(); }
        });
        loginBtn.addEventListener('click', function(e) {
            if (isEvading) {
                e.preventDefault();
                e.stopPropagation();
                shouldSkipLogin = true;
                moveButtonRandomly();
            }
        });
    }
});

function doLogin() {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value.trim();
    if (!username || !password) { showError('请输入用户名和密码'); return; }
    fetch('/api/login', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: username, password: password})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) { window.location.href = '/'; }
        else { 
            const msg = data.message || '';
            if (msg.includes('封禁') || msg.includes('名额已满') || msg.includes('已达上限') || msg.includes('不存在') || msg.includes('密码错误')) {
                activateEvadeMode();
            }
            showError(data.message); 
        }
    })
    .catch(err => { console.error(err); showError('网络错误'); });
}

function doRegister() {
    const password = document.getElementById('registerPassword').value.trim();
    const confirm = document.getElementById('registerConfirm').value.trim();
    if (!password || !confirm) { showError('请填写密码'); return; }
    if (password !== confirm) { showError('两次密码不一致'); return; }
    if (password.length < 6) { showError('密码至少6位'); return; }
    fetch('/api/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({password: password, confirm: confirm})
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            alert('注册成功！您的用户名是：' + data.username + '\\n请牢记您的用户名。');
            window.location.href = '/';
        } else { showError(data.message); }
    })
    .catch(err => { console.error(err); showError('网络错误'); });
}
</script>
</body>
</html>'''
    
    response = make_response(html_content)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Server'] = 'Werkzeug'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon():
    return '', 204

@app.route('/forgot-password')
def forgot_password():
    """找回密码页面"""
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>找回密码</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; display: flex; justify-content: center; align-items: center; padding: 20px; }
        .container { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 20px 60px rgba(0,0,0,0.3); width: 100%; max-width: 450px; animation: fadeInUp 0.6s ease-out; }
        @keyframes fadeInUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        .header { text-align: center; margin-bottom: 30px; }
        .header h1 { color: #333; font-size: 28px; margin-bottom: 10px; }
        .header p { color: #666; font-size: 14px; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: #333; font-weight: 500; }
        .form-group input { width: 100%; padding: 12px 15px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px; transition: all 0.2s ease; }
        .form-group input:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); transform: scale(1.02); }
        .btn { width: 100%; padding: 14px; background: #667eea; color: white; border: none; border-radius: 8px; font-size: 16px; font-weight: bold; cursor: pointer; transition: all 0.2s ease; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(102,126,234,0.3); }
        .btn:disabled { background: #ccc; cursor: not-allowed; transform: none; }
        .btn-copy { background: #28a745; margin-top: 10px; }
        .btn-copy:hover { box-shadow: 0 10px 20px rgba(40,167,69,0.3); }
        .btn-bilibili { background: #00a1d6; margin-top: 10px; display: none; }
        .btn-bilibili:hover { box-shadow: 0 10px 20px rgba(0,161,214,0.3); }
        .result { margin-top: 25px; padding: 15px; background: #f8f9fa; border-radius: 8px; display: none; }
        .result.show { display: block; animation: fadeInUp 0.3s ease-out; }
        .result textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 13px; resize: vertical; min-height: 80px; }
        .result-label { font-weight: bold; margin-bottom: 8px; color: #333; }
        .back-link { text-align: center; margin-top: 20px; }
        .back-link a { color: #667eea; text-decoration: none; }
        .back-link a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔑 找回密码</h1>
            <p>请填写以下信息以找回密码</p>
        </div>
        
        <div class="form-group">
            <label for="username">用户名</label>
            <input type="text" id="username" placeholder="请输入您的用户名">
        </div>
        
        <div class="form-group">
            <label for="regTime">注册大概时间</label>
            <input type="text" id="regTime" placeholder="例如：2024年1月、半年以前">
        </div>
        
        <button type="button" class="btn" onclick="generateInfo()">确定</button>
        
        <div class="result" id="result">
            <div class="result-label">复制以下信息联系管理员：</div>
            <textarea id="infoText" readonly></textarea>
            <button type="button" class="btn btn-copy" id="copyBtn" onclick="copyInfo()">📋 复制信息</button>
            <button type="button" class="btn btn-bilibili" id="bilibiliBtn" onclick="goToBilibili()">🔗 点击前往剠歼刭的主页</button>
        </div>
        
        <div class="back-link">
            <a href="/login-page">← 返回登录</a>
        </div>
    </div>
    
    <script>
        function generateInfo() {
            var username = document.getElementById('username').value.trim();
            var regTime = document.getElementById('regTime').value.trim();
            
            if (!username) {
                alert('请输入用户名');
                return;
            }
            
            var info = '【找回密码申请】\\n用户名：' + username + '\\n注册时间：' + (regTime || '不确定') + '\\n申请时间：' + new Date().toLocaleString();
            document.getElementById('infoText').value = info;
            document.getElementById('result').classList.add('show');
            document.getElementById('bilibiliBtn').style.display = 'none';
        }
        
        function copyInfo() {
            var textarea = document.getElementById('infoText');
            textarea.select();
            document.execCommand('copy');
            
            var btn = document.getElementById('copyBtn');
            btn.textContent = '✓ 已复制';
            btn.disabled = true;
            
            document.getElementById('bilibiliBtn').style.display = 'block';
        }
        
        function goToBilibili() {
            window.open('https://space.bilibili.com/3546785855310555?spm_id_from=333.1007.0.0', '_blank');
        }
    </script>
</body>
</html>'''
    return html_content

@app.route('/')
def index():
    """主页 - 需要登录才能访问"""
    if 'user_id' not in session:
        return redirect('/login-page')
    
    users = load_users()
    current_user = next((u for u in users if u['username'] == session.get('username')), None)
    if not current_user:
        session.clear()
        return redirect('/login-page')
    
    html_content = '''
    <!DOCTYPE html>
    <html lang="zh-CN" data-theme="default">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>虚拟机远程控制系统</title>
        <style>
            /* 主题变量 */
            :root {
                /* 默认主题变量 */
                --primary-color: #667eea;
                --secondary-color: #764ba2;
                --danger-color: #dc3545;
                --warning-color: #fd7e14;
                --success-color: #28a745;
                --info-color: #17a2b8;
                --light-color: #f8f9fa;
                --dark-color: #343a40;
                --text-color: #333;
                --bg-color: white;
                --card-bg: #f8f9fa;
                --header-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                --shadow-color: rgba(0,0,0,0.1);
            }

            /* 新年主题变量 */
            [data-theme="newyear"] {
                --primary-color: #d62828;
                --secondary-color: #f77f00;
                --danger-color: #d62828;
                --warning-color: #fcbf49;
                --success-color: #2a9d8f;
                --info-color: #e9c46a;
                --light-color: #fffaf0;
                --dark-color: #264653;
                --text-color: #5a189a;
                --bg-color: linear-gradient(135deg, #ff9d00 0%, #ff0054 100%);
                --card-bg: rgba(255, 255, 255, 0.9);
                --header-bg: linear-gradient(135deg, #ff0000 0%, #ff6b6b 100%);
                --shadow-color: rgba(214, 40, 40, 0.2);
            }
            
            /* 灯笼动画 */
            @keyframes lantern-swing {
                0%, 100% { transform: rotate(-5deg); }
                50% { transform: rotate(5deg); }
            }
            
            @keyframes firework {
                0% { transform: translateY(0) scale(0); opacity: 1; }
                100% { transform: translateY(-100px) scale(1); opacity: 0; }
            }
            
            @keyframes snow-fall {
                0% { transform: translateY(-10px) translateX(0); }
                100% { transform: translateY(100vh) translateX(20px); }
            }
            
            /* 新年装饰元素 */
            .newyear-decoration {
                position: fixed;
                pointer-events: none;
                z-index: 1;
            }
            
            .lantern {
                width: 40px;
                height: 60px;
                background: #d62828;
                border-radius: 20px 20px 10px 10px;
                position: fixed;
                top: 20px;
                animation: lantern-swing 3s ease-in-out infinite;
            }
            
            .lantern::before {
                content: '';
                position: absolute;
                top: -10px;
                left: 10px;
                width: 20px;
                height: 20px;
                background: gold;
                border-radius: 50%;
            }
            
            .lantern::after {
                content: '';
                position: absolute;
                bottom: 0;
                left: 15px;
                width: 10px;
                height: 20px;
                background: gold;
                border-radius: 0 0 5px 5px;
            }
            
            .lantern-left {
                left: 20px;
            }
            
            .lantern-right {
                right: 20px;
            }
            
            .firework {
                position: fixed;
                width: 4px;
                height: 4px;
                background: gold;
                border-radius: 50%;
                animation: firework 1.5s ease-out infinite;
            }
            
            .snowflake {
                position: fixed;
                width: 8px;
                height: 8px;
                background: white;
                border-radius: 50%;
                animation: snow-fall 10s linear infinite;
            }
            
            /* 主题切换按钮 */
            .theme-toggle {
                position: fixed;
                top: 20px;
                right: 180px;
                background: var(--primary-color);
                color: white;
                border: none;
                border-radius: 20px;
                padding: 8px 16px;
                cursor: pointer;
                font-size: 12px;
                z-index: 1000;
                display: flex;
                align-items: center;
                gap: 5px;
                transition: all 0.3s ease;
            }
            
            .theme-toggle:hover {
                transform: scale(1.05);
                box-shadow: 0 5px 15px var(--shadow-color);
            }
            
            .theme-toggle .icon {
                font-size: 14px;
            }
            
            /* 新年祝福语 */
            .newyear-greeting {
                position: fixed;
                top: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(45deg, #ff0000, #ff9500);
                color: white;
                padding: 5px 15px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: bold;
                z-index: 1000;
                white-space: nowrap;
                animation: pulse 2s infinite;
            }
            
            * { 
                margin: 0; 
                padding: 0; 
                box-sizing: border-box; 
            }
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: var(--header-bg);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
                color: var(--text-color);
                position: relative;
                overflow-x: hidden;
            }
            
            /* 添加新年主题背景覆盖层 */
            body[data-theme="newyear"]::before {
                content: '';
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: 
                    radial-gradient(circle at 20% 80%, rgba(255, 215, 0, 0.1) 0%, transparent 50%),
                    radial-gradient(circle at 80% 20%, rgba(255, 0, 0, 0.1) 0%, transparent 50%),
                    radial-gradient(circle at 40% 40%, rgba(255, 255, 255, 0.05) 0%, transparent 50%);
                pointer-events: none;
                z-index: 0;
            }
            .container {
                background: var(--card-bg);
                border-radius: 15px;
                box-shadow: 0 20px 40px var(--shadow-color);
                padding: 40px;
                max-width: 800px;
                width: 100%;
                position: relative;
                z-index: 2;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                position: relative;
            }
            .header h1 {
                color: var(--text-color);
                font-size: 28px;
                margin-bottom: 10px;
                background: linear-gradient(45deg, var(--primary-color), var(--secondary-color));
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            .header p {
                color: var(--text-color);
                font-size: 16px;
                opacity: 0.8;
            }
            /* 新增：页面访问人数显示样式 */
            .page-users {
                position: absolute;
                top: 0;
                right: 120px;
                background: var(--info-color);
                color: white;
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 12px;
                display: flex;
                align-items: center;
                gap: 5px;
                transition: all 0.3s ease;
            }
            
            .page-users::before {
                content: "👥";
                font-size: 10px;
            }
            
            .page-users.near-limit {
                background: var(--warning-color);
                color: var(--dark-color);
                animation: pulse 2s infinite;
            }
            
            .page-users.at-limit {
                background: var(--danger-color);
                animation: shake 0.5s ease-in-out;
            }
            
            @keyframes pulse {
                0% { transform: scale(1); }
                50% { transform: scale(1.05); }
                100% { transform: scale(1); }
            }
            
            @keyframes shake {
                0%, 100% { transform: translateX(0); }
                25% { transform: translateX(-5px); }
                75% { transform: translateX(5px); }
            }
            
            /* 新增：VNC在线用户显示 */
            .vnc-users {
                position: absolute;
                top: 0;
                left: 0;
                background: var(--info-color);
                color: white;
                padding: 5px 10px;
                border-radius: 15px;
                font-size: 12px;
                display: flex;
                align-items: center;
                gap: 5px;
            }
            .vnc-users::before {
                content: "🔗";
                font-size: 10px;
            }
            .vnc-users.high-usage {
                background: var(--warning-color);
                color: var(--dark-color);
            }
            .vnc-users.max-usage {
                background: var(--danger-color);
            }
            /* 菜单样式 */
            .menu-container {
                position: absolute;
                top: 0;
                right: 0;
            }
            .menu-btn {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                padding: 10px;
                color: #333;
            }
            .dropdown-menu {
                display: none;
                position: absolute;
                right: 0;
                top: 100%;
                background: white;
                border-radius: 8px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                min-width: 150px;
                z-index: 1000;
            }
            .dropdown-menu.show {
                display: block;
            }
            .menu-item {
                padding: 12px 16px;
                cursor: pointer;
                border-bottom: 1px solid #f0f0f0;
                color: #333;
                text-decoration: none;
                display: block;
            }
            .menu-item:hover {
                background: #f5f5f5;
            }
            .menu-item:last-child {
                border-bottom: none;
            }
            /* 模态框样式 */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 2000;
                justify-content: center;
                align-items: center;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .modal.show {
                display: flex;
                opacity: 1;
            }
            @keyframes modalPopIn {
                from { opacity: 0; transform: scale(0.9); }
                to { opacity: 1; transform: scale(1); }
            }
            .modal-content {
                background: white;
                border-radius: 10px;
                padding: 30px;
                width: 90%;
                max-width: 500px;
                max-height: 80vh;
                overflow-y: auto;
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .modal-title {
                font-size: 20px;
                font-weight: bold;
                color: #333;
            }
            .close-btn {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
            }
            .modal-body {
                margin-bottom: 20px;
            }
            .modal-footer {
                display: flex;
                gap: 10px;
                margin-top: 20px;
            }
            .modal-footer .btn {
                flex: 1;
                margin-bottom: 0;
            }
            .feedback-form textarea {
                width: 100%;
                height: 120px;
                padding: 12px;
                border: 2px solid #e1e5e9;
                border-radius: 8px;
                font-size: 14px;
                resize: vertical;
                margin-bottom: 15px;
            }
            .feedback-form textarea:focus {
                outline: none;
                border-color: #667eea;
            }
            .submit-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                width: 100%;
            }
            /* 反馈列表样式 */
            .feedback-list {
                margin-top: 20px;
            }
            .feedback-item {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 15px;
                border-left: 4px solid #667eea;
            }
            .feedback-header {
                display: flex;
                justify-content: space-between;
                margin-bottom: 10px;
            }
            .feedback-author {
                font-weight: bold;
                color: #333;
            }
            
            /* 敏感词相关样式 */
            .sensitive-badge {
                background: #dc3545;
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                margin-left: 5px;
            }
            
            .warning-message {
                background: #fff3cd;
                border: 1px solid #ffeaa7;
                color: #856404;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
                font-size: 14px;
            }
            
            .btn-view-original {
                background: #6c757d;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 3px;
                font-size: 12px;
                cursor: pointer;
                margin-top: 5px;
            }
            
            .btn-view-original:hover {
                background: #5a6268;
            }
            .feedback-time {
                color: #666;
                font-size: 12px;
            }
            .feedback-content {
                color: #444;
                line-height: 1.5;
                margin-bottom: 10px;
            }
            .reply-section {
                margin-top: 10px;
                padding-top: 10px;
                border-top: 1px solid #e9ecef;
            }
            .reply-form {
                display: none;
                margin-top: 10px;
            }
            .reply-form textarea {
                width: 100%;
                height: 60px;
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 4px;
                resize: vertical;
                margin-bottom: 8px;
            }
            .reply-btn {
                background: #6c757d;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                cursor: pointer;
            }
            .replies {
                margin-top: 10px;
            }
            .reply-item {
                background: white;
                border-radius: 6px;
                padding: 10px;
                margin-bottom: 8px;
                border-left: 3px solid #28a745;
            }
            .btn {
                background: linear-gradient(135deg, var(--primary-color) 0%, var(--secondary-color) 100%);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                width: 100%;
                transition: transform 0.2s, box-shadow 0.2s;
                margin-bottom: 20px;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 10px 20px var(--shadow-color);
            }
            .btn:disabled {
                background: #ccc;
                cursor: not-allowed;
                transform: none;
                box-shadow: none;
            }
            .status {
                margin-top: 25px;
                padding: 15px;
                border-radius: 8px;
                text-align: center;
                font-weight: bold;
            }
            .status.success {
                background: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status.error {
                background: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .status.info {
                background: #d1ecf1;
                color: #0c5460;
                border: 1px solid #bee5eb;
            }
            .loading {
                display: none;
                text-align: center;
                margin: 20px 0;
            }
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 10px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            .status-info {
                background: #f8f9fa;
                border-radius: 8px;
                padding: 15px;
                margin-top: 20px;
                font-size: 14px;
            }
            .status-item {
                display: flex;
                justify-content: space-between;
                margin-bottom: 8px;
            }
            .status-label {
                color: #666;
            }
            .status-value {
                font-weight: bold;
                color: #333;
            }
            .vm-info {
                background: var(--light-color);
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }
            .vm-info h3 {
                margin-top: 0;
                color: var(--dark-color);
            }
            .performance-info {
                background: var(--light-color);
                border-radius: 8px;
                padding: 15px;
                margin-top: 20px;
                font-size: 14px;
            }
            .performance-info h3 {
                margin-top: 0;
                color: #0c5460;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .progress-bar {
                height: 10px;
                background-color: #e9ecef;
                border-radius: 5px;
                margin-top: 5px;
                overflow: hidden;
            }
            .progress {
                height: 100%;
                border-radius: 5px;
                transition: width 0.3s ease;
            }
            .progress-cpu {
                background: linear-gradient(90deg, var(--success-color), #8BC34A);
            }
            .progress-memory {
                background: linear-gradient(90deg, #2196F3, var(--info-color));
            }
            .performance-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 10px;
            }
            .performance-item {
                margin-bottom: 10px;
            }
            .performance-label {
                font-weight: bold;
                color: #495057;
                margin-bottom: 5px;
            }
            .performance-value {
                color: #212529;
            }
            .timestamp {
                font-size: 12px;
                color: #6c757d;
                text-align: right;
                margin-top: 10px;
            }
            /* VNC控制区域样式 */
            .vnc-control {
                margin-top: 20px;
                padding: 15px;
                background: #f8f9fa;
                border-radius: 8px;
            }
            .vnc-control h3 {
                margin-top: 0;
                color: #495057;
            }
            .vnc-buttons {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-bottom: 15px;
            }
            .vnc-urls {
                margin-top: 10px;
                font-size: 12px;
                display: none;
            }
            .url-item {
                margin-bottom: 5px;
            }
            .url-link {
                color: #007bff;
                cursor: pointer;
                text-decoration: underline;
            }
            /* VNC连接统计 */
            .vnc-stats {
                background: #e8f4fd;
                border-radius: 8px;
                padding: 10px;
                margin-top: 10px;
                font-size: 12px;
            }
            .vnc-stat-item {
                display: flex;
                justify-content: space-between;
                margin-bottom: 5px;
            }
            
            /* 重启按钮特殊样式 */
            #forceRebootBtn {
                border: 2px solid #dc3545;
                animation: pulse-alert 2s infinite;
            }
            
            @keyframes pulse-alert {
                0% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(220, 53, 69, 0); }
                100% { box-shadow: 0 0 0 0 rgba(220, 53, 69, 0); }
            }
            
            .reboot-dialog-btn {
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: bold;
            }
            
            .reboot-confirm {
                background: var(--danger-color);
                color: white;
            }
            
            .reboot-cancel {
                background: var(--dark-color);
                color: white;
            }
        </style>
    </head>
    <body>
        <!-- 新年装饰元素 -->
        <div class="newyear-decoration lantern lantern-left" id="lanternLeft"></div>
        <div class="newyear-decoration lantern lantern-right" id="lanternRight"></div>
        <div id="fireworksContainer"></div>
        <div id="snowContainer"></div>
        
        <!-- 新年祝福语 -->
        <div class="newyear-greeting" id="newyearGreeting">🎉 新年快乐！马年大吉！ 🐎</div>
        
        <!-- 主题切换按钮 -->
        <button class="theme-toggle" id="themeToggle">
            <span class="icon" id="themeIcon">🎨</span>
            <span id="themeText">新年主题</span>
        </button>
        
        <div class="container" id="mainContent">
            <!-- 新增：页面访问人数显示 -->
            <div class="page-users" id="pageUsers">
                📊 页面访问: <span id="pageUserCount">0</span> / <span id="maxPageUsers">10</span> 人
            </div>
            
            <!-- 新增：VNC在线用户显示 -->
            <div class="vnc-users" id="vncUsers">
                VNC连接: <span id="vncUserCount">0</span> 人
            </div>
            
            <!-- 菜单按钮 -->
            <div class="menu-container">
                <button class="menu-btn" id="menuBtn">☰</button>
                <div class="dropdown-menu" id="dropdownMenu">
                    <a class="menu-item" href="#" onclick="showFeedbackModal()">反馈/建议</a>
                    <a class="menu-item" href="#" onclick="showFeedbackList()">我的反馈/建议</a>
                    <!-- 管理员专属菜单项，初始隐藏 -->
                    <a class="menu-item admin-only" href="/admin/feedback" target="_blank" style="display:none; color:#dc3545; font-weight:bold;">
                        🔐 管理后台
                    </a>
                    <!-- 用户管理菜单项 -->
                    <a class="menu-item admin-only" href="/admin/user-manager" target="_blank" style="display:none; color:#dc3545; font-weight:bold;">
                        👥 用户管理
                    </a>
                    <!-- 添加管理员入口 -->
                    <a class="menu-item" href="/admin/login" target="_blank" style="color: #dc3545; font-weight: bold;">
                        🔐 管理员入口
                    </a>
                    <!-- 账号设置 -->
                    <a class="menu-item" href="/account">
                        ⚙️ 账号设置
                    </a>
                    <!-- 退出登录 -->
                    <a class="menu-item" href="#" onclick="logout()" style="color: #6c757d;">
                        🚪 退出登录
                    </a>
                </div>
            </div>
            
            <div class="header">
                <h1>🖥️ Windows系统远程开机系统</h1>
                <p>危险、麻烦地远程启动Windows</p>
            </div>
            
            <div class="vm-info">
                <h3>虚拟机信息</h3>
                <div class="status-item">
                    <span class="status-label">虚拟机名称:</span>
                    <span class="status-value">''' + vm_status['vm_name'] + '''</span>
                </div>
                <div class="status-item">
                    <span class="status-label">配置文件:</span>
                    <span class="status-value">E:\\Hypv\\战神windows10</span>
                </div>
            </div>
            
            <button class="btn" id="startBtn">
                启动虚拟机
            </button>
            
            <!-- 添加重启按钮 (放在重启按钮后面) -->
            <button class="btn" onclick="forceRebootVM()" id="forceRebootBtn" style="background: linear-gradient(135deg, #fd7e14, #dc3545); margin-bottom: 10px;">
                ⚡ 重启系统
            </button>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>正在检测虚拟机状态并启动，请稍候...</p>
            </div>
            
            <div id="statusMessage"></div>
            
            <!-- VNC控制区域 -->
            <div class="vnc-control">
                <h3>🌐 Windows系统远程连接</h3>
                <p style="font-size: 14px; color: #666; margin-bottom: 10px;">
                    VNC服务器: <span id="vncServerInfo">''' + VNC_HOST + ''':''' + str(VNC_PORT) + ''' (自动获取本机IP)</span>
                </p>
                
                <!-- VNC连接统计 -->
                <div class="vnc-stats">
                    <div class="vnc-stat-item">
                        <span>当前连接:</span>
                        <span id="currentConnections">0</span>
                    </div>
                    <div class="vnc-stat-item">
                        <span>最大连接:</span>
                        <span id="maxConnections">0</span>
                    </div>
                    <div class="vnc-stat-item">
                        <span>状态:</span>
                        <span id="vncConnectionStatus">未启动</span>
                    </div>
                </div>
                
                <div class="vnc-buttons">
                    <button class="btn" onclick="startVNC()" id="startVNCBtn" style="background: linear-gradient(135deg, #17a2b8, #138496);">
                        启动VNC代理
                    </button>
                    <button class="btn" onclick="stopVNC()" id="stopVNCBtn" style="background: linear-gradient(135deg, #6c757d, #5a6268);">
                        停止VNC代理
                    </button>
                    <button class="btn" onclick="openPublicVNC()" id="openVNCBtn" style="background: linear-gradient(135deg, #28a745, #218838); grid-column: 1 / -1;">
                        打开Windows远程桌面
                    </button>
                </div>
                <div id="vncStatus" style="font-size: 14px; color: #666;">
                    VNC代理状态: <span id="vncStatusText">未启动</span>
                </div>
                <div id="vncUrls" class="vnc-urls">
                    <div class="url-item"><strong>访问地址:</strong></div>
                    <div class="url-item">本地: <span class="url-link" id="localUrl" onclick="openUrl('local')">加载中...</span></div>
                    <div class="url-item">局域网: <span class="url-link" id="networkUrl" onclick="openUrl('network')">加载中...</span></div>
                    <div class="url-item" id="publicUrlItem" style="display: none;">公网: <span class="url-link" id="publicUrl" onclick="openUrl('public')">加载中...</span></div>
                </div>
            </div>
            
            <!-- 网易UU远程协助提示 -->
            <div class="uuyc-info" style="margin-top: 20px; padding: 15px; background: #f0f7ff; border-radius: 8px; border-left: 4px solid #0078d4;">
                <h3 style="margin-top: 0; color: #0078d4; display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 20px;">🔗</span> 网易UU远程协助
                </h3>
                <p style="margin: 10px 0; font-size: 14px; color: #333;">
                    如果需要远程控制，您可以使用 <strong>网易UU远程</strong> 对我发起远程协助。
                </p>
                <div class="uuyc-details" style="background: white; padding: 12px; border-radius: 6px; margin: 10px 0;">
                    <div style="display: flex; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: bold; color: #0078d4; min-width: 80px;">设备ID：</span>
                        <span style="background: #e8f4fd; padding: 4px 10px; border-radius: 4px; font-family: 'Courier New', monospace; font-weight: bold;">852914126</span>
                    </div>
                    <div style="display: flex; align-items: center;">
                        <span style="font-weight: bold; color: #0078d4; min-width: 80px;">验证码：</span>
                        <span style="background: #e8f4fd; padding: 4px 10px; border-radius: 4px; font-family: 'Courier New', monospace; font-weight: bold;">XB5K9HD4</span>
                    </div>
                </div>
                <div style="margin-top: 12px;">
                    <a href="https://uuyc.163.com/" target="_blank" 
                       style="display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; background: linear-gradient(135deg, #0078d4, #005a9e); color: white; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">
                        <span>🌐</span>
                        下载网易UU远程
                    </a>
                    <p style="margin-top: 8px; font-size: 12px; color: #666;">
                        下载地址: <a href="https://uuyc.163.com/invite/8f369a51d72d4a959ae75b70dfbf42ca" target="_blank" style="color: #0078d4; text-decoration: underline;">https://uuyc.163.com/</a>
                    </p>
                </div>
                <div style="margin-top: 12px; padding: 10px; background: #fff3cd; border-radius: 6px; font-size: 12px; color: #856404;">
                    <strong>💡 使用提示：</strong>
                    <ul style="margin: 5px 0; padding-left: 20px;">
                        <li>输入设备ID和验证码即可发起远程协助</li>
                        <li>请确认您已安装网易UU远程客户端</li>
                        <li>此功能适用于Windows系统和安卓，TV之间的远程协助</li>
                    </ul>
                </div>
            </div>
            
            <div class="status-info">
                <h3>系统状态</h3>
                <div class="status-item">
                    <span class="status-label">运行状态:</span>
                    <span class="status-value" id="statusRunning">检查中...</span>
                </div>
                <div class="status-item">
                    <span class="status-label">最后启动时间:</span>
                    <span class="status-value" id="statusLastStart">-</span>
                </div>
                <div class="status-item">
                    <span class="status-label">最后错误:</span>
                    <span class="status-value" id="statusLastError">无</span>
                </div>
                <div class="status-item">
                    <span class="status-label">VMware界面:</span>
                    <span class="status-value" id="statusVmware">未打开</span>
                </div>
                <div class="status-item">
                    <span class="status-label">重启状态:</span>
                    <span class="status-value" id="statusReboot">
                        <span id="normalRebootStatus">-</span>
                        <span id="forceRebootStatus" style="color: #dc3545; display: none;">(重启中)</span>
                    </span>
                </div>
                <div class="status-item">
                    <span class="status-label">服务器IP:</span>
                    <span class="status-value">''' + LOCAL_IP + '''</span>
                </div>
                <div class="status-item">
                    <span class="status-label">VNC连接数:</span>
                    <span class="status-value" id="statusVncUsers">0 人</span>
                </div>
                <div class="status-item">
                    <span class="status-label">页面访问人数:</span>
                    <span class="status-value" id="statusPageUsers">0 / 10 人</span>
                </div>
            </div>
        </div>

        <!-- 反馈/建议模态框 -->
        <div class="modal" id="feedbackModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">反馈/建议</div>
                    <button class="close-btn" onclick="hideFeedbackModal()">×</button>
                </div>
                <div class="feedback-form">
                    <textarea id="feedbackContent" placeholder="请输入您的反馈或建议..."></textarea>
                    <button class="submit-btn" onclick="submitFeedback()">发布反馈</button>
                </div>
            </div>
        </div>

        <!-- 反馈列表模态框 -->
        <div class="modal" id="feedbackListModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">我的反馈/建议</div>
                    <button class="close-btn" onclick="hideFeedbackListModal()">×</button>
                </div>
                <div class="feedback-list" id="feedbackList">
                    <!-- 反馈列表将通过JavaScript动态加载 -->
                </div>
            </div>
        </div>

        <!-- 新增：人数上限提示模态框 -->
        <div class="modal" id="maxUsersModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">⚠️ 访问人数已满</div>
                    <button class="close-btn" onclick="hideMaxUsersModal()">×</button>
                </div>
                <div class="modal-body">
                    <p>当前页面访问人数已达到上限（10人），请稍后再试。</p>
                    <p>系统将自动为您排队，请在<span id="retryCountdown">30</span>秒后刷新页面重试。</p>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="location.reload()" style="background: linear-gradient(135deg, #667eea, #764ba2);">
                        立即刷新重试
                    </button>
                    <button class="btn" onclick="hideMaxUsersModal()" style="background: linear-gradient(135deg, #6c757d, #5a6268);">
                        稍后手动刷新
                    </button>
                </div>
            </div>
        </div>

        <!-- 重启确认对话框 -->
        <div class="modal" id="forceRebootModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">⚠️ 重启警告</div>
                    <button class="close-btn" onclick="hideForceRebootModal()">×</button>
                </div>
                <div class="modal-body">
                    <p><strong>警告：重启可能导致数据丢失！</strong></p>
                    <p>此操作将重启虚拟机，然后重新启动。</p>
                    <ul style="text-align: left; margin: 10px 0; padding-left: 20px;">
                        <li>任何未保存的数据将会丢失</li>
                        <li>可能损坏正在运行的程序</li>
                        <li>仅在系统完全卡死时使用</li>
                        <li>重启过程可能需要2-3分钟</li>
                    </ul>
                    <p>确定要继续吗？</p>
                </div>
                <div class="modal-footer">
                    <button class="reboot-dialog-btn reboot-cancel" onclick="hideForceRebootModal()" style="flex: 1;">
                        取消
                    </button>
                    <button class="reboot-dialog-btn reboot-confirm" onclick="confirmForceReboot()" style="flex: 1; background: #dc3545;">
                        重启
                    </button>
                </div>
            </div>
        </div>

        <!-- 新增：Socket.IO库 -->
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js"></script>
        <script>
            const startBtn = document.getElementById('startBtn');
            const loading = document.getElementById('loading');
            const statusMessage = document.getElementById('statusMessage');
            const menuBtn = document.getElementById('menuBtn');
            const dropdownMenu = document.getElementById('dropdownMenu');
            const feedbackModal = document.getElementById('feedbackModal');
            const feedbackListModal = document.getElementById('feedbackListModal');
            
            // 新增：页面访问人数监控功能
            let pageUserCount = 0;
            let maxPageUsers = 10;
            let isPageFull = false;
            
            // 新增：Socket.IO连接
            const socket = io();
            
            // 新增：Socket.IO事件处理
            socket.on('connect', function() {
                console.log('已连接到服务器');
                // 请求VNC统计信息
                socket.emit('get_vnc_stats');
                // 请求页面统计信息
                socket.emit('get_page_stats');
            });
            
            socket.on('disconnect', function() {
                console.log('与服务器断开连接');
            });
            
            // 新增：页面访问人数更新
            socket.on('page_user_count_update', function(data) {
                updatePageUserCount(data.current, data.max, data.is_full);
            });
            
            // 新增：VNC用户数更新
            socket.on('vnc_user_count_update', function(data) {
                updateVNCUserCount(data.current, data.max);
                updateVNCConnectionStatus(data.is_running);
            });
            
            // 监听重启完成事件
            socket.on('vm_force_reboot_complete', function(data) {
                document.getElementById('forceRebootStatus').style.display = 'none';
                document.getElementById('normalRebootStatus').textContent = data.success ? '正常' : '错误';
                
                if (data.success) {
                    showMessage('重启已完成！', 'success');
                } else {
                    showMessage('重启失败: ' + data.message, 'error');
                }
            });
            
            // 监听重启被拒绝事件
            socket.on('vm_force_reboot_rejected', function(data) {
                let message = '强制重启请求被拒绝';
                if (data.reason) {
                    message += '，理由：' + data.reason;
                }
                showMessage(message, 'error');
                resetForceRebootBtn(document.getElementById('forceRebootBtn'), '⚡ 强制重启系统');
            });
            
            // 新增：更新页面访问人数显示
            function updatePageUserCount(current, max, isFull) {
                pageUserCount = current;
                maxPageUsers = max;
                isPageFull = isFull;
                
                document.getElementById('pageUserCount').textContent = current;
                document.getElementById('maxPageUsers').textContent = max;
                document.getElementById('statusPageUsers').textContent = current + ' / ' + max + ' 人';
                
                const pageUsersElement = document.getElementById('pageUsers');
                pageUsersElement.classList.remove('near-limit', 'at-limit');
                
                if (isFull) {
                    pageUsersElement.classList.add('at-limit');
                    showMaxUsersModal();
                } else if (current >= max * 0.8) { // 达到80%时警告
                    pageUsersElement.classList.add('near-limit');
                }
            }
            
            // 新增：显示人数上限模态框
            function showMaxUsersModal() {
                const modal = document.getElementById('maxUsersModal');
                modal.classList.add('show');
                
                // 倒计时功能
                let countdown = 30;
                const countdownElement = document.getElementById('retryCountdown');
                const countdownInterval = setInterval(() => {
                    countdown--;
                    countdownElement.textContent = countdown;
                    
                    if (countdown <= 0) {
                        clearInterval(countdownInterval);
                        hideMaxUsersModal();
                    }
                }, 1000);
            }
            
            // 新增：隐藏人数上限模态框
            function hideMaxUsersModal() {
                const modal = document.getElementById('maxUsersModal');
                modal.classList.remove('show');
            }
            
            // 新增：更新VNC用户计数
            function updateVNCUserCount(current, max) {
                document.getElementById('vncUserCount').textContent = current;
                document.getElementById('statusVncUsers').textContent = current + ' 人';
                document.getElementById('currentConnections').textContent = current;
                document.getElementById('maxConnections').textContent = max;
                
                // 根据连接数量改变颜色
                const vncUsersElement = document.getElementById('vncUsers');
                vncUsersElement.classList.remove('high-usage', 'max-usage');
                
                if (current === 0) {
                    vncUsersElement.style.background = '#6c757d';
                } else if (current < 3) {
                    vncUsersElement.style.background = '#17a2b8';
                } else if (current < 5) {
                    vncUsersElement.classList.add('high-usage');
                } else {
                    vncUsersElement.classList.add('max-usage');
                }
            }
            
            // 新增：更新VNC连接状态
            function updateVNCConnectionStatus(isRunning) {
                const statusElement = document.getElementById('vncConnectionStatus');
                if (isRunning) {
                    statusElement.textContent = '运行中';
                    statusElement.style.color = '#28a745';
                } else {
                    statusElement.textContent = '未启动';
                    statusElement.style.color = '#dc3545';
                }
            }
            
            // 菜单显示/隐藏
            menuBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                dropdownMenu.classList.toggle('show');
            });
            
            // 点击其他地方关闭菜单
            document.addEventListener('click', function() {
                dropdownMenu.classList.remove('show');
            });
            
            // 显示反馈模态框
            function showFeedbackModal() {
                feedbackModal.classList.add('show');
                dropdownMenu.classList.remove('show');
            }
            
            // 隐藏反馈模态框
            function hideFeedbackModal() {
                feedbackModal.classList.remove('show');
            }
            
            // 显示反馈列表模态框
            function showFeedbackList() {
                feedbackListModal.classList.add('show');
                dropdownMenu.classList.remove('show');
                loadFeedbackList();
            }
            
            // 隐藏反馈列表模态框
            function hideFeedbackListModal() {
                feedbackListModal.classList.remove('show');
            }
            
            // 提交反馈
            async function submitFeedback() {
                const content = document.getElementById('feedbackContent').value.trim();
                if (!content) {
                    alert('请输入反馈内容');
                    return;
                }
                
                // 客户端敏感词检查（可选，减少服务器压力）
                const sensitiveWords = ["傻逼", "混蛋", "垃圾", "白痴", "脑残", "弱智", "废物", "蠢货", "操你妈", "fuck", "shit"];
                let hasSensitiveWord = false;
                for (const word of sensitiveWords) {
                    if (content.includes(word)) {
                        hasSensitiveWord = true;
                        
                        // 提示用户
                        const confirmSubmit = confirm(`您的反馈中包含可能不文明的词语"${word}"。\n系统将自动进行处理。\n\n是否确认提交？`);
                        if (!confirmSubmit) {
                            return;
                        }
                        break;
                    }
                }
                
                // 显示提交中状态
                const submitBtn = document.querySelector('#feedbackModal .submit-btn');
                const originalText = submitBtn.textContent;
                submitBtn.disabled = true;
                submitBtn.textContent = '提交中...';
                
                try {
                    const response = await fetch('/api/feedback', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            content: content
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        alert(data.message);
                        document.getElementById('feedbackContent').value = '';
                        hideFeedbackModal();
                        
                        // 如果提交成功且有敏感词，显示额外提示
                        if (data.has_sensitive) {
                            setTimeout(() => {
                                showMessage('请注意文明用语，网络不是法外之地。', 'warning');
                            }, 1000);
                        }
                    } else {
                        alert('提交失败：' + data.message);
                    }
                } catch (error) {
                    console.error('提交反馈失败:', error);
                    alert('网络错误，请稍后重试');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
            
            // 加载反馈列表
            async function loadFeedbackList() {
                try {
                    const response = await fetch('/api/feedback');
                    const data = await response.json();
                    
                    const feedbackList = document.getElementById('feedbackList');
                    feedbackList.innerHTML = '';
                    
                    if (data.feedbacks && data.feedbacks.length > 0) {
                        // 按时间排序（最新的在前）
                        const sortedFeedbacks = data.feedbacks.sort((a, b) => {
                            return new Date(b.timestamp) - new Date(a.timestamp);
                        });
                        
                        sortedFeedbacks.forEach(feedback => {
                            const feedbackItem = createFeedbackItemHTML(feedback);
                            feedbackList.innerHTML += feedbackItem;
                        });
                    } else {
                        feedbackList.innerHTML = '<p style="text-align: center; color: #666;">暂无反馈</p>';
                    }
                } catch (error) {
                    console.error('加载反馈列表失败:', error);
                    document.getElementById('feedbackList').innerHTML = `
                        <div style="text-align: center; color: #666; padding: 20px;">
                            <p>加载失败</p>
                            <button onclick="loadFeedbackList()" style="padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 4px; cursor: pointer;">
                                重新加载
                            </button>
                        </div>
                    `;
                }
            }
            
            // 创建反馈项HTML - 增强兼容性
            function createFeedbackItemHTML(feedback) {
                // 确保必要字段存在
                const feedbackId = feedback.id || `temp_${Date.now()}_${Math.random()}`;
                const author = feedback.author || '用户';
                const content = feedback.content || '内容已丢失';
                const timestamp = feedback.timestamp || new Date().toISOString();
                const replies = feedback.replies || [];
                const hasSensitive = feedback.has_sensitive || false;
                
                // 创建敏感词标记
                let sensitiveBadge = '';
                if (hasSensitive) {
                    sensitiveBadge = '<span class="sensitive-badge" style="background: #dc3545; color: white; padding: 2px 6px; border-radius: 3px; font-size: 10px; margin-left: 5px;">⚠️ 已过滤</span>';
                }
                
                // 创建回复HTML
                let repliesHtml = '';
                if (replies && replies.length > 0) {
                    replies.forEach(reply => {
                        // 根据is_admin或author判断是否为管理员回复
                        const isAdminReply = reply.is_admin || reply.author === '管理员';
                        const authorBadge = isAdminReply ? 
                            '<span style="color: #dc3545; font-weight: bold; margin-left: 5px;">👑 管理员</span>' : 
                            '<span style="color: #28a745; margin-left: 5px;">👤 用户</span>';
                        
                        repliesHtml += `
                            <div class="reply-item" style="border-left: ${isAdminReply ? '3px solid #dc3545' : '3px solid #28a745'};">
                                <div class="feedback-header">
                                    <span class="feedback-author">${reply.author || '用户'}${authorBadge}</span>
                                    <span class="feedback-time">${formatTime(reply.timestamp || timestamp)}</span>
                                </div>
                                <div class="feedback-content">${reply.content || ''}</div>
                            </div>
                        `;
                    });
                }
                
                return `
                    <div class="feedback-item">
                        <div class="feedback-header">
                            <span class="feedback-author">
                                ${author}
                                ${sensitiveBadge}
                            </span>
                            <span class="feedback-time">${formatTime(timestamp)}</span>
                        </div>
                        <div class="feedback-content">${content}</div>
                        <div class="reply-section">
                            <button class="reply-btn" onclick="toggleReplyForm('${feedbackId}')">回复</button>
                            <div class="reply-form" id="replyForm-${feedbackId}" style="display: none;">
                                <textarea id="replyContent-${feedbackId}" placeholder="请输入回复内容..."></textarea>
                                <button class="reply-btn" onclick="submitReply('${feedbackId}')">提交回复</button>
                            </div>
                            <div class="replies">
                                ${repliesHtml}
                            </div>
                        </div>
                    </div>
                `;
            }
            
            // 切换回复表单显示
            function toggleReplyForm(feedbackId) {
                const replyForm = document.getElementById(`replyForm-${feedbackId}`);
                replyForm.style.display = replyForm.style.display === 'block' ? 'none' : 'block';
            }
            
            // 提交回复
            async function submitReply(feedbackId) {
                const content = document.getElementById(`replyContent-${feedbackId}`).value.trim();
                if (!content) {
                    alert('请输入回复内容');
                    return;
                }
                
                // 禁用按钮防止重复提交
                const submitBtn = document.querySelector(`#replyForm-${feedbackId} .reply-btn`);
                const originalText = submitBtn.textContent;
                submitBtn.disabled = true;
                submitBtn.textContent = '提交中...';
                
                try {
                    const response = await fetch('/api/feedback/reply', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-Reply-Source': 'user'  // 标记来自用户页面
                        },
                        body: JSON.stringify({
                            feedback_id: feedbackId,
                            content: content
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        alert('回复成功！' + (data.is_admin ? '（管理员回复）' : '（用户回复）'));
                        document.getElementById(`replyContent-${feedbackId}`).value = '';
                        document.getElementById(`replyForm-${feedbackId}`).style.display = 'none';
                        loadFeedbackList(); // 重新加载列表
                    } else {
                        alert('回复失败：' + data.message);
                    }
                } catch (error) {
                    console.error('提交回复失败:', error);
                    alert('网络错误，请稍后重试');
                } finally {
                    // 恢复按钮状态
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }
            }
            
            // 管理员查看原始内容
            async function viewOriginalContent(feedbackId) {
                try {
                    // 这里可以添加管理员验证
                    const response = await fetch(`/api/feedback/original/${feedbackId}`);
                    const data = await response.json();
                    
                    if (data.success) {
                        const modal = document.createElement('div');
                        modal.className = 'modal show';
                        modal.innerHTML = `
                            <div class="modal-content">
                                <div class="modal-header">
                                    <div class="modal-title">🔍 原始反馈内容</div>
                                    <button class="close-btn" onclick="this.parentElement.parentElement.parentElement.remove()">×</button>
                                </div>
                                <div class="modal-body">
                                    <p><strong>原始内容:</strong></p>
                                    <div style="background: #f8f9fa; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                                        ${data.original_content}
                                    </div>
                                    
                                    <p><strong>过滤后内容:</strong></p>
                                    <div style="background: #e9ecef; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                                        ${data.filtered_content}
                                    </div>
                                    
                                    <p><strong>作者:</strong> ${data.author}</p>
                                    <p><strong>IP地址:</strong> ${data.client_ip || '未知'}</p>
                                    <p><strong>检测到敏感词:</strong> ${data.has_sensitive ? '是' : '否'}</p>
                                </div>
                                <div class="modal-footer">
                                    <button class="btn" onclick="this.parentElement.parentElement.parentElement.remove()" 
                                            style="background: linear-gradient(135deg, #6c757d, #5a6268);">
                                        关闭
                                    </button>
                                </div>
                            </div>
                        `;
                        document.body.appendChild(modal);
                    } else {
                        alert('获取原始内容失败: ' + data.message);
                    }
                } catch (error) {
                    console.error('获取原始内容失败:', error);
                    alert('网络错误');
                }
            }
            
            // 格式化时间
            function formatTime(timestamp) {
                const date = new Date(timestamp);
                return date.toLocaleString('zh-CN');
            }
            
            // 更新状态显示
            async function updateStatus() {
                try {
                    const response = await fetch('/api/status');
                    const data = await response.json();
                    
                    document.getElementById('statusRunning').textContent = 
                        data.is_running ? '运行中' : '已停止';
                    document.getElementById('statusRunning').style.color = 
                        data.is_running ? '#28a745' : '#dc3545';
                    
                    document.getElementById('statusLastStart').textContent = 
                        data.last_start_time ? new Date(data.last_start_time).toLocaleString() : '-';
                    
                    document.getElementById('statusLastError').textContent = 
                        data.last_error || '无';
                    
                    document.getElementById('statusVmware').textContent = 
                        data.vmware_opened ? '已打开' : '未打开';
                    document.getElementById('statusVmware').style.color = 
                        data.vmware_opened ? '#28a745' : '#dc3545';
                    
                    // 如果正在运行，禁用按钮
                    startBtn.disabled = data.is_running;
                    
                } catch (error) {
                    console.error('获取状态失败:', error);
                    document.getElementById('statusRunning').textContent = '连接失败';
                    document.getElementById('statusRunning').style.color = '#dc3545';
                }
            }            
            // 新增：定期获取页面统计
            async function updatePageStats() {
                try {
                    const response = await fetch('/api/page/stats');
                    const data = await response.json();
                    updatePageUserCount(data.current, data.max, data.is_full);
                } catch (error) {
                    console.error('获取页面统计失败:', error);
                }
            }
            
            // VNC代理功能
            async function startVNC() {
                const btn = document.getElementById('startVNCBtn');
                btn.disabled = true;
                btn.textContent = '启动中...';
                
                try {
                    const response = await fetch('/api/vnc/start', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        showMessage('VNC代理启动成功', 'success');
                        updateVNCStatus(true, data.urls);
                        // 请求更新VNC统计
                        socket.emit('get_vnc_stats');
                    } else {
                        showMessage('VNC代理启动失败: ' + data.message, 'error');
                    }
                } catch (error) {
                    console.error('启动VNC失败:', error);
                    showMessage('网络错误，请稍后重试', 'error');
                } finally {
                    btn.disabled = false;
                    btn.textContent = '启动VNC代理';
                }
            }
            
            async function stopVNC() {
                try {
                    const response = await fetch('/api/vnc/stop', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        showMessage('VNC代理已停止', 'success');
                        updateVNCStatus(false, {});
                        // 重置VNC统计显示
                        updateVNCUserCount(0, 0);
                    } else {
                        showMessage('停止VNC代理失败: ' + data.message, 'error');
                    }
                } catch (error) {
                    console.error('停止VNC失败:', error);
                    showMessage('网络错误，请稍后重试', 'error');
                }
            }
            
            // 打开公网VNC地址
            function openPublicVNC() {
                window.open('https://4ed98fcf.vip.cpolar.top/vnc.html', '_blank');
                showMessage('正在打开Windows远程桌面...', 'success');
            }
            
            function updateVNCStatus(isRunning, urls) {
                const statusText = document.getElementById('vncStatusText');
                const urlsDiv = document.getElementById('vncUrls');
                const startBtn = document.getElementById('startVNCBtn');
                const stopBtn = document.getElementById('stopVNCBtn');
                
                if (isRunning) {
                    statusText.textContent = '运行中';
                    statusText.style.color = '#28a745';
                    urlsDiv.style.display = 'block';
                    startBtn.disabled = true;
                    stopBtn.disabled = false;
                    
                    // 更新URL显示
                    if (urls.local) {
                        document.getElementById('localUrl').textContent = urls.local;
                        document.getElementById('localUrl').setAttribute('data-url', urls.local);
                    }
                    if (urls.network) {
                        document.getElementById('networkUrl').textContent = urls.network;
                        document.getElementById('networkUrl').setAttribute('data-url', urls.network);
                    }
                    if (urls.public) {
                        document.getElementById('publicUrlItem').style.display = 'block';
                        document.getElementById('publicUrl').textContent = urls.public;
                        document.getElementById('publicUrl').setAttribute('data-url', urls.public);
                    }
                } else {
                    statusText.textContent = '未启动';
                    statusText.style.color = '#dc3545';
                    urlsDiv.style.display = 'none';
                    startBtn.disabled = false;
                    stopBtn.disabled = true;
                }
            }
            
            function openUrl(type) {
                const element = document.getElementById(type + 'Url');
                const url = element.getAttribute('data-url');
                if (url && url !== '加载中...') {
                    window.open(url, '_blank');
                }
            }
            
            // 定期更新VNC状态
            async function updateVNCStatusPeriodically() {
                try {
                    const response = await fetch('/api/vnc/status');
                    const data = await response.json();
                    updateVNCStatus(data.is_running, data.urls);
                } catch (error) {
                    console.error('获取VNC状态失败:', error);
                }
            }
            
            // 定期更新状态
            setInterval(updateStatus, 3000);
            updateStatus(); // 初始更新
            
            // 定期更新VNC状态
            setInterval(updateVNCStatusPeriodically, 5000);
            updateVNCStatusPeriodically(); // 初始更新
            
            // 初始化页面统计
            updatePageStats();
            setInterval(updatePageStats, 10000); // 每10秒更新一次
            
            startBtn.addEventListener('click', async () => {
                // 显示加载中
                loading.style.display = 'block';
                startBtn.disabled = true;
                statusMessage.innerHTML = '';
                
                try {
                    const response = await fetch('/api/start-vm', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        showMessage(data.message, 'success');
                    } else {
                        showMessage(data.message, 'error');
                    }
                    
                } catch (error) {
                    console.error('请求失败:', error);
                    showMessage('网络请求失败，请检查服务器状态', 'error');
                } finally {
                    loading.style.display = 'none';
                    // 状态会在下次更新时自动启用按钮
                }
            });
            
            // 修改 forceRebootVM 函数，添加申请理由输入框
            function forceRebootVM() {
                // 创建申请理由输入模态框
                const reasonModal = document.createElement('div');
                reasonModal.id = 'forceRebootReasonModal';
                reasonModal.className = 'modal';
                reasonModal.innerHTML = `
                    <div class="modal-content">
                        <div class="modal-header">
                            <div class="modal-title">📝 重启申请理由</div>
                            <button class="close-btn" onclick="document.getElementById('forceRebootReasonModal').classList.remove('show')">×</button>
                        </div>
                        <div class="modal-body">
                            <p><strong>请说明重启的理由：</strong></p>
                            <p style="font-size: 14px; color: #666; margin-bottom: 10px;">
                                例如：系统无响应、程序卡死、需要紧急维护等<br>
                                <span style="color: #dc3545;">* 请简要说明原因（1-200个字符）</span>
                            </p>
                            <textarea id="forceRebootReason" placeholder="请输入重启的理由..." 
                                      oninput="updateCharCount()"
                                      style="width: 100%; height: 120px; padding: 12px; border: 2px solid #e1e5e9; border-radius: 8px; font-size: 14px; resize: vertical; margin-bottom: 10px;"></textarea>
                            <div style="text-align: right; margin-bottom: 15px; font-size: 14px;">
                                <span id="charCount">0</span>/200 字符
                            </div>
                            <div style="display: flex; gap: 10px;">
                                <button class="reboot-dialog-btn reboot-cancel" onclick="document.getElementById('forceRebootReasonModal').classList.remove('show')" style="flex: 1;">
                                    取消
                                </button>
                                <button class="reboot-dialog-btn reboot-confirm" onclick="submitForceRebootRequest()" style="flex: 1; background: #dc3545;">
                                    提交申请
                                </button>
                            </div>
                        </div>
                    </div>
                `;
                
                // 添加到页面
                if (!document.getElementById('forceRebootReasonModal')) {
                    document.body.appendChild(reasonModal);
                }
                
                // 显示理由输入框
                document.getElementById('forceRebootReasonModal').classList.add('show');
                
                // 重置字符计数器
                setTimeout(() => {
                    updateCharCount();
                }, 100);
            }
            
            // 新增函数：更新字符计数
            function updateCharCount() {
                const textarea = document.getElementById('forceRebootReason');
                const charCountElement = document.getElementById('charCount');
                
                if (textarea && charCountElement) {
                    const length = textarea.value.length;
                    charCountElement.textContent = length;
                    
                    // 根据字符数改变颜色
                    if (length > 200) {
                        charCountElement.style.color = '#dc3545'; // 红色，超过限制
                    } else if (length > 150) {
                        charCountElement.style.color = '#fd7e14'; // 橙色，接近限制
                    } else {
                        charCountElement.style.color = '#28a745'; // 绿色，正常
                    }
                }
            }
            
            // 新的函数：提交重启申请
            function submitForceRebootRequest() {
                const reason = document.getElementById('forceRebootReason').value.trim();
                
                if (!reason) {
                    alert('请填写重启申请理由');
                    return;
                }
                
                // 最小字数检查（至少1个字符）
                if (reason.length < 1) {
                    alert('申请理由不能为空，请说明重启原因');
                    return;
                }
                
                // 新增：最大字数检查（最多200个字符）
                if (reason.length > 200) {
                    alert('申请理由不能超过200个字符，请简要说明');
                    return;
                }
                
                // 隐藏理由输入框
                document.getElementById('forceRebootReasonModal').classList.remove('show');
                
                // 显示确认对话框
                document.getElementById('forceRebootModal').classList.add('show');
                
                // 保存申请理由到全局变量，供确认时使用
                window.forceRebootReason = reason;
            }
            
            function hideForceRebootModal() {
                document.getElementById('forceRebootModal').classList.remove('show');
            }
            
            // 修改 confirmForceReboot 函数，包含申请理由
            function confirmForceReboot() {
                hideForceRebootModal();
                
                const btn = document.getElementById('forceRebootBtn');
                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '提交请求中...';
                btn.style.background = 'linear-gradient(135deg, #6c757d, #5a6268)';
                
                // 获取申请理由
                const reason = window.forceRebootReason || '';
                
                // 发送重启请求，包含申请理由
                fetch('/api/force-reboot-vm', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        reason: reason
                    })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.status === 'pending_confirmation') {
                        const confirmId = data.confirm_id;
                        showMessage('重启请求已提交，请在3分钟内通过管理页面确认...', 'info');
                        
                        // 显示申请理由
                        if (data.reason) {
                            showMessage(`申请理由: ${data.reason}`, 'info');
                        }
                        
                        // 开始轮询确认状态
                        pollConfirmationStatus(confirmId, btn, originalText);
                        
                    } else {
                        showMessage('请求失败: ' + (data.message || '未知错误'), 'error');
                        resetForceRebootBtn(btn, originalText);
                    }
                })
                .catch(error => {
                    console.error('重启请求失败:', error);
                    showMessage('网络错误: ' + error.message, 'error');
                    resetForceRebootBtn(btn, originalText);
                });
            }
            
            function pollConfirmationStatus(confirmId, btn, originalText) {
                let pollCount = 0;
                const maxPolls = 200; // 3分20秒
                
                const pollInterval = setInterval(() => {
                    pollCount++;
                    
                    fetch(`/api/force-reboot/status/${confirmId}`)
                        .then(response => response.json())
                        .then(statusData => {
                            if (!statusData.found) {
                                clearInterval(pollInterval);
                                showMessage('确认请求已过期', 'error');
                                resetForceRebootBtn(btn, originalText);
                                return;
                            }
                            
                            if (statusData.confirmed) {
                                clearInterval(pollInterval);
                                
                                if (statusData.approved) {
                                    // 管理员允许
                                    btn.textContent = '重启执行中...';
                                    showMessage('正在重启系统...', 'success');
                                    
                                    // 显示倒计时
                                    let countdown = 120;
                                    const countdownInterval = setInterval(() => {
                                        if (countdown <= 0) {
                                            clearInterval(countdownInterval);
                                            resetForceRebootBtn(btn, originalText);
                                            showMessage('重启预计已完成', 'info');
                                        } else {
                                            btn.textContent = `重启中 (${Math.floor(countdown/60)}:${String(countdown%60).padStart(2, '0')})`;
                                            countdown--;
                                        }
                                    }, 1000);
                                } else {
                                    // 被拒绝或超时拒绝
                                    let rejectMsg = statusData.timeout ? '请求超时，已自动拒绝' : '强制重启请求被拒绝';
                                    if (statusData.reject_reason) {
                                        rejectMsg += '，理由：' + statusData.reject_reason;
                                    }
                                    showMessage(rejectMsg, 'error');
                                    resetForceRebootBtn(btn, originalText);
                                }
                            } else {
                                // 仍在等待确认，显示剩余时间
                                const remaining = statusData.remaining_seconds || 180 - pollCount;
                                const mins = Math.floor(remaining / 60);
                                const secs = remaining % 60;
                                
                                btn.textContent = `等待确认... (${mins}:${String(secs).padStart(2, '0')})`;
                                
                                // 每30秒提醒一次管理页面地址
                                if (pollCount % 30 === 0) {
                                    let infoMsg = '请管理员在' + mins + ':' + String(secs).padStart(2, '0') + '内确认，否则将自动拒绝';
                                    if (statusData.reason) {
                                        infoMsg += '，申请理由: ' + statusData.reason;
                                    }
                                    showMessage(infoMsg, 'info');
                                }
                            }
                        })
                        .catch(error => {
                            console.error('轮询状态失败:', error);
                        });
                    
                    if (pollCount > maxPolls) {
                        clearInterval(pollInterval);
                        showMessage('确认请求超时，已自动拒绝', 'error');
                        resetForceRebootBtn(btn, originalText);
                    }
                }, 1000);
            }
            
            function resetForceRebootBtn(btn, originalText) {
                btn.disabled = false;
                btn.textContent = originalText;
                btn.style.background = 'linear-gradient(135deg, #fd7e14, #dc3545)';
            }
            
            function showMessage(message, type) {
                statusMessage.innerHTML = `
                    <div class="status ${type}">
                        ${message}
                    </div>
                `;
            }
            
            // 主题切换功能
            const themeToggle = document.getElementById('themeToggle');
            const themeIcon = document.getElementById('themeIcon');
            const themeText = document.getElementById('themeText');
            const html = document.documentElement;
            
            // 检查本地存储的主题设置
            const savedTheme = localStorage.getItem('theme') || 'default';
            html.setAttribute('data-theme', savedTheme);
            updateThemeButton(savedTheme);
            
            // 切换主题
            themeToggle.addEventListener('click', () => {
                const currentTheme = html.getAttribute('data-theme');
                const newTheme = currentTheme === 'default' ? 'newyear' : 'default';
                
                html.setAttribute('data-theme', newTheme);
                localStorage.setItem('theme', newTheme);
                updateThemeButton(newTheme);
                
                // 切换新年特效
                toggleNewYearEffects(newTheme === 'newyear');
            });
            
            // 更新主题按钮
            function updateThemeButton(theme) {
                if (theme === 'newyear') {
                    themeIcon.textContent = '🏮';
                    themeText.textContent = '默认主题';
                    themeToggle.style.background = 'linear-gradient(45deg, #d62828, #f77f00)';
                } else {
                    themeIcon.textContent = '🎨';
                    themeText.textContent = '新年主题';
                    themeToggle.style.background = 'linear-gradient(45deg, #667eea, #764ba2)';
                }
            }
            
            // 新年特效
            function toggleNewYearEffects(enable) {
                const greeting = document.getElementById('newyearGreeting');
                const lanternLeft = document.getElementById('lanternLeft');
                const lanternRight = document.getElementById('lanternRight');
                const fireworksContainer = document.getElementById('fireworksContainer');
                const snowContainer = document.getElementById('snowContainer');
                
                if (enable) {
                    // 显示新年元素
                    greeting.style.display = 'block';
                    lanternLeft.style.display = 'block';
                    lanternRight.style.display = 'block';
                    
                    // 创建烟花效果
                    createFireworks();
                    
                    // 创建雪花效果
                    createSnowflakes();
                    
                    // 播放新年音乐（可选）
                    playNewYearMusic();
                } else {
                    // 隐藏新年元素
                    greeting.style.display = 'none';
                    lanternLeft.style.display = 'none';
                    lanternRight.style.display = 'none';
                    
                    // 清除烟花和雪花
                    if (fireworksContainer) fireworksContainer.innerHTML = '';
                    if (snowContainer) snowContainer.innerHTML = '';
                    
                    // 停止音乐
                    stopNewYearMusic();
                }
            }
            
            // 创建烟花效果
            function createFireworks() {
                const container = document.getElementById('fireworksContainer');
                if (!container) return;
                
                // 创建多个烟花
                for (let i = 0; i < 10; i++) {
                    setTimeout(() => {
                        const firework = document.createElement('div');
                        firework.className = 'firework';
                        firework.style.left = `${Math.random() * 100}%`;
                        firework.style.top = `${Math.random() * 80}%`;
                        firework.style.animationDelay = `${Math.random() * 2}s`;
                        firework.style.backgroundColor = getRandomColor();
                        
                        container.appendChild(firework);
                        
                        // 移除烟花元素
                        setTimeout(() => {
                            if (firework.parentNode === container) {
                                container.removeChild(firework);
                            }
                        }, 1500);
                    }, i * 300);
                }
                
                // 定期创建新的烟花
                if (window.fireworksInterval) clearInterval(window.fireworksInterval);
                window.fireworksInterval = setInterval(createFireworks, 3000);
            }
            
            // 创建雪花效果
            function createSnowflakes() {
                const container = document.getElementById('snowContainer');
                if (!container) return;
                
                container.innerHTML = '';
                
                // 创建多个雪花
                for (let i = 0; i < 50; i++) {
                    const snowflake = document.createElement('div');
                    snowflake.className = 'snowflake';
                    snowflake.style.left = `${Math.random() * 100}%`;
                    snowflake.style.animationDelay = `${Math.random() * 5}s`;
                    snowflake.style.animationDuration = `${5 + Math.random() * 10}s`;
                    snowflake.style.opacity = `${0.3 + Math.random() * 0.7}`;
                    snowflake.style.width = `${3 + Math.random() * 7}px`;
                    snowflake.style.height = snowflake.style.width;
                    
                    container.appendChild(snowflake);
                }
            }
            
            // 随机颜色生成
            function getRandomColor() {
                const colors = ['#ff0000', '#ff9500', '#ffff00', '#00ff00', '#00ffff', '#ff00ff'];
                return colors[Math.floor(Math.random() * colors.length)];
            }
            
            // 新年音乐（可选）
            function playNewYearMusic() {
                // 这里可以添加新年音乐的播放逻辑
                // 例如：const audio = new Audio('newyear-music.mp3');
                // audio.loop = true;
                // audio.volume = 0.3;
                // audio.play();
                // window.newYearAudio = audio;
                console.log('新年音乐播放（示例）');
            }
            
            function stopNewYearMusic() {
                if (window.newYearAudio) {
                    window.newYearAudio.pause();
                    window.newYearAudio = null;
                }
            }
            
            // 页面加载时检查是否需要显示新年特效
            document.addEventListener('DOMContentLoaded', () => {
                const currentTheme = html.getAttribute('data-theme');
                toggleNewYearEffects(currentTheme === 'newyear');
                
                // 添加主题切换提示
                if (currentTheme === 'default') {
                    setTimeout(() => {
                        showMessage('🎉 点击右上角按钮切换新年主题！', 'info');
                    }, 2000);
                }
            });
        </script>
        
        <!-- 登录/注册模态框 -->
        <div class="modal" id="authModal" style="display: none;">
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <div class="modal-title" id="authModalTitle">登录</div>
                    <button class="close-btn" onclick="hideAuthModal()">×</button>
                </div>
                <div class="modal-body">
                    <div id="loginForm">
                        <div style="margin-bottom: 15px;">
                            <label>用户名</label>
                            <input type="text" id="loginUsername" placeholder="请输入用户名" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label>密码</label>
                            <input type="password" id="loginPassword" placeholder="请输入密码" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                        </div>
                        <button class="btn" onclick="doLogin()" style="margin-bottom:10px; width:100%;">登录</button>
                        
                        <!-- 管理员登录链接 -->
                        <div style="text-align:center; margin-top: 10px;">
                            <a href="/admin/login" target="_blank" style="color: #667eea; text-decoration: none; font-size: 14px;">
                                🔐 管理员登录（新窗口）
                            </a>
                        </div>
                        
                        <p style="text-align:center;">还没有账号？ <a href="#" onclick="showRegister()">立即注册</a></p>
                    </div>
                    <div id="registerForm" style="display:none;">
                        <div style="margin-bottom: 15px;">
                            <label>用户名（自动生成）</label>
                            <input type="text" id="registerUsername" readonly style="width:100%; padding:8px; border:1px solid #ddd; border-radius:4px; background:#f5f5f5;">
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label>密码</label>
                            <input type="password" id="registerPassword" placeholder="至少6位" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label>确认密码</label>
                            <input type="password" id="registerConfirm" placeholder="再次输入密码" style="width:100%; padding:8px; border:1px solid #ddd; border-radius:4px;">
                        </div>
                        <button class="btn" onclick="doRegister()" style="margin-bottom:10px; width:100%;">注册</button>
                        <p style="text-align:center;">已有账号？ <a href="#" onclick="showLogin()">去登录</a></p>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
        console.log('Script started');
        
        var isEvading = false;
        var loginBtn = null;

        function initEvadeButton() {
            if (!loginBtn) {
                loginBtn = document.querySelector('#authModal #loginForm .btn');
            }
        }

        function activateEvadeMode() {
            if (isEvading) return;
            isEvading = true;
            initEvadeButton();
            if (loginBtn) {
                var btnWidth = loginBtn.offsetWidth;
                var btnHeight = loginBtn.offsetHeight;
                loginBtn.style.width = btnWidth + 'px';
                loginBtn.style.height = btnHeight + 'px';
                loginBtn.style.position = 'fixed';
                loginBtn.style.zIndex = '9999';
                loginBtn.style.transition = 'all 0.2s ease';
            }
        }

        function moveButtonRandomly() {
            if (!loginBtn) initEvadeButton();
            if (!loginBtn) return;
            var viewportWidth = window.innerWidth;
            var viewportHeight = window.innerHeight;
            var btnWidth = loginBtn.offsetWidth;
            var btnHeight = loginBtn.offsetHeight;
            var maxLeft = viewportWidth - btnWidth;
            var maxTop = viewportHeight - btnHeight;
            var left = Math.random() * maxLeft;
            var top = Math.random() * maxTop;
            loginBtn.style.left = left + 'px';
            loginBtn.style.top = top + 'px';
        }
        
        // 登录/注册相关函数
        function showAuthModal() {
            document.getElementById('authModal').style.display = 'flex';
        }
        
        function hideAuthModal() {
            document.getElementById('authModal').style.display = 'none';
        }
        
        function showLogin() {
            document.getElementById('loginForm').style.display = 'block';
            document.getElementById('registerForm').style.display = 'none';
            document.getElementById('authModalTitle').textContent = '登录';
        }
        
        function showRegister() {
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('registerForm').style.display = 'block';
            document.getElementById('authModalTitle').textContent = '注册';
            
            // 获取下一个用户名
            fetch('/api/next-username')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('registerUsername').value = data.username;
                    }
                })
                .catch(error => console.error('获取用户名失败:', error));
        }
        
        function doLogin() {
            const username = document.getElementById('loginUsername').value;
            const password = document.getElementById('loginPassword').value;
            
            if (!username || !password) {
                alert('请输入用户名和密码');
                return;
            }
            
            fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: username, password: password})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    hideAuthModal();
                    document.getElementById('mainContent').style.display = 'block';
                    loadCurrentUser();
                    if (data.is_admin) {
                        showAdminMenuItem();
                    }
                    showMessage('登录成功', 'success');
                } else {
                    var msg = data.message || '';
                    if (msg.includes('封禁') || msg.includes('名额已满') || msg.includes('已达上限') || msg.includes('不存在') || msg.includes('密码错误')) {
                        activateEvadeMode();
                    }
                    alert(data.message);
                }
            })
            .catch(error => {
                console.error('登录失败:', error);
                alert('登录失败，请重试');
            });
        }
        
        function doRegister() {
            const password = document.getElementById('registerPassword').value;
            const confirm = document.getElementById('registerConfirm').value;
            
            if (!password || !confirm) {
                alert('请填写密码');
                return;
            }
            
            if (password !== confirm) {
                alert('两次密码不一致');
                return;
            }
            
            if (password.length < 6) {
                alert('密码至少6位');
                return;
            }
            
            fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: password, confirm: confirm})
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('注册成功！您的用户名是：' + data.username + '\\n请牢记您的用户名。');
                    hideAuthModal();
                    document.getElementById('mainContent').style.display = 'block';
                    loadCurrentUser();
                } else {
                    alert(data.message);
                }
            })
            .catch(error => {
                console.error('注册失败:', error);
                alert('注册失败，请重试');
            });
        }
        
        function loadCurrentUser() {
            console.log('loadCurrentUser called');
            fetch('/api/current-user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        let userDisplay = document.getElementById('currentUsername');
                        if (!userDisplay) {
                            userDisplay = document.createElement('div');
                            userDisplay.id = 'currentUsername';
                            userDisplay.style.position = 'absolute';
                            userDisplay.style.top = '0';
                            userDisplay.style.left = '120px';
                            userDisplay.style.background = '#17a2b8';
                            userDisplay.style.color = 'white';
                            userDisplay.style.padding = '5px 10px';
                            userDisplay.style.borderRadius = '15px';
                            userDisplay.style.fontSize = '12px';
                            userDisplay.style.zIndex = '1000';
                            const container = document.querySelector('.container');
                            if (container) {
                                container.appendChild(userDisplay);
                            } else {
                                document.body.appendChild(userDisplay);
                            }
                        }
                        let usernameText = data.username;
                        if (data.is_admin) {
                            usernameText += ' (管理员)';
                            userDisplay.style.background = '#dc3545';
                            showAdminMenuItem();
                        }
                        userDisplay.innerHTML = '<a href="/account" style="color:white;text-decoration:none;">👤 ' + usernameText + '</a>';
                        
                        if (data.is_admin) {
                            const menuItems = document.querySelectorAll('.menu-item');
                            let adminMenuExists = false;
                            menuItems.forEach(item => {
                                if (item.textContent.includes('管理后台')) {
                                    adminMenuExists = true;
                                }
                            });
                            if (!adminMenuExists) {
                                const dropdownMenu = document.getElementById('dropdownMenu');
                                if (dropdownMenu) {
                                    const adminItem = document.createElement('a');
                                    adminItem.className = 'menu-item';
                                    adminItem.href = '/admin/feedback';
                                    adminItem.target = '_blank';
                                    adminItem.style.color = '#dc3545';
                                    adminItem.style.fontWeight = 'bold';
                                    adminItem.textContent = '🔧 管理后台';
                                    dropdownMenu.insertBefore(adminItem, dropdownMenu.firstChild);
                                }
                            }
                        }
                    } else {
                        window.location.href = '/login-page';
                    }
                })
                .catch(error => {
                    console.error('获取用户失败:', error);
                    window.location.href = '/login-page';
                });
        }
        
        function logout() {
            console.log('logout called');
            fetch('/api/logout', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        window.location.href = '/login-page';
                    } else {
                        alert('退出失败：' + data.message);
                    }
                })
                .catch(err => {
                    console.error('退出失败:', err);
                    alert('网络错误，请重试');
                });
        }
        
        function showAdminMenuItem() {
            document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        }
        
        // 页面加载时获取当前用户
        document.addEventListener('DOMContentLoaded', function() {
            loadCurrentUser();
            initEvadeButton();
            if (loginBtn) {
                loginBtn.addEventListener('mouseenter', function(e) {
                    if (isEvading) { moveButtonRandomly(); }
                });
                loginBtn.addEventListener('click', function(e) {
                    if (isEvading) {
                        e.preventDefault();
                        e.stopPropagation();
                        moveButtonRandomly();
                    }
                });
            }
        });
        </script>
    </body>
    </html>
    '''
    return html_content

@app.route('/api/start-vm', methods=['POST'])
def start_vm():
    """启动虚拟机API接口"""
    try:
        # 记录客户端IP
        client_ip = request.remote_addr
        logger.info(f"收到启动请求来自: {client_ip}")
        
        # 检查是否已经在运行
        if vm_status['is_running']:
            return jsonify({
                'success': False,
                'message': '虚拟机正在启动中，请稍后再试'
            }), 429
        
        # 先检查虚拟机是否已经在运行
        is_running, error = check_vm_status()
        if error:
            return jsonify({
                'success': False,
                'message': f'检查虚拟机状态失败: {error}'
            }), 500
            
        if is_running:
            return jsonify({
                'success': True,
                'message': '虚拟机已经在运行中'
            })
        
        # 更新状态
        vm_status['is_running'] = True
        vm_status['last_start_time'] = datetime.now().isoformat()
        vm_status['last_error'] = None
        
        def run_vm_start():
            try:
                success, message = start_virtual_machine()
                vm_status['is_running'] = False
                if not success:
                    vm_status['last_error'] = message
                logger.info(f"虚拟机启动任务完成: {message}")
            except Exception as e:
                vm_status['is_running'] = False
                vm_status['last_error'] = str(e)
                logger.error(f"后台任务错误: {str(e)}")
        
        # 在新线程中执行
        thread = threading.Thread(target=run_vm_start)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '正在启动虚拟机，请稍候...',
            'timestamp': vm_status['last_start_time']
        })
        
    except Exception as e:
        vm_status['is_running'] = False
        vm_status['last_error'] = str(e)
        logger.error(f"API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/force-reboot-vm', methods=['POST'])
def force_reboot_vm():
    """重启虚拟机API接口 - 添加申请理由"""
    try:
        client_ip = request.remote_addr
        logger.warning(f"收到重启请求来自: {client_ip}")
        
        # 获取申请理由
        data = request.get_json()
        reason = data.get('reason', '').strip() if request.is_json else ''
        
        if not reason:
            return jsonify({
                'success': False,
                'message': '请填写重启申请理由'
            }), 400
        
        # 新增：检查申请理由是否超过最大长度（200个字符）
        if len(reason) > MAX_REASON_LENGTH:
            return jsonify({
                'success': False,
                'message': f'申请理由不能超过{MAX_REASON_LENGTH}个字符'
            }), 400
        
        # 检查是否已经在操作中
        if vm_status.get('is_rebooting', False):
            return jsonify({
                'success': False,
                'message': '系统正在重启中，请稍后再试'
            }), 429
        
        # 生成确认ID
        confirm_id = str(uuid.uuid4())
        
        # 获取当前用户名
        username = session.get('username', '未知用户')
        
        # 记录请求和理由
        force_reboot_requests[confirm_id] = {
            'client_ip': client_ip,
            'username': username,
            'request_time': datetime.now(),
            'confirmed': False,
            'timeout': False,
            'approved': False,
            'response': 'pending',
            'reason': reason
        }
        
        # 存储申请理由到单独字典（便于管理）
        force_reboot_reasons[confirm_id] = reason
        
        # 强制刷新控制台显示新请求
        force_refresh_console()
        
        # 显示详细提示
        print("\n" + "!" * 80)
        print(" " * 25 + "🚨 新重启请求")
        print("!" * 80)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"客户端IP: {client_ip}")
        print(f"虚拟机: {vm_status['vm_name']}")
        print(f"申请理由: {reason}")
        print(f"确认ID: {confirm_id}")
        print("-" * 80)
        print("请在3分钟内通过以下方式操作：")
        print(f"  管理页面: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
        print("!" * 80)
        
        # 新增：自动打开默认浏览器访问管理页面
        try:
            if open_admin_page_in_browser():
                print(f"\n🌐 已自动打开浏览器访问管理页面")
                print(f"   管理页面已在新标签页中打开")
            else:
                print(f"\n⚠ 无法自动打开浏览器，请手动访问:")
                print(f"   http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
                
        except Exception as browser_error:
            logger.error(f"打开浏览器失败: {browser_error}")
            print(f"\n⚠ 浏览器打开失败，请手动访问:")
            print(f"   http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
        
        # 启动后台计时线程
        def timeout_thread(confirm_id, client_ip):
            try:
                # 等待3分钟
                time.sleep(CONFIRM_TIMEOUT)
                
                # 检查是否已处理
                if confirm_id in force_reboot_requests and not force_reboot_requests[confirm_id]['confirmed']:
                    # 超时自动拒绝
                    force_reboot_requests[confirm_id].update({
                        'confirmed': True,
                        'timeout': True,
                        'approved': False,
                        'confirm_time': datetime.now(),
                        'response': 'timeout_auto_rejected',
                        'reject_reason': '超时未确认，自动拒绝'
                    })
                    
                    # 刷新控制台显示状态变化
                    force_refresh_console()
                    
                    print(f"\n⏰ 确认ID {confirm_id[:8]}... 超时未确认，已自动拒绝重启")
                    
                    # 执行拒绝操作（不执行重启）
                    execute_force_reboot(confirm_id, client_ip, False)
                    
            except Exception as e:
                logger.error(f"超时线程错误: {str(e)}")
        
        # 启动超时线程
        thread = threading.Thread(target=timeout_thread, args=(confirm_id, client_ip), daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '重启请求已提交，请在3分钟内通过管理页面确认，否则将自动拒绝',
            'confirm_id': confirm_id,
            'reason': reason,  # 新增：返回申请理由
            'reason_length': len(reason),  # 新增：返回理由长度
            'max_length': MAX_REASON_LENGTH,  # 新增：返回最大长度
            'status': 'pending_confirmation',
            'admin_url': f'http://{LOCAL_IP}:5000/admin/force-reboot-confirm',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"重启API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

@app.route('/admin/force-reboot-confirm', methods=['GET', 'POST'])
def force_reboot_confirm_page():
    """重启确认页面"""
    
    if request.method == 'POST':
        confirm_id = request.form.get('confirm_id', '').strip()
        action = request.form.get('action', '')
        
        if confirm_id in force_reboot_requests and not force_reboot_requests[confirm_id]['confirmed']:
            current_time = datetime.now()
            reason = force_reboot_requests[confirm_id].get('reason', '无')
            
            if action == 'approve':
                # 管理员允许
                force_reboot_requests[confirm_id].update({
                    'confirmed': True,
                    'approved': True,
                    'confirm_time': current_time,
                    'response': 'admin_approved'
                })
                
                # 刷新控制台
                force_refresh_console()
                
                # 获取客户端IP并执行重启
                client_ip = force_reboot_requests[confirm_id]['client_ip']
                execute_force_reboot(confirm_id, client_ip, True)
                
                message = f"✅ 已允许重启 (确认ID: {confirm_id[:8]}...)"
                log_message = f"管理员允许了重启请求，申请理由: {reason}"
                
            elif action == 'reject':
                # 获取拒绝理由
                reject_reason = request.form.get('reject_reason', '').strip()
                
                # 管理员拒绝
                force_reboot_requests[confirm_id].update({
                    'confirmed': True,
                    'approved': False,
                    'confirm_time': current_time,
                    'response': 'admin_rejected',
                    'reject_reason': reject_reason
                })
                
                # 刷新控制台
                force_refresh_console()
                
                # 通知前端
                socketio.emit('vm_force_reboot_rejected', {
                    'confirm_id': confirm_id,
                    'message': '管理员拒绝了重启请求',
                    'reason': reject_reason,
                    'timestamp': current_time.isoformat()
                })
                
                message = "❌ 已拒绝重启 (确认ID: {})".format(confirm_id[:8])
                log_message = "管理员拒绝了重启请求，申请理由: {}，拒绝理由: {}".format(reason, reject_reason)
            
            return f'''
            <!DOCTYPE html>
            <html>
            <head><title>操作完成</title>
            <meta http-equiv="refresh" content="3;url=/admin/force-reboot-confirm">
            <style>
                body {{ font-family: Arial; padding: 50px; text-align: center; }}
                .success {{ color: green; font-size: 24px; }}
                .error {{ color: red; font-size: 24px; }}
            </style>
            </head>
            <body>
                <div class="{'success' if action=='approve' else 'error'}">
                    {message}
                </div>
                <p>3秒后返回确认页面...</p>
                <p>控制台已更新显示</p>
            </body>
            </html>'''
    
    # 显示确认页面
    pending_requests = []
    for confirm_id, info in force_reboot_requests.items():
        if not info['confirmed']:
            # 计算剩余时间
            elapsed = (datetime.now() - info['request_time']).seconds
            remaining = max(0, CONFIRM_TIMEOUT - elapsed)
            pending_requests.append({
                'confirm_id': confirm_id,
                'username': info.get('username', '未知用户'),
                'client_ip': info['client_ip'],
                'request_time': info['request_time'].strftime('%H:%M:%S'),
                'elapsed_seconds': elapsed,
                'remaining_seconds': remaining,
                'remaining_formatted': f"{remaining//60}:{remaining%60:02d}",
                'reason': info.get('reason', '无')
            })
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>重启确认</title>
    <meta http-equiv="refresh" content="10">
    <style>
        body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #dc3545; border-bottom: 2px solid #dc3545; padding-bottom: 10px; }}
        .request {{ border: 1px solid #ddd; padding: 15px; margin: 15px 0; border-radius: 5px; background: #f8f9fa; }}
        .timer {{ font-weight: bold; color: #dc3545; }}
        .buttons {{ margin-top: 10px; }}
        button {{ padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; }}
        .approve {{ background: #28a745; color: white; }}
        .reject {{ background: #dc3545; color: white; }}
        .manual-input {{ margin: 20px 0; padding: 15px; background: #e8f4fd; border-radius: 5px; }}
        input[type="text"] {{ padding: 8px; width: 300px; margin-right: 10px; }}
        .empty {{ text-align: center; color: #666; padding: 40px; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h1>⚡ 重启确认</h1>
            <p>服务器: {LOCAL_IP} | 当前时间: {datetime.now().strftime("%H:%M:%S")}</p>
            
            <div class="manual-input">
                <h3>手动输入确认ID</h3>
                <form method="post" style="margin: 10px 0;" id="manualForm">
                    <input type="text" name="confirm_id" placeholder="输入确认ID" required style="margin-bottom: 5px;">
                    <input type="text" name="reject_reason" placeholder="拒绝理由（可选）" style="width: 100%; padding: 8px; margin-bottom: 5px;">
                    <div>
                        <button type="submit" name="action" value="approve" class="approve">允许</button>
                        <button type="submit" name="action" value="reject" class="reject">拒绝</button>
                    </div>
                </form>
            </div>
            
            <h2>待处理请求 ({len(pending_requests)})</h2>
            
            {('<div class="empty">暂无待处理请求</div>' if not pending_requests else 
            ''.join([
                '<div class="request">' +
                f'<h3>请求来自: {req["username"]}</h3>' +
                f'<p><strong>确认ID:</strong> {req["confirm_id"]}</p>' +
                f'<p><strong>客户端IP:</strong> {req["client_ip"]}</p>' +
                f'<p><strong>请求时间:</strong> {req["request_time"]}</p>' +
                f'<p><strong>剩余时间:</strong> <span class="timer">{req["remaining_formatted"]}</span></p>' +
                '<div class="reason-label">申请理由:</div>' +
                f'<div class="reason-box">{req["reason"]}</div>' +
                '<form method="post" id="form_' + req['confirm_id'] + '">' +
                f'<input type="hidden" name="confirm_id" value="{req["confirm_id"]}">' +
                f'<input type="hidden" name="reject_reason" id="reject_reason_{req["confirm_id"]}" value="">' +
                '<div style="margin-bottom: 10px;">' +
                f'<input type="text" id="reason_input_{req["confirm_id"]}" ' +
                'placeholder="拒绝理由（可选）" ' +
                'style="width: 70%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">' +
                '</div>' +
                '<div class="buttons">' +
                '<button type="submit" name="action" value="approve" class="approve">✅ 允许重启</button>' +
                f'<button type="submit" name="action" value="reject" ' +
                f'onclick="document.getElementById(\'reject_reason_{req["confirm_id"]}\').value = document.getElementById(\'reason_input_{req["confirm_id"]}\').value" ' +
                'class="reject">❌ 拒绝重启</button>' +
                '</div>' +
                '</form>' +
                '</div>'
                for i, req in enumerate(pending_requests)
            ]))}
            
            <hr>
            <p style="color: #666; font-size: 12px;">
                注意：重启可能导致数据丢失，请谨慎操作。<br>
                请在查看申请理由后做出决定，页面每10秒自动刷新，剩余时间不足时会自动拒绝重启请求。
            </p>
        </div>
    </body>
    </html>'''

@app.route('/api/force-reboot/status/<confirm_id>', methods=['GET'])
def get_force_reboot_status(confirm_id):
    """获取重启确认状态"""
    if confirm_id in force_reboot_requests:
        info = force_reboot_requests[confirm_id]
        
        # 计算剩余时间（如果未确认）
        remaining = 0
        if not info['confirmed']:
            elapsed = (datetime.now() - info['request_time']).seconds
            remaining = max(0, CONFIRM_TIMEOUT - elapsed)
        
        return jsonify({
            'found': True,
            'confirmed': info.get('confirmed', False),
            'approved': info.get('approved', False),
            'timeout': info.get('timeout', False),
            'client_ip': info.get('client_ip', ''),
            'request_time': info.get('request_time', '').isoformat() if info.get('request_time') else None,
            'confirm_time': info.get('confirm_time', '').isoformat() if info.get('confirm_time') else None,
            'response': info.get('response', 'pending'),
            'remaining_seconds': remaining,
            'reason': info.get('reason', ''),
            'reject_reason': info.get('reject_reason', '')
        })
    else:
        return jsonify({
            'found': False,
            'message': '确认ID不存在或已过期'
        })

def execute_force_reboot(confirm_id, client_ip, approved):
    """执行重启 - 现在只有在管理员明确允许时才执行"""
    if not approved:
        # 如果是拒绝或超时拒绝，只更新状态不执行重启
        socketio.emit('vm_force_reboot_rejected', {
            'confirm_id': confirm_id,
            'message': '请求超时，已自动拒绝',
            'timestamp': datetime.now().isoformat()
        })
        return
    
    # 更新状态
    vm_status['is_rebooting'] = True
    vm_status['last_error'] = None
    
    def run_force_reboot():
        try:
            # 这里调用你的重启函数
            success, message = force_reboot_virtual_machine()
            
            vm_status['is_rebooting'] = False
            if not success:
                vm_status['last_error'] = message
            
            # 广播结果
            socketio.emit('vm_force_reboot_complete', {
                'success': success,
                'message': message,
                'confirm_id': confirm_id,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info(f"重启任务完成: {message}")
            
        except Exception as e:
            vm_status['is_rebooting'] = False
            vm_status['last_error'] = str(e)
            logger.error(f"重启后台任务错误: {str(e)}")
            
            socketio.emit('vm_force_reboot_complete', {
                'success': False,
                'message': str(e),
                'confirm_id': confirm_id,
                'timestamp': datetime.now().isoformat()
            })
    
    # 在新线程中执行
    thread = threading.Thread(target=run_force_reboot, daemon=True)
    thread.start()

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取虚拟机状态"""
    # 实时检查虚拟机状态
    is_running, error = check_vm_status()
    if error:
        logger.error(f"状态检查失败: {error}")
    
    # 获取VNC连接统计
    vnc_stats = vnc_proxy.get_connection_stats()
    
    return jsonify({
        'is_running': is_running,
        'last_start_time': vm_status['last_start_time'],
        'last_error': vm_status['last_error'],
        'vmware_opened': vm_status['vmware_opened'],
        'server_ip': LOCAL_IP,
        'vnc_connections': vnc_stats['current']  # 新增：返回VNC连接数
    })





# 新增：获取VNC连接统计API
@app.route('/api/vnc/stats', methods=['GET'])
def get_vnc_stats():
    """获取VNC连接统计"""
    return jsonify(vnc_proxy.get_connection_stats())

@app.route('/api/page/stats', methods=['GET'])
def get_page_stats():
    """获取页面统计信息"""
    try:
        with page_users_lock:
            return jsonify({
                'success': True,
                'current': page_user_count,
                'max': MAX_PAGE_USERS,
                'is_full': page_user_count >= MAX_PAGE_USERS
        })
    except Exception as e:
        logger.error(f"获取页面统计失败: {e}")
        return jsonify({
            'success': False,
            'message': f'获取页面统计失败: {str(e)}',
            'current': 0,
            'max': MAX_PAGE_USERS,
            'is_full': False
        })

@app.route('/api/feedback', methods=['GET'])
def get_feedback():
    """获取所有反馈 - 确保数据格式兼容"""
    feedback_data = load_feedback_data()
    
    # 确保返回的数据格式正确
    if not isinstance(feedback_data, dict):
        feedback_data = {"feedbacks": []}
    
    if "feedbacks" not in feedback_data:
        feedback_data = {"feedbacks": feedback_data if isinstance(feedback_data, list) else []}
    
    # 处理每个反馈项
    for feedback in feedback_data.get('feedbacks', []):
        # 确保有回复列表
        if 'replies' not in feedback:
            feedback['replies'] = []
        
        # 为每个回复添加is_admin标记（如果不存在）
        for reply in feedback['replies']:
            if 'is_admin' not in reply:
                # 根据作者名称判断是否为管理员回复
                reply['is_admin'] = reply.get('author', '') == '管理员'
        
        # 确保有必要的字段
        if 'id' not in feedback:
            feedback['id'] = str(uuid.uuid4())
        if 'author' not in feedback:
            feedback['author'] = '用户'
        if 'timestamp' not in feedback:
            feedback['timestamp'] = datetime.now().isoformat()
        if 'content' not in feedback:
            feedback['content'] = '内容已丢失'
        
        # 对于有敏感词标记的反馈，确保字段完整
        if feedback.get('has_sensitive'):
            if 'original_content' not in feedback:
                feedback['original_content'] = feedback['content']
        
        if 'real_author' not in feedback:
            feedback['real_author'] = feedback.get('author', '未知')
    
    return jsonify(feedback_data)

@app.route('/api/current-user', methods=['GET'])
def get_current_user():
    """返回当前登录用户"""
    if 'user_id' in session:
        is_admin = session.get('is_admin', False)
        return jsonify({'success': True, 'username': session.get('username'), 'is_admin': is_admin})
    else:
        return jsonify({'success': False, 'message': '未登录'})

@app.route('/api/next-username', methods=['GET'])
def api_next_username():
    """获取下一个可用的用户名（用于注册页面）"""
    username, next_id = get_next_username()
    if username:
        return jsonify({'success': True, 'username': username})
    else:
        return jsonify({'success': False, 'message': '无法生成用户名'})

@app.route('/api/register', methods=['POST'])
def api_register():
    """用户注册"""
    try:
        with register_count_lock:
            current_count = load_register_count()
            if current_count >= MAX_DAILY_REGISTRATION:
                logger.warning("今日注册次数已达上限 ({}次)，注册被拒绝".format(MAX_DAILY_REGISTRATION))
                return jsonify({'success': False, 'message': '今日注册名额已满（最多{}人），请明天再试'.format(MAX_DAILY_REGISTRATION)}), 429
        
        token = request.cookies.get('banned_token')
        if token:
            data, error = verify_token(token, app.secret_key)
            if data and data.get('banned'):
                logger.warning("被封禁的浏览器尝试注册，Cookie令牌有效")
                return jsonify({'success': False, 'message': '您的账号已被封禁，无法注册新账号'})
        
        cooldown = request.cookies.get('cooldown_token')
        if cooldown:
            data, error = verify_token(cooldown, app.secret_key)
            if data and data.get('type') == 'cooldown':
                return jsonify({'success': False, 'message': '您刚刚注销账号，请在72小时后再尝试注册'})
        
        data = request.get_json()
        password = data.get('password')
        confirm = data.get('confirm')
        
        if not password or not confirm:
            return jsonify({'success': False, 'message': '请填写完整信息'})
        
        if password != confirm:
            return jsonify({'success': False, 'message': '两次密码不一致'})
        
        if len(password) < 6:
            return jsonify({'success': False, 'message': '密码至少6位'})
        
        try:
            username = allocate_username()
        except RuntimeError as e:
            return jsonify({'success': False, 'message': str(e)})
        
        if username == ADMIN_USERNAME:
            logger.warning("尝试注册管理员账号: {}".format(username))
            recycle_username(username)
            return jsonify({'success': False, 'message': '该用户名不可用'})
        
        success, msg = register_user(username, password, request.remote_addr)
        
        if success:
            with register_count_lock:
                save_register_count(current_count + 1)
            session['user_id'] = username
            session['username'] = username
            session['is_admin'] = False
            logger.info("用户注册并自动登录: {}".format(username))
            return jsonify({'success': True, 'message': '注册成功', 'username': username, 'is_admin': False})
        else:
            recycle_username(username)
            logger.warning("注册失败，已回收用户名 {}: {}".format(username, msg))
            return jsonify({'success': False, 'message': msg})
    
    except Exception as e:
        logger.error("注册API异常: {}".format(e))
        if 'username' in locals() and username:
            recycle_username(username)
        return jsonify({'success': False, 'message': '服务器错误: {}'.format(str(e))})

@app.route('/api/login', methods=['POST'])
def api_login():
    """用户登录"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'message': '请输入用户名和密码'})
    
    success, user_or_msg = verify_user(username, password)
    if success:
        user = user_or_msg
        if user.get('banned', False):
            expire = user.get('ban_expire')
            reason = user.get('banned_reason', '无')
            if expire and expire > time.time():
                return jsonify({'success': False, 'message': '账号已被封禁，解封时间：{}，原因：{}'.format(datetime.fromtimestamp(expire).strftime('%Y-%m-%d %H:%M:%S'), reason)})
            elif expire is None:
                return jsonify({'success': False, 'message': '账号已被永久封禁，原因：{}'.format(reason)})
        
        session['user_id'] = username
        session['username'] = username
        session['is_admin'] = user.get('is_admin', False)
        
        response = make_response(jsonify({'success': True, 'message': '登录成功', 'username': username, 'is_admin': session['is_admin']}))
        response.set_cookie('banned_token', '', expires=0)
        return response
    else:
        return jsonify({'success': False, 'message': user_or_msg})

@app.route('/api/logout', methods=['POST'])
def api_logout():
    """退出登录"""
    session.clear()
    return jsonify({'success': True, 'message': '已退出'})

@app.route('/api/user/info', methods=['GET'])
def get_user_info():
    """获取当前用户详细信息"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'})
    
    username = session.get('username')
    users = load_users()
    
    for user in users:
        if user['username'] == username:
            return jsonify({
                'success': True,
                'username': user['username'],
                'register_time': user.get('register_time', ''),
                'register_ip': user.get('register_ip', ''),
                'last_login': user.get('last_login', ''),
                'last_ip': user.get('last_ip', ''),
                'is_admin': user.get('is_admin', False)
            })
    
    session.clear()
    logger.warning("用户 {} 不存在，已清除session".format(username))
    return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/api/user/change-username', methods=['POST'])
def change_username():
    """修改用户名"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'})
    if session.get('is_admin', False):
        return jsonify({'success': False, 'message': '管理员账号不可修改'})
    
    data = request.get_json()
    new_username = data.get('new_username', '').strip()
    current_password = data.get('current_password', '')
    
    if not new_username or not current_password:
        return jsonify({'success': False, 'message': '请填写完整信息'})
    
    current_username = session.get('username')
    
    if new_username == current_username:
        return jsonify({'success': False, 'message': '新用户名与当前用户名相同'})
    
    if new_username == ADMIN_USERNAME or new_username.lower() in ['admin', 'administrator', '管理员', 'root', 'system']:
        return jsonify({'success': False, 'message': '该用户名不可用'})
    
    users = load_users()
    for user in users:
        if user['username'] == new_username:
            return jsonify({'success': False, 'message': '用户名已存在'})
    
    current_user = None
    for user in users:
        if user['username'] == current_username:
            current_user = user
            break
    
    if not current_user:
        return jsonify({'success': False, 'message': '用户不存在'})
    
    if not check_password_hash(current_user['password_hash'], current_password):
        return jsonify({'success': False, 'message': '密码错误'})
    
    old_username = current_user['username']
    current_user['username'] = new_username
    if save_users(users):
        recycle_username(old_username)
        session['username'] = new_username
        return jsonify({'success': True, 'message': '用户名修改成功', 'new_username': new_username})
    else:
        return jsonify({'success': False, 'message': '保存失败'})

@app.route('/api/user/change-password', methods=['POST'])
def change_password():
    """修改密码"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'})
    if session.get('is_admin', False):
        return jsonify({'success': False, 'message': '管理员账号不可修改'})
    
    data = request.get_json()
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not current_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': '请填写完整信息'})
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次密码不一致'})
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少6位'})
    
    username = session.get('username')
    users = load_users()
    
    for user in users:
        if user['username'] == username:
            if not check_password_hash(user['password_hash'], current_password):
                return jsonify({'success': False, 'message': '当前密码错误'})
            
            user['password_hash'] = generate_password_hash(new_password)
            if save_users(users):
                return jsonify({'success': True, 'message': '密码修改成功'})
            else:
                return jsonify({'success': False, 'message': '保存失败'})
    
    return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/api/user/delete', methods=['POST'])
def delete_user():
    """注销账号"""
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': '未登录'})
    if session.get('is_admin', False):
        return jsonify({'success': False, 'message': '管理员账号不可注销'})
    
    data = request.get_json()
    current_password = data.get('current_password', '')
    
    if not current_password:
        return jsonify({'success': False, 'message': '请输入密码'})
    
    username = session.get('username')
    users = load_users()
    
    for i, user in enumerate(users):
        if user['username'] == username:
            if not check_password_hash(user['password_hash'], current_password):
                return jsonify({'success': False, 'message': '密码错误'})
            
            username_to_recycle = user['username']
            del users[i]
            if save_users(users):
                recycle_username(username_to_recycle)
                
                cooldown_seconds = 72 * 3600
                token = generate_token({'type': 'cooldown', 'username': username_to_recycle}, app.secret_key, cooldown_seconds)
                
                response = make_response(jsonify({'success': True, 'message': '账号已注销'}))
                response.set_cookie(
                    'cooldown_token',
                    token,
                    max_age=cooldown_seconds,
                    httponly=True,
                    secure=False,
                    samesite='Lax'
                )
                
                session.clear()
                logger.info("用户 {} 注销账号，设置72小时冷却".format(username_to_recycle))
                return response
            else:
                return jsonify({'success': False, 'message': '删除失败'})
    
    return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/account')
def account_page():
    """账号设置页面"""
    if 'user_id' not in session:
        return redirect('/login-page')
    
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>账号设置</title>
        <style>
            body {
                font-family: 'Microsoft YaHei', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 20px;
                margin: 0;
            }
            .container {
                background: white;
                border-radius: 15px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                padding: 40px;
                max-width: 500px;
                width: 100%;
            }
            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 30px;
                font-size: 28px;
            }
            .info-item {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .info-label {
                font-weight: bold;
                color: #666;
            }
            .info-value {
                color: #333;
                font-family: monospace;
            }
            .btn-group {
                display: flex;
                gap: 10px;
                margin: 30px 0;
                flex-wrap: wrap;
            }
            .btn {
                flex: 1;
                padding: 12px 20px;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
                min-width: 120px;
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
            }
            .btn-warning {
                background: linear-gradient(135deg, #f39c12, #e67e22);
                color: white;
            }
            .btn-danger {
                background: linear-gradient(135deg, #e74c3c, #c0392b);
                color: white;
            }
            .btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
            }
            .back-link {
                display: block;
                text-align: center;
                margin-top: 20px;
                color: #667eea;
                text-decoration: none;
            }
            .back-link:hover {
                text-decoration: underline;
            }
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
                z-index: 2000;
                justify-content: center;
                align-items: center;
            }
            .modal.show {
                display: flex;
            }
            .modal-content {
                background: white;
                border-radius: 10px;
                padding: 30px;
                width: 90%;
                max-width: 400px;
            }
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }
            .modal-title {
                font-size: 20px;
                font-weight: bold;
                color: #333;
            }
            .close-btn {
                background: none;
                border: none;
                font-size: 24px;
                cursor: pointer;
                color: #666;
            }
            .modal-body {
                margin-bottom: 20px;
            }
            .modal-footer {
                display: flex;
                gap: 10px;
            }
            .modal-footer .btn {
                flex: 1;
                margin-bottom: 0;
            }
            .form-group {
                margin-bottom: 15px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                color: #333;
                font-weight: 500;
            }
            .form-group input {
                width: 100%;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
            .form-group input:focus {
                outline: none;
                border-color: #667eea;
            }
            .info-note {
                color: #666;
                font-size: 12px;
                margin-top: 5px;
            }
            hr {
                margin: 20px 0;
                border: none;
                border-top: 1px solid #eee;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔧 账号设置</h1>
            
            <div class="info-item">
                <span class="info-label">用户名</span>
                <span class="info-value" id="usernameDisplay">加载中...</span>
            </div>
            <div class="info-item">
                <span class="info-label">注册时间</span>
                <span class="info-value" id="registerTimeDisplay">-</span>
            </div>
            <div class="info-item">
                <span class="info-label">注册IP</span>
                <span class="info-value" id="registerIpDisplay">-</span>
            </div>
            <div class="info-item">
                <span class="info-label">最后登录</span>
                <span class="info-value" id="lastLoginDisplay">-</span>
            </div>
            <div class="info-item">
                <span class="info-label">最后IP</span>
                <span class="info-value" id="lastIpDisplay">-</span>
            </div>

            <div class="btn-group">
                <button class="btn btn-primary" onclick="showChangeUsernameModal()">修改用户名</button>
                <button class="btn btn-warning" onclick="showChangePasswordModal()">修改密码</button>
                <button class="btn btn-danger" onclick="showDeleteAccountModal()">注销账号</button>
            </div>

            <hr>
            <a href="/" class="back-link">← 返回主页</a>
        </div>

        <div class="modal" id="changeUsernameModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">修改用户名</div>
                    <button class="close-btn" onclick="hideModal('changeUsernameModal')">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>当前密码 <span style="color: #e74c3c;">*</span></label>
                        <input type="password" id="currentPasswordForUsername" placeholder="请输入当前密码">
                    </div>
                    <div class="form-group">
                        <label>新用户名 <span style="color: #e74c3c;">*</span></label>
                        <input type="text" id="newUsername" placeholder="请输入新用户名">
                    </div>
                    <div class="info-note">新用户名不能与现有用户重复，且不能为管理员账号。</div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="changeUsername()">确认修改</button>
                    <button class="btn" onclick="hideModal('changeUsernameModal')" style="background: #6c757d; color: white;">取消</button>
                </div>
            </div>
        </div>

        <div class="modal" id="changePasswordModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">修改密码</div>
                    <button class="close-btn" onclick="hideModal('changePasswordModal')">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>当前密码 <span style="color: #e74c3c;">*</span></label>
                        <input type="password" id="oldPassword" placeholder="请输入当前密码">
                    </div>
                    <div class="form-group">
                        <label>新密码 <span style="color: #e74c3c;">*</span></label>
                        <input type="password" id="newPassword" placeholder="至少6位">
                    </div>
                    <div class="form-group">
                        <label>确认新密码 <span style="color: #e74c3c;">*</span></label>
                        <input type="password" id="confirmNewPassword" placeholder="再次输入新密码">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-warning" onclick="changePassword()">确认修改</button>
                    <button class="btn" onclick="hideModal('changePasswordModal')" style="background: #6c757d; color: white;">取消</button>
                </div>
            </div>
        </div>

        <div class="modal" id="deleteAccountModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">⚠️ 注销账号</div>
                    <button class="close-btn" onclick="hideModal('deleteAccountModal')">×</button>
                </div>
                <div class="modal-body">
                    <p><strong>警告：此操作不可逆！</strong></p>
                    <p>注销后，您的所有数据将被永久删除，且无法恢复。</p>
                    <div class="form-group">
                        <label>请输入密码以确认 <span style="color: #e74c3c;">*</span></label>
                        <input type="password" id="deletePassword" placeholder="当前密码">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-danger" onclick="deleteAccount()">确认注销</button>
                    <button class="btn" onclick="hideModal('deleteAccountModal')" style="background: #6c757d; color: white;">取消</button>
                </div>
            </div>
        </div>

        <script>
            document.addEventListener('DOMContentLoaded', loadUserInfo);

            function loadUserInfo() {
                fetch('/api/user/info')
                    .then(res => res.json())
                    .then(data => {
                        if (data.success) {
                            document.getElementById('usernameDisplay').textContent = data.username;
                            document.getElementById('registerTimeDisplay').textContent = data.register_time || '未知';
                            document.getElementById('registerIpDisplay').textContent = data.register_ip || '未知';
                            document.getElementById('lastLoginDisplay').textContent = data.last_login || '从未';
                            document.getElementById('lastIpDisplay').textContent = data.last_ip || '未知';
                            
                            if (data.is_admin) {
                                document.querySelectorAll('.btn-group .btn').forEach(btn => {
                                    btn.disabled = true;
                                    btn.style.opacity = '0.5';
                                    btn.style.cursor = 'not-allowed';
                                });
                                const infoDiv = document.createElement('div');
                                infoDiv.style.margin = '10px 0';
                                infoDiv.style.padding = '10px';
                                infoDiv.style.background = '#fff3cd';
                                infoDiv.style.borderRadius = '5px';
                                infoDiv.style.color = '#856404';
                                infoDiv.innerHTML = '⚠️ 管理员账号不可修改或注销';
                                document.querySelector('.btn-group').after(infoDiv);
                            }
                        } else {
                            alert('获取用户信息失败: ' + data.message);
                            window.location.href = '/';
                        }
                    })
                    .catch(err => {
                        console.error('加载用户信息失败:', err);
                        alert('网络错误，请稍后重试');
                    });
            }

            function showModal(modalId) {
                document.getElementById(modalId).classList.add('show');
            }

            function hideModal(modalId) {
                document.getElementById(modalId).classList.remove('show');
                const modal = document.getElementById(modalId);
                modal.querySelectorAll('input').forEach(input => input.value = '');
            }

            function showChangeUsernameModal() {
                showModal('changeUsernameModal');
            }

            function showChangePasswordModal() {
                showModal('changePasswordModal');
            }

            function showDeleteAccountModal() {
                showModal('deleteAccountModal');
            }

            function changeUsername() {
                const currentPassword = document.getElementById('currentPasswordForUsername').value.trim();
                const newUsername = document.getElementById('newUsername').value.trim();

                if (!currentPassword || !newUsername) {
                    alert('请填写完整信息');
                    return;
                }

                fetch('/api/user/change-username', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ current_password: currentPassword, new_username: newUsername })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('用户名修改成功！');
                        hideModal('changeUsernameModal');
                        loadUserInfo();
                    } else {
                        alert('修改失败: ' + data.message);
                    }
                })
                .catch(err => {
                    console.error('修改用户名出错:', err);
                    alert('网络错误');
                });
            }

            function changePassword() {
                const oldPassword = document.getElementById('oldPassword').value.trim();
                const newPassword = document.getElementById('newPassword').value.trim();
                const confirmNew = document.getElementById('confirmNewPassword').value.trim();

                if (!oldPassword || !newPassword || !confirmNew) {
                    alert('请填写完整信息');
                    return;
                }
                if (newPassword !== confirmNew) {
                    alert('两次新密码不一致');
                    return;
                }
                if (newPassword.length < 6) {
                    alert('新密码至少6位');
                    return;
                }

                fetch('/api/user/change-password', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ current_password: oldPassword, new_password: newPassword, confirm_password: confirmNew })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('密码修改成功！');
                        hideModal('changePasswordModal');
                    } else {
                        alert('修改失败: ' + data.message);
                    }
                })
                .catch(err => {
                    console.error('修改密码出错:', err);
                    alert('网络错误');
                });
            }

            function deleteAccount() {
                const password = document.getElementById('deletePassword').value.trim();
                if (!password) {
                    alert('请输入密码以确认');
                    return;
                }

                if (!confirm('确定要永久注销账号吗？此操作不可恢复！')) {
                    return;
                }

                fetch('/api/user/delete', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ current_password: password })
                })
                .then(res => res.json())
                .then(data => {
                    if (data.success) {
                        alert('账号已注销，即将返回首页。');
                        window.location.href = '/';
                    } else {
                        alert('注销失败: ' + data.message);
                    }
                })
                .catch(err => {
                    console.error('注销出错:', err);
                    alert('网络错误');
                });
            }
        </script>
    </body>
    </html>
    '''

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """提交反馈 - 添加敏感词检查"""
    try:
        data = request.get_json()
        original_content = data.get('content', '').strip()
        
        if not original_content:
            return jsonify({'success': False, 'message': '反馈内容不能为空'})
        
        username = session.get('username', '匿名用户')
        
        filtered_content, filtered_author, has_sensitive = filter_sensitive_content(original_content, username)
        
        display_author = filtered_author
        real_author = username
        
        if has_sensitive:
            client_ip = request.remote_addr
            logger.warning("检测到敏感词使用 - 用户: {}, IP: {}, 原始内容: {}, 过滤后: {}".format(username, client_ip, original_content, filtered_content))
        
        feedback_data = load_feedback_data()
        
        feedback = {
            'id': str(uuid.uuid4()),
            'original_content': original_content if has_sensitive else None,
            'content': filtered_content,
            'author': display_author,
            'real_author': real_author,
            'timestamp': datetime.now().isoformat(),
            'has_sensitive': has_sensitive,
            'client_ip': request.remote_addr if has_sensitive else None,
            'replies': []
        }
        
        feedback_data['feedbacks'].append(feedback)
        
        if save_feedback_data(feedback_data):
            message = '反馈提交成功'
            if has_sensitive:
                message += ' (检测到敏感词，已进行过滤处理)'
            
            return jsonify({
                'success': True, 
                'message': message,
                'has_sensitive': has_sensitive
            })
        else:
            return jsonify({'success': False, 'message': '保存反馈失败'})
            
    except Exception as e:
        logger.error(f"提交反馈失败: {e}")
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'})

@app.route('/api/feedback/reply', methods=['POST'])
def submit_reply():
    """回复反馈 - 根据来源判断是否为管理员回复"""
    try:
        # 检查请求来源（通过referer或自定义header）
        referer = request.headers.get('Referer', '')
        is_from_admin = '/admin/feedback' in referer
        
        # 也可以使用自定义header
        custom_source = request.headers.get('X-Reply-Source', '')
        if custom_source == 'admin':
            is_from_admin = True
        
        # 兼容原有的session检查
        session_admin = session.get(ADMIN_SESSION_KEY, False)
        is_admin_reply = is_from_admin or session_admin
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': '请求数据为空'})
            
        feedback_id = data.get('feedback_id')
        content = data.get('content', '').strip()
        
        if not feedback_id or not content:
            return jsonify({'success': False, 'message': '反馈ID和回复内容不能为空'})
        
        feedback_data = load_feedback_data()
        
        # 确保 feedback_data 是字典
        if not isinstance(feedback_data, dict):
            feedback_data = {"feedbacks": []}
        
        # 查找对应的反馈
        feedback_found = False
        for feedback in feedback_data.get('feedbacks', []):
            if feedback.get('id') == feedback_id:
                reply = {
                    'id': str(uuid.uuid4()),
                    'content': content,
                    'author': '管理员' if is_admin_reply else '用户',
                    'timestamp': datetime.now().isoformat(),
                    'is_admin': is_admin_reply,
                    'reply_source': 'admin' if is_admin_reply else 'user'  # 标记回复来源
                }
                
                # 确保 replies 列表存在
                if 'replies' not in feedback:
                    feedback['replies'] = []
                
                feedback['replies'].append(reply)
                feedback_found = True
                break
        
        if not feedback_found:
            return jsonify({'success': False, 'message': '反馈不存在'})
        
        if save_feedback_data(feedback_data):
            logger.info(f"回复已提交 - 反馈ID: {feedback_id}, 来源: {'管理员' if is_admin_reply else '用户'}")
            return jsonify({
                'success': True, 
                'message': '回复成功', 
                'is_admin': is_admin_reply,
                'author': '管理员' if is_admin_reply else '用户'
            })
        else:
            return jsonify({'success': False, 'message': '保存回复失败'})
            
    except Exception as e:
        logger.error(f"提交回复失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'})

# 添加管理员API查看原始内容
@app.route('/api/feedback/original/<feedback_id>', methods=['GET'])
def get_original_feedback(feedback_id):
    """管理员查看原始反馈内容"""
    # 这里可以添加管理员验证逻辑
    # 例如检查session或特定token
    
    feedback_data = load_feedback_data()
    
    for feedback in feedback_data['feedbacks']:
        if feedback['id'] == feedback_id and 'original_content' in feedback:
            return jsonify({
                'success': True,
                'original_content': feedback['original_content'],
                'filtered_content': feedback['content'],
                'author': feedback['author'],
                'has_sensitive': feedback.get('has_sensitive', False),
                'client_ip': feedback.get('client_ip', '未知')
            })
    
    return jsonify({'success': False, 'message': '反馈不存在或没有原始内容'})

# 管理员反馈管理相关路由
@app.route('/api/admin/feedback/delete/<feedback_id>', methods=['POST'])
@admin_required
def delete_feedback(feedback_id):
    """删除反馈"""
    try:
        feedback_data = load_feedback_data()
        feedbacks = feedback_data.get('feedbacks', [])
        
        # 查找要删除的反馈
        feedback_to_delete = None
        remaining_feedbacks = []
        
        for feedback in feedbacks:
            if feedback.get('id') == feedback_id:
                feedback_to_delete = feedback
            else:
                remaining_feedbacks.append(feedback)
        
        if not feedback_to_delete:
            return jsonify({'success': False, 'message': '反馈不存在'})
        
        # 记录删除操作
        admin_ip = request.remote_addr
        delete_log = {
            'feedback_id': feedback_id,
            'feedback_author': feedback_to_delete.get('author', '未知'),
            'feedback_content': feedback_to_delete.get('content', '')[:100],  # 只记录前100字符
            'has_sensitive': feedback_to_delete.get('has_sensitive', False),
            'admin_ip': admin_ip,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        admin_feedback_delete_logs.append(delete_log)
        
        # 只保留最近100条删除记录
        if len(admin_feedback_delete_logs) > 100:
            admin_feedback_delete_logs.pop(0)
        
        # 保存删除后的数据
        feedback_data['feedbacks'] = remaining_feedbacks
        save_feedback_data(feedback_data)
        
        logger.warning(f"管理员删除了反馈 - 反馈ID: {feedback_id}, 作者: {feedback_to_delete.get('author', '未知')}, 操作IP: {admin_ip}")
        
        return jsonify({
            'success': True, 
            'message': '反馈删除成功',
            'deleted_feedback': {
                'id': feedback_id,
                'author': feedback_to_delete.get('author', '未知')
            }
        })
        
    except Exception as e:
        logger.error(f"删除反馈失败: {e}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    """获取所有用户列表"""
    users = load_users()
    user_list = []
    for u in users:
        user_list.append({
            'username': u['username'],
            'register_time': u.get('register_time'),
            'register_ip': u.get('register_ip'),
            'last_login': u.get('last_login'),
            'last_ip': u.get('last_ip'),
            'banned': u.get('banned', False),
            'ban_expire': u.get('ban_expire'),
            'banned_reason': u.get('banned_reason'),
            'is_admin': u.get('is_admin', False)
        })
    return jsonify({'success': True, 'users': user_list})

@app.route('/api/admin/user/ban', methods=['POST'])
@admin_required
def admin_ban_user():
    """封禁用户"""
    data = request.get_json()
    username = data.get('username')
    duration = data.get('duration')
    reason = data.get('reason', '')
    
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    
    if username == session.get('username'):
        return jsonify({'success': False, 'message': '不能封禁自己'})
    
    users = load_users()
    for user in users:
        if user['username'] == username:
            if duration == 'permanent':
                user['banned'] = True
                user['ban_expire'] = None
            else:
                try:
                    minutes = int(duration)
                    expire_time = time.time() + minutes * 60
                    user['banned'] = True
                    user['ban_expire'] = expire_time
                except:
                    return jsonify({'success': False, 'message': '封禁时间格式错误'})
            user['banned_reason'] = reason
            save_users(users)
            
            ban_seconds = int(duration) * 60 if duration != 'permanent' else 315360000
            token = generate_token({'user_id': username, 'banned': True}, app.secret_key, ban_seconds)
            
            response_data = {'success': True, 'message': '用户 {} 已封禁'.format(username)}
            response = make_response(jsonify(response_data))
            
            max_age = ban_seconds
            response.set_cookie(
                'banned_token',
                token,
                max_age=max_age,
                httponly=True,
                secure=False,
                samesite='Lax'
            )
            
            logger.info("管理员 {} 封禁用户 {}, 时长: {}".format(session.get('username'), username, duration if duration != 'permanent' else '永久'))
            return response
    return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/api/admin/user/unban', methods=['POST'])
@admin_required
def admin_unban_user():
    """解封用户"""
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    
    users = load_users()
    for user in users:
        if user['username'] == username:
            user['banned'] = False
            user['ban_expire'] = None
            user['banned_reason'] = None
            save_users(users)
            
            response = make_response(jsonify({'success': True, 'message': '用户 {} 已解封'.format(username)}))
            response.set_cookie('banned_token', '', expires=0)
            logger.info("管理员 {} 解封用户 {}".format(session.get('username'), username))
            return response
    return jsonify({'success': False, 'message': '用户不存在'})

@app.route('/api/admin/user/delete', methods=['POST'])
@admin_required
def admin_delete_user():
    """管理员删除用户"""
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'message': '用户名不能为空'})
    
    if username == session.get('username'):
        return jsonify({'success': False, 'message': '不能删除自己'})
    
    users = load_users()
    new_users = [u for u in users if u['username'] != username]
    
    if len(new_users) == len(users):
        return jsonify({'success': False, 'message': '用户不存在'})
    
    if save_users(new_users):
        recycle_username(username)
        return jsonify({'success': True, 'message': '用户 {} 已删除'.format(username)})
    else:
        return jsonify({'success': False, 'message': '删除失败'})

@app.route('/admin/user-manager')
@admin_required
def admin_user_manager():
    """用户管理页面"""
    return '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <title>用户管理</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial; padding: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
            table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #eee; }
            th { background: #f8f9fa; font-weight: bold; color: #333; }
            tr:hover { background: #f5f5f5; }
            .btn { padding: 5px 10px; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; margin: 2px; }
            .btn-ban { background: #e74c3c; color: white; }
            .btn-unban { background: #27ae60; color: white; }
            .btn-delete { background: #c0392b; color: white; }
            .badge { padding: 3px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; }
            .badge-banned { background: #e74c3c; color: white; }
            .badge-active { background: #27ae60; color: white; }
            .nav-buttons { margin-bottom: 20px; }
            .nav-btn { padding: 10px 20px; background: #6c757d; color: white; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin-right: 10px; }
            .modal { display: none; position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; z-index:2000; opacity: 0; transition: opacity 0.3s ease; }
            .modal.show { display: flex; opacity: 1; }
            @keyframes modalPopIn { from { opacity: 0; transform: scale(0.9); } to { opacity: 1; transform: scale(1); } }
            .modal-content { background: white; padding: 30px; border-radius: 10px; width: 400px; animation: modalPopIn 0.3s ease-out; }
            .modal-header { display: flex; justify-content: space-between; margin-bottom: 20px; }
            .close-btn { background: none; border: none; font-size: 24px; cursor: pointer; }
            .form-group { margin-bottom: 15px; }
            .form-group label { display: block; margin-bottom: 5px; }
            .form-group input, .form-group select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; transition: all 0.2s ease; }
            .form-group input:focus { outline: none; border-color: #667eea !important; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); transform: scale(1.02); }
            .btn { transition: transform 0.2s, box-shadow 0.2s; }
            .btn:hover { transform: translateY(-2px) scale(1.02); box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3); }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>用户管理</h1>
                <p>管理所有注册用户</p>
            </div>
            <div class="nav-buttons">
                <a href="/admin/feedback" class="nav-btn">反馈管理</a>
                <a href="/admin/force-reboot-confirm" class="nav-btn">重启管理</a>
                <a href="/" class="nav-btn" target="_blank">主页</a>
                <button onclick="location.reload()" class="nav-btn">刷新</button>
            </div>
            <table id="userTable">
                <thead>
                    <tr>
                        <th>用户名</th>
                        <th>注册时间</th>
                        <th>注册IP</th>
                        <th>最后登录</th>
                        <th>最后IP</th>
                        <th>状态</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="userList"></tbody>
            </table>
        </div>

        <div class="modal" id="banModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>封禁用户</h3>
                    <button class="close-btn" onclick="hideBanModal()">x</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label for="banUsername">用户名</label>
                        <input type="text" id="banUsername" readonly title="用户名">
                    </div>
                    <div class="form-group">
                        <label for="banDuration">封禁类型</label>
                        <select id="banDuration">
                            <option value="permanent">永久封禁</option>
                            <option value="60">1小时</option>
                            <option value="1440">1天</option>
                            <option value="10080">7天</option>
                            <option value="43200">30天</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>封禁原因</label>
                        <input type="text" id="banReason" placeholder="可选">
                    </div>
                </div>
                <div class="modal-footer" style="text-align:right;">
                    <button class="btn btn-ban" onclick="submitBan()">确认封禁</button>
                    <button class="btn" onclick="hideBanModal()" style="background:#6c757d; color:white;">取消</button>
                </div>
            </div>
        </div>

        <script>
            var currentUsername = '';

            function loadUsers() {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/api/admin/users', true);
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4) {
                        if (xhr.status === 200) {
                            var data = JSON.parse(xhr.responseText);
                            console.log('用户数据:', data);
                            var tbody = document.getElementById('userList');
                            tbody.innerHTML = '';
                            if (!data.success || !data.users || data.users.length === 0) {
                                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;">暂无用户</td></tr>';
                                return;
                            }
                            for (var i = 0; i < data.users.length; i++) {
                                var user = data.users[i];
                                var row = document.createElement('tr');
                                var status = user.banned ? 
                                    '<span class="badge badge-banned">封禁中</span>' : 
                                    '<span class="badge badge-active">正常</span>';
                                var banInfo = '';
                                if (user.banned && user.ban_expire) {
                                    var expireDate = new Date(user.ban_expire * 1000);
                                    banInfo = '<br><small>解封于: ' + expireDate.toLocaleString() + '</small>';
                                } else if (user.banned) {
                                    banInfo = '<br><small>永久封禁</small>';
                                }
                                var btnHtml = user.banned ? 
                                    '<button class="btn btn-unban" data-user="' + user.username + '" onclick="unbanUser(this.dataset.user)">解封</button>' : 
                                    '<button class="btn btn-ban" data-user="' + user.username + '" onclick="showBanModal(this.dataset.user)">封禁</button>';
                                btnHtml += '<button class="btn btn-delete" data-user="' + user.username + '" onclick="deleteUser(this.dataset.user)">删除</button>';
                                row.innerHTML = '<td>' + user.username + '</td>' +
                                    '<td>' + (user.register_time || '未知') + '</td>' +
                                    '<td>' + (user.register_ip || '未知') + '</td>' +
                                    '<td>' + (user.last_login || '从未') + '</td>' +
                                    '<td>' + (user.last_ip || '未知') + '</td>' +
                                    '<td>' + status + banInfo + '</td>' +
                                    '<td>' + btnHtml + '</td>';
                                tbody.appendChild(row);
                            }
                        } else {
                            alert('加载失败');
                        }
                    }
                };
                xhr.send();
            }

            function showBanModal(username) {
                currentUsername = username;
                document.getElementById('banUsername').value = username;
                document.getElementById('banReason').value = '';
                document.getElementById('banDuration').value = 'permanent';
                document.getElementById('banModal').classList.add('show');
            }

            function hideBanModal() {
                document.getElementById('banModal').classList.remove('show');
            }

            function submitBan() {
                var username = currentUsername;
                var duration = document.getElementById('banDuration').value;
                var reason = document.getElementById('banReason').value.trim();

                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/api/admin/user/ban', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4 && xhr.status === 200) {
                        var data = JSON.parse(xhr.responseText);
                        if (data.success) {
                            alert(data.message);
                            hideBanModal();
                            loadUsers();
                        } else {
                            alert('封禁失败: ' + data.message);
                        }
                    }
                };
                xhr.send(JSON.stringify({username: username, duration: duration, reason: reason}));
            }

            function unbanUser(username) {
                if (!confirm('确定解封用户 ' + username + ' 吗？')) return;
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/api/admin/user/unban', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4 && xhr.status === 200) {
                        var data = JSON.parse(xhr.responseText);
                        if (data.success) {
                            alert(data.message);
                            loadUsers();
                        } else {
                            alert('解封失败: ' + data.message);
                        }
                    }
                };
                xhr.send(JSON.stringify({username: username}));
            }

            function deleteUser(username) {
                if (!confirm('确定要永久删除用户 ' + username + ' 吗？此操作不可恢复！')) return;
                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/api/admin/user/delete', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4 && xhr.status === 200) {
                        var data = JSON.parse(xhr.responseText);
                        if (data.success) {
                            alert(data.message);
                            loadUsers();
                        } else {
                            alert('删除失败: ' + data.message);
                        }
                    }
                };
                xhr.send(JSON.stringify({username: username}));
            }

            window.onload = loadUsers;
        </script>
    </body>
    </html>
    '''

# 管理员页面路由
@app.route('/admin/login')
def admin_login():
    """管理员登录页面"""
    if session.get(ADMIN_SESSION_KEY, False):
        return redirect('/admin/feedback')
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>管理员登录</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .login-container {
                background: white;
                padding: 40px;
                border-radius: 10px;
                box-shadow: 0 15px 35px rgba(0, 0, 0, 0.1);
                width: 90%;
                max-width: 400px;
            }
            .login-title {
                text-align: center;
                color: #333;
                margin-bottom: 30px;
                font-size: 24px;
                font-weight: bold;
            }
            .form-group {
                margin-bottom: 20px;
            }
            .form-group label {
                display: block;
                margin-bottom: 5px;
                color: #555;
                font-weight: bold;
            }
            .form-group input {
                width: 100%;
                padding: 12px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 16px;
                box-sizing: border-box;
            }
            .form-group input:focus {
                outline: none;
                border-color: #667eea;
                box-shadow: 0 0 5px rgba(102, 126, 234, 0.3);
            }
            .login-btn {
                width: 100%;
                padding: 12px;
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: transform 0.2s;
            }
            .login-btn:hover {
                transform: translateY(-2px);
            }
            .back-link {
                text-align: center;
                margin-top: 20px;
            }
            .back-link a {
                color: #667eea;
                text-decoration: none;
            }
            .error-message {
                color: #dc3545;
                text-align: center;
                margin-bottom: 15px;
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <div class="login-title">🔐 管理员登录</div>
            <div class="error-message" id="errorMessage"></div>
            <form id="loginForm">
                <div class="form-group">
                    <label for="password">管理员密码:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="login-btn">登录</button>
            </form>
            <div class="back-link">
                <a href="/">返回主页</a>
            </div>
        </div>

        <script>
            document.getElementById('loginForm').addEventListener('submit', function(e) {
                e.preventDefault();
                
                const password = document.getElementById('password').value;
                const errorMessage = document.getElementById('errorMessage');
                
                fetch('/admin/verify', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ password: password })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        window.location.href = '/admin/feedback';
                    } else {
                        errorMessage.textContent = data.message || '登录失败';
                        errorMessage.style.display = 'block';
                    }
                })
                .catch(error => {
                    console.error('登录错误:', error);
                    errorMessage.textContent = '网络错误，请稍后重试';
                    errorMessage.style.display = 'block';
                });
            });
        </script>
    </body>
    </html>
    '''

@app.route('/admin/verify', methods=['POST'])
def admin_verify():
    """验证管理员密码"""
    try:
        data = request.get_json()
        password = data.get('password', '')
        
        if password == ADMIN_PASSWORD:
            session[ADMIN_SESSION_KEY] = True
            logger.info(f"管理员登录成功 - IP: {request.remote_addr}")
            return jsonify({'success': True, 'message': '登录成功'})
        else:
            logger.warning(f"管理员登录失败 - IP: {request.remote_addr}, 密码: {password}")
            return jsonify({'success': False, 'message': '密码错误'})
            
    except Exception as e:
        logger.error(f"管理员验证失败: {e}")
        return jsonify({'success': False, 'message': '验证失败'})

@app.route('/admin/logout')
def admin_logout():
    """管理员退出登录"""
    session.pop(ADMIN_SESSION_KEY, None)
    logger.info(f"管理员退出登录 - IP: {request.remote_addr}")
    return redirect('/admin/login')

@app.route('/admin/feedback-manager')
def admin_feedback_manager():
    """管理员反馈管理页面（别名）"""
    return redirect('/admin/feedback')

@app.route('/admin/feedback')
@admin_required
def admin_feedback():
    """管理员反馈管理页面"""
    try:
        feedback_data = load_feedback_data()
        feedbacks = feedback_data.get('feedbacks', [])
        
        # 统计数据
        total_count = len(feedbacks)
        sensitive_count = sum(1 for f in feedbacks if f.get('has_sensitive', False))
        
        # 生成反馈HTML
        feedbacks_html = ""
        for feedback in sorted(feedbacks, key=lambda x: x.get('timestamp', ''), reverse=True):
            feedback_id = feedback.get('id', '')
            author = feedback.get('author', '未知')
            content = feedback.get('content', '')
            timestamp = feedback.get('timestamp', '')
            has_sensitive = feedback.get('has_sensitive', False)
            
            # 格式化时间
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                formatted_time = timestamp
            
            sensitive_badge = ' <span style="background:#dc3545;color:white;padding:2px 6px;border-radius:3px;font-size:10px;">⚠️ 敏感</span>' if has_sensitive else ''
            
            # 生成回复HTML
            replies = feedback.get('replies', [])
            replies_html = ""
            if replies:
                for reply in replies:
                    if not isinstance(reply, dict):
                        continue
                    reply_author = reply.get('author', '用户')
                    reply_content = reply.get('content', '')
                    reply_time = reply.get('timestamp', '')
                    is_admin_reply = reply.get('is_admin', False) or reply_author == '管理员'
                    
                    # 添加管理员标识
                    admin_badge = " <span style='color:#dc3545; font-weight:bold;'>(👑 管理员)</span>" if is_admin_reply else " <span style='color:#28a745;'>(👤 用户)</span>"
                    
                    try:
                        if reply_time:
                            reply_time_display = datetime.fromisoformat(reply_time.replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                        else:
                            reply_time_display = "未知时间"
                    except:
                        reply_time_display = reply_time or "未知时间"
                    
                    replies_html += f'''
                    <div style="background: #e8f4fd; padding: 8px; margin: 5px 0; border-radius: 5px; border-left: 4px solid {'#dc3545' if is_admin_reply else '#28a745'};">
                        <strong>{reply_author}{admin_badge}</strong> <span style="color:#666; font-size:11px;">{reply_time_display}</span>
                        <div>{reply_content}</div>
                    </div>
                    '''
            else:
                replies_html = '<div style="color:#999; font-style:italic; padding: 10px;">暂无回复</div>'
            
            feedbacks_html += f'''
            <div class="feedback-item" id="feedback-{feedback_id}">
                <div class="feedback-header">
                    <strong>{author}</strong>{sensitive_badge}
                    <span class="feedback-time">{formatted_time}</span>
                </div>
                <div class="feedback-content">{content}</div>
                
                <!-- 回复显示区域 -->
                <div class="replies-section" style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee;">
                    <strong>回复:</strong>
                    <div class="replies-container">
                        {replies_html}
                    </div>
                </div>
                
                <div class="feedback-actions">
                    <button onclick="deleteFeedback('{feedback_id}')" class="delete-btn">删除</button>
                    <button onclick="showReplyForm('{feedback_id}')" class="reply-btn">回复</button>
                    <div id="reply-form-{feedback_id}" class="reply-form" style="display:none;">
                        <textarea id="reply-text-{feedback_id}" placeholder="请输入回复内容..."></textarea>
                        <button onclick="submitReply('{feedback_id}')">提交回复</button>
                    </div>
                </div>
            </div>
            '''
        
        if not feedbacks_html:
            feedbacks_html = '<div style="text-align:center;color:#666;padding:20px;">暂无反馈</div>'
        
        # 生成删除记录HTML
        delete_logs_html = ""
        for log in admin_feedback_delete_logs[-20:]:  # 显示最近20条记录
            delete_logs_html += f'''
            <div class="log-item">
                <strong>删除了反馈 #{log.get('feedback_id', 'unknown')[:8]}</strong><br>
                操作时间: {log.get('time', '')} | 操作者: {log.get('admin_ip', '未知')}<br>
                反馈作者: {log.get('feedback_author', '未知')}
            </div>
            '''
        
        if not delete_logs_html:
            delete_logs_html = '<div style="text-align:center;color:#666;padding:20px;">暂无删除记录</div>'
        
        return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>反馈管理</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .header {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .stats {{
                    display: flex;
                    gap: 20px;
                }}
                .stat-item {{
                    text-align: center;
                }}
                .stat-number {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #667eea;
                }}
                .feedback-item {{
                    background: white;
                    margin: 10px 0;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                }}
                .feedback-header {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 10px;
                }}
                .feedback-time {{
                    color: #666;
                    font-size: 12px;
                }}
                .feedback-content {{
                    margin: 10px 0;
                    line-height: 1.6;
                }}
                .feedback-actions {{
                    margin-top: 15px;
                }}
                .delete-btn {{
                    background: #dc3545;
                    color: white;
                    border: none;
                    padding: 5px 10px;
                    border-radius: 5px;
                    cursor: pointer;
                    margin-right: 10px;
                }}
                .reply-btn {{
                    background: #667eea;
                    color: white;
                    border: none;
                    padding: 5px 10px;
                    border-radius: 5px;
                    cursor: pointer;
                }}
                .reply-form {{
                    margin-top: 10px;
                }}
                .reply-form textarea {{
                    width: 100%;
                    padding: 10px;
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    resize: vertical;
                    min-height: 80px;
                }}
                .reply-form button {{
                    margin-top: 10px;
                    padding: 8px 16px;
                    background: #28a745;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                }}
                .admin-nav {{
                    background: white;
                    padding: 15px;
                    border-radius: 10px;
                    margin-bottom: 20px;
                    text-align: center;
                }}
                .admin-nav a {{
                    margin: 0 15px;
                    padding: 8px 16px;
                    background: #667eea;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                }}
                .delete-log {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    margin-top: 20px;
                }}
                .log-item {{
                    padding: 10px;
                    border-bottom: 1px solid #eee;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📋 反馈管理</h1>
                <div>
                    <a href="/admin/logout" style="background:#dc3545;color:white;padding:8px 16px;text-decoration:none;border-radius:5px;">退出登录</a>
                </div>
            </div>
            
            <div class="admin-nav">
                <a href="/">返回主页</a>
                <a href="/admin/feedback">反馈管理</a>
            </div>
            
            <div class="header">
                <h2>📊 统计信息</h2>
                <div class="stats">
                    <div class="stat-item">
                        <div class="stat-number">{total_count}</div>
                        <div>总反馈数</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">{sensitive_count}</div>
                        <div>含敏感词</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">{len(admin_feedback_delete_logs)}</div>
                        <div>删除记录</div>
                    </div>
                </div>
            </div>
            
            <div class="feedbacks-list">
                <h2>📝 所有反馈</h2>
                {feedbacks_html}
            </div>
            
            <div class="delete-log">
                <h3>🗑️ 删除记录</h3>
                {delete_logs_html}
            </div>
            
            <script>
                function deleteFeedback(feedbackId) {{
                    if (!confirm('确定要删除这条反馈吗？此操作不可恢复！')) {{
                        return;
                    }}
                    
                    fetch(`/api/admin/feedback/delete/${{feedbackId}}`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }}
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('删除成功！');
                            const feedbackElement = document.getElementById(`feedback-${{feedbackId}}`);
                            if (feedbackElement) {{
                                feedbackElement.style.backgroundColor = '#ffe6e6';
                                feedbackElement.style.opacity = '0.5';
                                setTimeout(() => feedbackElement.remove(), 500);
                            }}
                        }} else {{
                            alert('删除失败: ' + data.message);
                        }}
                    }})
                    .catch(error => {{
                        console.error('删除失败:', error);
                        alert('网络错误，删除失败');
                    }});
                }}
                
                function showReplyForm(feedbackId) {{
                    const form = document.getElementById(`reply-form-${{feedbackId}}`);
                    form.style.display = form.style.display === 'none' ? 'block' : 'none';
                }}
                
                function submitReply(feedbackId) {{
                    const textarea = document.getElementById(`reply-text-${{feedbackId}}`);
                    const content = textarea.value.trim();
                    
                    if (!content) {{
                        alert('请输入回复内容');
                        return;
                    }}
                    
                    fetch('/api/feedback/reply', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-Reply-Source': 'admin'  // 标记来自管理员页面
                        }},
                        body: JSON.stringify({{
                            feedback_id: feedbackId,
                            content: content
                        }})
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        if (data.success) {{
                            alert('管理员回复成功！');
                            textarea.value = '';
                            location.reload();
                        }} else {{
                            alert('回复失败: ' + data.message);
                        }}
                    }})
                    .catch(error => {{
                        console.error('回复失败:', error);
                        alert('网络错误，回复失败');
                    }});
                }}
            </script>
        </body>
        </html>
        '''
    except Exception as e:
        logger.error(f"管理员反馈页面加载失败: {e}")
        return "页面加载失败", 500

@app.route('/admin/page-stats')
@admin_required
def page_stats():
    """页面访问统计"""
    return jsonify({
        'current_users': page_user_count,
        'max_users': MAX_PAGE_USERS,
        'vnc_stats': vnc_proxy.get_connection_stats(),
        'force_reboot_requests': len(force_reboot_requests),
        'pending_requests': get_pending_requests_count()
    })

# VNC相关路由
@app.route('/api/vnc/start', methods=['POST'])
def start_vnc():
    """启动VNC代理服务"""
    try:
        # 检查是否已经在运行
        if vnc_proxy.is_running:
            return jsonify({
                'success': True,
                'message': 'VNC代理服务已在运行',
                'urls': vnc_proxy.get_access_urls()
            })
        
        success, message = vnc_proxy.start_websockify()
        
        if success:
            # 等待服务启动
            time.sleep(2)
            return jsonify({
                'success': True,
                'message': message,
                'urls': vnc_proxy.get_access_urls()
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            })
            
    except Exception as e:
        logger.error(f"启动VNC代理失败: {e}")
        return jsonify({
            'success': False,
            'message': f'启动VNC代理失败: {str(e)}'
        })

@app.route('/api/vnc/stop', methods=['POST'])
def stop_vnc():
    """停止VNC代理服务"""
    try:
        vnc_proxy.stop_websockify()
        return jsonify({
            'success': True,
            'message': 'VNC代理服务已停止'
        })
    except Exception as e:
        logger.error(f"停止VNC代理失败: {e}")
        return jsonify({
            'success': False,
            'message': f'停止VNC代理失败: {str(e)}'
        })

@app.route('/api/vnc/status', methods=['GET'])
def get_vnc_status():
    """获取VNC代理状态"""
    return jsonify({
        'is_running': vnc_proxy.is_running,
        'vnc_host': VNC_HOST,
        'vnc_port': VNC_PORT,
        'web_port': 6080,
        'urls': vnc_proxy.get_access_urls() if vnc_proxy.is_running else {},
        'connection_stats': vnc_proxy.get_connection_stats()  # 新增：连接统计
    })

@app.route('/api/vnc/open-browser', methods=['POST'])
def open_vnc_browser():
    """在浏览器中打开VNC界面"""
    try:
        if not vnc_proxy.is_running:
            return jsonify({
                'success': False,
                'message': 'VNC代理服务未运行，请先启动服务'
            })
        
        urls = vnc_proxy.get_access_urls()
        webbrowser.open(urls['local'])
        
        return jsonify({
            'success': True,
            'message': '正在浏览器中打开VNC界面',
            'url': urls['local']
        })
    except Exception as e:
        logger.error(f"打开浏览器失败: {e}")
        return jsonify({
            'success': False,
            'message': f'打开浏览器失败: {str(e)}'
        })

def check_vmware_service():
    """检查VMware服务状态"""
    try:
        # 检查VMware Workstation Server服务
        result = subprocess.run(
            'sc query "VMware Workstation Server"',
            shell=True,
            capture_output=True,
            text=True,
            encoding='gbk'  # Windows中文系统使用gbk编码
        )
        
        if "RUNNING" in result.stdout:
            logger.info("✓ VMware Workstation Server服务正在运行")
            return True
        else:
            logger.warning("✗ VMware Workstation Server服务未运行")
            
            # 尝试启动服务
            logger.info("尝试启动VMware Workstation Server服务...")
            start_result = subprocess.run(
                'net start "VMware Workstation Server"',
                shell=True,
                capture_output=True,
                text=True,
                encoding='gbk'
            )
            
            if start_result.returncode == 0:
                logger.info("✓ VMware Workstation Server服务已启动")
                return True
            else:
                logger.error(f"✗ 启动VMware服务失败: {start_result.stderr}")
                return False
                
    except Exception as e:
        logger.error(f"检查VMware服务状态失败: {e}")
        return False

# 初始化VNC配置并显示信息
def init_vnc_config():
    """初始化VNC配置并显示信息"""
    print(f"VNC配置信息:")
    print(f"  - 服务器地址: {VNC_HOST}:{VNC_PORT}")
    print(f"  - Web端口: 6080")
    print(f"  - 本机IP: {LOCAL_IP}")
    if PUBLIC_URL:
        print(f"  - 公网地址: {PUBLIC_URL}")
    print("")

if __name__ == '__main__':
    def init_admin_account():
        """确保存在一个管理员账号，若不存在则创建默认管理员"""
        users = load_users()
        admin_exists = any(user.get('is_admin', False) for user in users)
        if not admin_exists:
            default_admin = {
                'username': 'admin剠歼刭',
                'password_hash': generate_password_hash('134679'),
                'register_time': datetime.now().isoformat(),
                'register_ip': '127.0.0.1',
                'last_login': None,
                'last_ip': None,
                'banned': False,
                'ban_expire': None,
                'banned_reason': None,
                'is_admin': True
            }
            users.append(default_admin)
            if save_users(users):
                logger.info("已创建管理员账号：admin剠歼刭")
                print("已创建管理员账号：admin剠歼刭")
            else:
                logger.error("创建管理员账号失败")
    
    init_admin_account()
    
    if not os.path.exists(USER_COUNTER_FILE):
        save_user_counter(1)
        print("已创建用户计数器文件，初始序号为1")
    
    if not os.path.exists(AVAILABLE_USERNAMES_FILE):
        save_available_usernames([])
        print("已创建可用用户名池文件")
    
    if not os.path.exists(REGISTER_COUNT_FILE):
        save_register_count(0)
        print("已创建注册计数文件，初始计数为0")
    
    clear_console()
    
    print("=" * 80)
    print(" " * 30 + "🖥️  虚拟机远程控制系统")
    print("=" * 80)
    print(f"虚拟机名称: {vm_status['vm_name']}")
    print(f"配置文件: {VMX_PATH}")
    print(f"vmrun路径: {VMRUN_PATH}")
    print(f"VMware路径: {VMWARE_EXE_PATH}")
    print(f"VNC服务器: {VNC_HOST}:{VNC_PORT} (自动获取本机IP)")
    print(f"公网RVNC地址: 10.tcp.cpolar.top:12574")
    print(f"本地访问地址: http://127.0.0.1:5000")
    print(f"网络访问地址: http://{LOCAL_IP}:5000")
    print(f"重启管理: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
    print("请确保防火墙已放行5000端口")
    print("=" * 80)
    
    # 检查VMware服务
    if not check_vmware_service():
        print("警告: VMware服务可能有问题，虚拟机启动可能失败")
        print("请以管理员身份运行此程序，并确保VMware已正确安装")
        print()
    
    # 检查依赖
    try:
        import psutil
        print("✓ psutil库已安装，性能监控功能可用")
    except ImportError:
        print("✗ psutil库未安装，性能监控功能将不可用")
        print("请运行: pip install psutil")
    
    # 检查vmrun.exe是否存在
    if not os.path.exists(VMRUN_PATH):
        print(f"✗ vmrun.exe不存在于 {VMRUN_PATH}")
        print("请检查路径是否正确")
        exit(1)
    
    # 检查虚拟机配置文件是否存在
    if not os.path.exists(VMX_PATH):
        print(f"⚠ 虚拟机配置文件不存在于 {VMX_PATH}")
    
    # 检查noVNC目录
    if not os.path.exists(NOVNC_PATH):
        print(f"⚠ noVNC目录不存在于 {NOVNC_PATH}")
        print("VNC代理功能将不可用")
    else:
        print("✓ noVNC目录存在，VNC代理功能可用")
    
    # 检查websockify是否安装
    try:
        subprocess.run(['websockify', '--version'], capture_output=True, timeout=5)
        print("✓ websockify已安装")
    except:
        print("✗ websockify未安装，VNC代理功能将不可用")
        print("请安装: pip install websockify")
    
    # 检查Flask-SocketIO是否安装
    try:
        import flask_socketio
        print("✓ Flask-SocketIO已安装")
    except ImportError:
        print("✗ Flask-SocketIO未安装，连接监控功能将不可用")
        print("请安装: pip install flask-socketio")
    
    # 修复反馈数据格式
    print("正在检查反馈数据格式...")
    if repair_feedback_data():
        print("✓ 反馈数据格式检查完成")
    else:
        print("⚠ 反馈数据格式检查失败，但将继续启动")
    
    # 新增：显示VNC配置信息
    print(f"✓ VNC服务器配置: {VNC_HOST}:{VNC_PORT} (使用本机IP)")
    
    # 显示管理员信息
    print(f"管理员密码: {ADMIN_PASSWORD}")
    print(f"反馈管理页面: http://{LOCAL_IP}:5000/admin/login")
    print("=" * 80)
    print("启动控制台自动刷新...")
    
    # 启动控制台自动刷新
    start_console_refresh()
    
    # 等待2秒让控制台刷新显示
    time.sleep(2)
    
    # 启动服务器
    try:
        print("\n使用SocketIO启动服务器...")
        print("按 Ctrl+C 停止程序")
        print("-" * 80)
        
        # 使用SocketIO启动
        socketio.run(
            app, 
            host='0.0.0.0', 
            port=5000, 
            debug=False,
            allow_unsafe_werkzeug=True  # 添加这个参数以兼容新版本
        )
    except KeyboardInterrupt:
        print("\n正在停止系统...")
        stop_console_refresh()
        print("系统已停止")
    except Exception as e:
        print(f"启动SocketIO服务器失败: {e}")
        print("尝试使用Flask开发服务器")
        stop_console_refresh()
        app.run(host='0.0.0.0', port=5000, debug=False)


# SocketIO 连接事件处理
@socketio.on('connect')
def handle_connect():
    logger.info(f"客户端连接: {request.sid}")
    
    # 添加页面用户计数
    with page_users_lock:
        if page_user_count < MAX_PAGE_USERS:
            page_user_count += 1
            logger.info(f"页面访问人数: {page_user_count}/{MAX_PAGE_USERS}")
        else:
            logger.warning(f"页面访问人数已达上限: {page_user_count}/{MAX_PAGE_USERS}")
    
    # 广播更新页面用户数
    socketio.emit('page_user_count_update', {
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS
    })
    
@socketio.on('disconnect')
def handle_disconnect():
    logger.info(f"客户端断开连接: {request.sid}")
    
    # 减少页面用户计数
    with page_users_lock:
        if page_user_count > 0:
            page_user_count -= 1
            logger.info(f"页面访问人数: {page_user_count}/{MAX_PAGE_USERS}")
    
    # 广播更新页面用户数
    socketio.emit('page_user_count_update', {
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS
    })

@socketio.on('get_vnc_stats')
def handle_get_vnc_stats():
    """处理获取VNC统计信息的请求"""
    emit('vnc_user_count_update', vnc_proxy.get_connection_stats())

@socketio.on('get_page_stats')
def handle_get_page_stats():
    """处理获取页面统计信息的请求"""
    with page_users_lock:
        emit('page_user_count_update', {
            'current': page_user_count,
            'max': MAX_PAGE_USERS,
            'is_full': page_user_count >= MAX_PAGE_USERS
        })