# 在文件开头的导入部分添加
import signal
import sys
import os
import threading
import time
from datetime import datetime
import subprocess

from flask import Flask, request, jsonify, session
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
from flask_socketio import SocketIO, emit
import signal  # 新增
import sys     # 确保有这个

# 控制台刷新配置
console_refresh_enabled = True
console_refresh_interval = 10  # 秒
console_refresh_thread = None
console_last_refresh = None

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
    print(f"强制重启管理: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
    print("-" * 80)
    
    # 虚拟机状态
    vm_state = "✅ 运行中" if vm_status.get('is_running', False) else "❌ 已停止"
    if vm_status.get('is_rebooting', False):
        vm_state = "🔄 重启中"
    
    print(f"虚拟机状态: {vm_state}")
    print(f"虚拟机名称: {vm_status.get('vm_name', '未知')}")
    print("-" * 80)
    
    # 强制重启请求状态
    print(f"🚨 待处理强制重启请求: {pending_count}")
    print("-" * 80)
    
    if pending_count > 0:
        # 显示待处理请求
        print("编号 | 确认ID           | 客户端IP        | 请求时间  | 剩余时间 | 状态")
        print("-" * 80)
        
        i = 1
        for confirm_id, info in force_reboot_requests.items():
            if not info['confirmed']:
                request_time = info['request_time'].strftime("%H:%M:%S")
                remaining = format_time_remaining(info['request_time'])
                client_ip = info['client_ip'][:15] if len(info['client_ip']) > 15 else info['client_ip']
                confirm_id_short = confirm_id[:8] + "..." if len(confirm_id) > 8 else confirm_id
                
                print(f"{i:3d} | {confirm_id_short:16s} | {client_ip:15s} | {request_time:9s} | {remaining:8s} | ⏳等待确认")
                i += 1
        
        print("-" * 80)
        print("操作指南:")
        print("  1. 访问管理页面: http://" + LOCAL_IP + ":5000/admin/force-reboot-confirm")
        print("  2. 输入确认ID并选择 '允许' 或 '拒绝'")
        print("  3. 或等待剩余时间为 00:00 自动允许")
        print()
    else:
        print("📭 当前没有待处理的强制重启请求")
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
                action = "⏰ 超时允许"
            
            confirm_time = info.get('confirm_time', info['request_time'])
            if isinstance(confirm_time, datetime):
                time_str = confirm_time.strftime("%H:%M:%S")
            else:
                time_str = str(confirm_time)[11:19] if len(str(confirm_time)) > 19 else str(confirm_time)
            
            print(f"{i+1:2d}. {confirm_id_short:16s} | {client_ip:15s} | {time_str:8s} | {action}")
    
    # 系统性能概览（可选）
    print("-" * 80)
    try:
        # 获取CPU和内存使用率
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        print(f"系统性能: CPU: {cpu_percent:5.1f}% | 内存: {memory_percent:5.1f}%")
    except:
        print("系统性能: 监控不可用")
    
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
app.secret_key = 'your_secret_key_here'  # 用于session管理
socketio = SocketIO(app, cors_allowed_origins="*")  # 新增SocketIO

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

# VMware配置路径
VMRUN_PATH = r"C:\VMware\VMware Workstation\vmrun.exe"
VMWARE_EXE_PATH = r"C:\MV\vmware.exe"
VMX_PATH = r"E:\Hypv\战神CF极致高帧版（W10）.vmx"

# VNC配置路径、公网
VNC_HOST = "192.168.200.104"
VNC_PORT = 5900
NOVNC_PATH = r"D:\Program Files\noVNC-master"
PUBLIC_URL = "https://776b2585.r10.cpolar.top"

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
CONFIRM_TIMEOUT = 180  # 3分钟超时

# 反馈数据存储
FEEDBACK_FILE = "feedback_data.json"

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
                            'max': self.max_connections
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

def load_feedback_data():
    """加载反馈数据"""
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"加载反馈数据失败: {e}")
    return {"feedbacks": []}

def save_feedback_data(data):
    """保存反馈数据"""
    try:
        with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存反馈数据失败: {e}")
        return False

def check_vm_status():
    """检查虚拟机状态"""
    try:
        cmd = [VMRUN_PATH, 'list']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=30)
        
        if result.returncode == 0:
            if VMX_PATH in result.stdout:
                return True, None
            else:
                return False, None
        else:
            error_msg = f"检查虚拟机状态失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"检查虚拟机状态异常: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def start_virtual_machine():
    """启动虚拟机"""
    try:
        logger.info(f"开始启动虚拟机: {VMX_PATH}")
        
        cmd = [VMRUN_PATH, 'start', VMX_PATH, 'nogui']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=120)
        
        if result.returncode == 0:
            logger.info(f"虚拟机启动成功: {result.stdout}")
            
            # 自动打开VMware图形界面
            try:
                if os.path.exists(VMWARE_EXE_PATH):
                    logger.info(f"正在自动打开VMware图形界面: {VMWARE_EXE_PATH}")
                    subprocess.Popen([VMWARE_EXE_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    vm_status['vmware_opened'] = True
                    return True, "虚拟机启动成功并已自动打开VMware图形界面"
                else:
                    return True, "虚拟机启动成功，但未找到VMware图形界面程序"
            except Exception as e:
                return True, "虚拟机启动成功，但打开VMware图形界面失败"
        else:
            error_msg = f"启动失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
    except Exception as e:
        error_msg = f"启动过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def force_shutdown_virtual_machine():
    """强制关闭虚拟机（硬关机）"""
    try:
        logger.info(f"开始强制关闭虚拟机: {VMX_PATH}")
        
        # 使用hard参数强制断电
        cmd = [VMRUN_PATH, 'stop', VMX_PATH, 'hard']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=30)
        
        if result.returncode == 0:
            logger.info(f"虚拟机强制关闭成功: {result.stdout}")
            return True, "虚拟机强制关闭成功"
        else:
            # 尝试其他强制关闭方法
            try:
                # 方法2：直接终止进程
                cmd = ['taskkill', '/F', '/IM', 'vmware-vmx.exe']
                subprocess.run(cmd, capture_output=True, timeout=10)
                logger.info("尝试终止VMware进程")
                return True, "通过终止进程强制关闭"
            except:
                error_msg = f"强制关闭失败: {result.stderr}"
                logger.error(error_msg)
                return False, error_msg
    except Exception as e:
        error_msg = f"强制关闭过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def force_reboot_virtual_machine():
    """强制重启虚拟机"""
    try:
        logger.info(f"开始强制重启虚拟机: {VMX_PATH}")
        
        # 第一步：强制关闭
        success, message = force_shutdown_virtual_machine()
        if not success:
            return False, f"强制关闭失败: {message}"
        
        # 等待更短时间（强制重启）
        logger.info("等待系统完全关闭...")
        time.sleep(5)
        
        # 第二步：立即启动
        success, message = start_virtual_machine()
        if not success:
            return False, f"启动失败: {message}"
        
        logger.info("虚拟机强制重启完成")
        return True, "虚拟机强制重启完成"
        
    except Exception as e:
        error_msg = f"强制重启过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def get_system_performance():
    """获取系统性能数据"""
    try:
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024**3), 1)
        memory_used_gb = round(memory.used / (1024**3), 1)
        memory_percent = memory.percent
        
        # 网络IO（发送和接收的字节数）
        net_io = psutil.net_io_counters()
        net_sent_mb = round(net_io.bytes_sent / (1024**2), 2)
        net_recv_mb = round(net_io.bytes_recv / (1024**2), 2)
        
        # 系统启动时间
        boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
        
        return {
            'cpu_percent': cpu_percent,
            'memory_total_gb': memory_total_gb,
            'memory_used_gb': memory_used_gb,
            'memory_percent': memory_percent,
            'net_sent_mb': net_sent_mb,
            'net_recv_mb': net_recv_mb,
            'boot_time': boot_time,
            'timestamp': datetime.now().strftime("%H:%M:%S")
        }
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

# 新增：页面访问人数监控的WebSocket事件处理
@socketio.on('connect')
def handle_connect():
    """处理客户端连接 - 页面访问人数监控"""
    global page_user_count
    
    # 检查是否达到人数上限
    with page_users_lock:
        if page_user_count >= MAX_PAGE_USERS:
            # 拒绝新连接
            return False
        
        page_user_count += 1
        page_connected_users[request.sid] = {
            'connect_time': datetime.now().isoformat(),
            'ip': request.remote_addr
        }
    
    # 广播更新页面访问人数
    emit('page_user_count_update', {
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS
    }, broadcast=True)
    
    # 原有的VNC统计发送
    emit('vnc_user_count_update', vnc_proxy.get_connection_stats())
    
    logger.info(f"新用户连接，当前页面访问人数: {page_user_count}/{MAX_PAGE_USERS}")

@socketio.on('disconnect')
def handle_disconnect():
    """处理客户端断开连接"""
    global page_user_count
    
    with page_users_lock:
        if request.sid in page_connected_users:
            page_user_count -= 1
            del page_connected_users[request.sid]
    
    # 广播更新页面访问人数
    emit('page_user_count_update', {
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS
    }, broadcast=True)
    
    logger.info(f"用户断开连接，当前页面访问人数: {page_user_count}/{MAX_PAGE_USERS}")

@socketio.on('get_page_stats')
def handle_get_page_stats():
    """处理获取页面统计请求"""
    emit('page_user_count_update', {
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS
    })

@socketio.on('get_vnc_stats')
def handle_get_vnc_stats():
    """处理获取VNC统计请求"""
    emit('vnc_user_count_update', vnc_proxy.get_connection_stats())

@app.route('/')
def index():
    """提供包含性能监控和反馈系统的主页"""
    html_content = '''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>虚拟机远程控制系统</title>
        <style>
            * { 
                margin: 0; 
                padding: 0; 
                box-sizing: border-box; 
            }
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
                max-width: 800px;
                width: 100%;
                position: relative;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                position: relative;
            }
            .header h1 {
                color: #333;
                font-size: 28px;
                margin-bottom: 10px;
            }
            .header p {
                color: #666;
                font-size: 16px;
            }
            /* 新增：页面访问人数显示样式 */
            .page-users {
                position: absolute;
                top: 0;
                right: 120px;
                background: #17a2b8;
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
                background: #ffc107;
                color: #212529;
                animation: pulse 2s infinite;
            }
            
            .page-users.at-limit {
                background: #dc3545;
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
                background: #17a2b8;
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
                background: #ffc107;
                color: #212529;
            }
            .vnc-users.max-usage {
                background: #dc3545;
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
            }
            .modal.show {
                display: flex;
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
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
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
                box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
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
                background: #e9ecef;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }
            .vm-info h3 {
                margin-top: 0;
                color: #495057;
            }
            .performance-info {
                background: #e8f4fd;
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
                background: linear-gradient(90deg, #4CAF50, #8BC34A);
            }
            .progress-memory {
                background: linear-gradient(90deg, #2196F3, #03A9F4);
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
            
            /* 强制重启按钮特殊样式 */
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
                background: #dc3545;
                color: white;
            }
            
            .reboot-cancel {
                background: #6c757d;
                color: white;
            }
        </style>
    </head>
    <body>
        <div class="container">
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
                </div>
            </div>
            
            <div class="header">
                <h1>🖥️ Windows系统远程开机系统   byB站剠歼刭</h1>
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
            
            <!-- 添加强制重启按钮 (放在重启按钮后面) -->
            <button class="btn" onclick="forceRebootVM()" id="forceRebootBtn" style="background: linear-gradient(135deg, #fd7e14, #dc3545); margin-bottom: 10px;">
                ⚡ 强制重启系统
            </button>
            
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>正在检测虚拟机状态并启动，请稍候...</p>
            </div>
            
            <div id="statusMessage"></div>
            
            <!-- VNC控制区域 -->
            <div class="vnc-control">
                <h3>🌐 Windows系统远程连接</h3>
                
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
                        <span id="forceRebootStatus" style="color: #dc3545; display: none;">(强制重启中)</span>
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
            
            <div class="performance-info">
                <h3>
                    系统性能监控
                    <span id="performanceTimestamp" style="font-size: 12px; font-weight: normal;">更新中...</span>
                </h3>
                <div class="performance-grid">
                    <div class="performance-item">
                        <div class="performance-label">CPU使用率</div>
                        <div class="performance-value" id="cpuPercent">0%</div>
                        <div class="progress-bar">
                            <div class="progress progress-cpu" id="cpuProgress" style="width: 0%"></div>
                        </div>
                    </div>
                    <div class="performance-item">
                        <div class="performance-label">内存使用</div>
                        <div class="performance-value" id="memoryUsage">0 GB / 0 GB (0%)</div>
                        <div class="progress-bar">
                            <div class="progress progress-memory" id="memoryProgress" style="width: 0%"></div>
                        </div>
                    </div>
                    <div class="performance-item">
                        <div class="performance-label">网络流量</div>
                        <div class="performance-value" id="networkUsage">上传: 0 MB | 下载: 0 MB</div>
                    </div>
                </div>
                <div class="timestamp">
                    系统启动时间: <span id="bootTime">未知</span>
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

        <!-- 强制重启确认对话框 -->
        <div class="modal" id="forceRebootModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">⚠️ 强制重启警告</div>
                    <button class="close-btn" onclick="hideForceRebootModal()">×</button>
                </div>
                <div class="modal-body">
                    <p><strong>警告：强制重启可能导致数据丢失！</strong></p>
                    <p>此操作将立即强制关闭虚拟机电源，然后重新启动。</p>
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
                        强制重启
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
            
            // 监听强制重启完成事件
            socket.on('vm_force_reboot_complete', function(data) {
                document.getElementById('forceRebootStatus').style.display = 'none';
                document.getElementById('normalRebootStatus').textContent = data.success ? '正常' : '错误';
                
                if (data.success) {
                    showMessage('强制重启已完成！', 'success');
                } else {
                    showMessage('强制重启失败: ' + data.message, 'error');
                }
            });
            
            // 监听强制重启被拒绝事件
            socket.on('vm_force_reboot_rejected', function(data) {
                showMessage('强制重启请求被拒绝: ' + data.message, 'error');
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
                        alert('反馈提交成功！');
                        document.getElementById('feedbackContent').value = '';
                        hideFeedbackModal();
                    } else {
                        alert('提交失败：' + data.message);
                    }
                } catch (error) {
                    console.error('提交反馈失败:', error);
                    alert('网络错误，请稍后重试');
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
                        data.feedbacks.forEach(feedback => {
                            const feedbackItem = document.createElement('div');
                            feedbackItem.className = 'feedback-item';
                            
                            let repliesHtml = '';
                            if (feedback.replies && feedback.replies.length > 0) {
                                feedback.replies.forEach(reply => {
                                    repliesHtml += `
                                        <div class="reply-item">
                                            <div class="feedback-header">
                                                <span class="feedback-author">${reply.author || '管理员'}</span>
                                                <span class="feedback-time">${formatTime(reply.timestamp)}</span>
                                            </div>
                                            <div class="feedback-content">${reply.content}</div>
                                        </div>
                                    `;
                                });
                            }
                            
                            feedbackItem.innerHTML = `
                                <div class="feedback-header">
                                    <span class="feedback-author">${feedback.author || '用户'}</span>
                                    <span class="feedback-time">${formatTime(feedback.timestamp)}</span>
                                </div>
                                <div class="feedback-content">${feedback.content}</div>
                                <div class="reply-section">
                                    <button class="reply-btn" onclick="toggleReplyForm('${feedback.id}')">回复</button>
                                    <div class="reply-form" id="replyForm-${feedback.id}">
                                        <textarea id="replyContent-${feedback.id}" placeholder="请输入回复内容..."></textarea>
                                        <button class="reply-btn" onclick="submitReply('${feedback.id}')">提交回复</button>
                                    </div>
                                    <div class="replies">
                                        ${repliesHtml}
                                    </div>
                                </div>
                            `;
                            
                            feedbackList.appendChild(feedbackItem);
                        });
                    } else {
                        feedbackList.innerHTML = '<p style="text-align: center; color: #666;">暂无反馈</p>';
                    }
                } catch (error) {
                    console.error('加载反馈列表失败:', error);
                    document.getElementById('feedbackList').innerHTML = '<p style="text-align: center; color: #666;">加载失败</p>';
                }
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
                        },
                        body: JSON.stringify({
                            feedback_id: feedbackId,
                            content: content
                        })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        alert('回复成功！');
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
            
            // 更新性能数据
            async function updatePerformance() {
                try {
                    const response = await fetch('/api/performance');
                    const data = await response.json();
                    
                    // 更新CPU使用率
                    document.getElementById('cpuPercent').textContent = data.cpu_percent + '%';
                    document.getElementById('cpuProgress').style.width = data.cpu_percent + '%';
                    
                    // 更新内存使用情况
                    document.getElementById('memoryUsage').textContent = 
                        data.memory_used_gb + ' GB / ' + data.memory_total_gb + ' GB (' + data.memory_percent + '%)';
                    document.getElementById('memoryProgress').style.width = data.memory_percent + '%';
                    
                    // 更新网络使用情况
                    document.getElementById('networkUsage').textContent = 
                        '上传: ' + data.net_sent_mb + ' MB | 下载: ' + data.net_recv_mb + ' MB';
                    
                    // 更新系统启动时间
                    document.getElementById('bootTime').textContent = data.boot_time;
                    
                    // 更新时间戳
                    document.getElementById('performanceTimestamp').textContent = '更新时间: ' + data.timestamp;
                    
                } catch (error) {
                    console.error('获取性能数据失败:', error);
                    document.getElementById('performanceTimestamp').textContent = '更新失败';
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
                window.open('https://776b2585.r10.cpolar.top/vnc.html', '_blank');
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
            
            // 定期更新性能数据（更频繁）
            setInterval(updatePerformance, 2000);
            updatePerformance(); // 初始更新
            
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
            
            // 强制重启功能
            function forceRebootVM() {
                // 显示确认对话框
                document.getElementById('forceRebootModal').classList.add('show');
            }
            
            function hideForceRebootModal() {
                document.getElementById('forceRebootModal').classList.remove('show');
            }
            
            function confirmForceReboot() {
                hideForceRebootModal();
                
                const btn = document.getElementById('forceRebootBtn');
                const originalText = btn.textContent;
                btn.disabled = true;
                btn.textContent = '提交请求中...';
                btn.style.background = 'linear-gradient(135deg, #6c757d, #5a6268)';
                
                // 发送强制重启请求
                fetch('/api/force-reboot-vm', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.status === 'pending_confirmation') {
                        const confirmId = data.confirm_id;
                        showMessage('强制重启请求已提交，请在3分钟内通过管理页面确认...', 'info');
                        
                        // 开始轮询确认状态
                        pollConfirmationStatus(confirmId, btn, originalText);
                        
                    } else {
                        showMessage('请求失败: ' + (data.message || '未知错误'), 'error');
                        resetForceRebootBtn(btn, originalText);
                    }
                })
                .catch(error => {
                    console.error('强制重启请求失败:', error);
                    showMessage('网络错误: ' + error.message, 'error');
                    resetForceRebootBtn(btn, originalText);
                });
            }
            
            function pollConfirmationStatus(confirmId, btn, originalText) {
                let pollCount = 0;
                const maxPolls = 200; // 3分20秒
                
                const pollInterval = setInterval(() => {
                    pollCount++;
                    
                    // 使用正确的API端点
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
                                    // 管理员允许或超时自动允许
                                    btn.textContent = '强制重启执行中...';
                                    showMessage('正在强制重启系统...', 'success');
                                    
                                    // 显示倒计时
                                    let countdown = 120;
                                    const countdownInterval = setInterval(() => {
                                        if (countdown <= 0) {
                                            clearInterval(countdownInterval);
                                            resetForceRebootBtn(btn, originalText);
                                            showMessage('强制重启预计已完成', 'info');
                                        } else {
                                            btn.textContent = `重启中 (${Math.floor(countdown/60)}:${String(countdown%60).padStart(2, '0')})`;
                                            countdown--;
                                        }
                                    }, 1000);
                                } else {
                                    // 被拒绝
                                    showMessage('强制重启请求被拒绝', 'error');
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
                                    showMessage(`请管理员访问 http://${window.location.hostname}:5000/admin/force-reboot-confirm 进行确认`, 'info');
                                }
                            }
                        })
                        .catch(error => {
                            console.error('轮询状态失败:', error);
                        });
                    
                    if (pollCount > maxPolls) {
                        clearInterval(pollInterval);
                        showMessage('确认请求超时', 'error');
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
    """强制重启虚拟机API接口"""
    try:
        client_ip = request.remote_addr
        logger.warning(f"收到强制重启请求来自: {client_ip}")
        
        # 检查是否已经在操作中
        if vm_status.get('is_rebooting', False):
            return jsonify({
                'success': False,
                'message': '系统正在重启中，请稍后再试'
            }), 429
        
        # 生成确认ID
        confirm_id = str(uuid.uuid4())
        
        # 记录请求
        force_reboot_requests[confirm_id] = {
            'client_ip': client_ip,
            'request_time': datetime.now(),
            'confirmed': False,
            'timeout': False,
            'approved': False,
            'response': 'pending'
        }
        
        # 强制刷新控制台显示新请求
        force_refresh_console()
        
        # 显示详细提示
        print("\n" + "!" * 80)
        print(" " * 25 + "🚨 新强制重启请求")
        print("!" * 80)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"客户端IP: {client_ip}")
        print(f"虚拟机: {vm_status['vm_name']}")
        print(f"确认ID: {confirm_id}")
        print("-" * 80)
        print("请在3分钟内通过以下方式操作：")
        print(f"  管理页面: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
        print("!" * 80)
        
        # 启动后台计时线程
        def timeout_thread(confirm_id, client_ip):
            try:
                # 等待3分钟
                time.sleep(CONFIRM_TIMEOUT)
                
                # 检查是否已处理
                if confirm_id in force_reboot_requests and not force_reboot_requests[confirm_id]['confirmed']:
                    # 超时自动允许
                    force_reboot_requests[confirm_id].update({
                        'confirmed': True,
                        'timeout': True,
                        'approved': True,
                        'confirm_time': datetime.now(),
                        'response': 'timeout_auto_approved'
                    })
                    
                    # 刷新控制台显示状态变化
                    force_refresh_console()
                    
                    print(f"\n⏰ 确认ID {confirm_id[:8]}... 超时未确认，自动允许强制重启")
                    
                    # 执行强制重启
                    execute_force_reboot(confirm_id, client_ip, True)
                    
            except Exception as e:
                logger.error(f"超时线程错误: {str(e)}")
        
        # 启动超时线程
        thread = threading.Thread(target=timeout_thread, args=(confirm_id, client_ip), daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'message': '强制重启请求已提交，请在3分钟内通过管理页面确认...',
            'confirm_id': confirm_id,
            'status': 'pending_confirmation',
            'admin_url': f'http://{LOCAL_IP}:5000/admin/force-reboot-confirm',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"强制重启API错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

@app.route('/admin/force-reboot-confirm', methods=['GET', 'POST'])
def force_reboot_confirm_page():
    """强制重启确认页面"""
    
    if request.method == 'POST':
        confirm_id = request.form.get('confirm_id', '').strip()
        action = request.form.get('action', '')
        
        if confirm_id in force_reboot_requests and not force_reboot_requests[confirm_id]['confirmed']:
            current_time = datetime.now()
            
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
                
                message = f"✅ 已允许强制重启 (确认ID: {confirm_id[:8]}...)"
                
            elif action == 'reject':
                # 管理员拒绝
                force_reboot_requests[confirm_id].update({
                    'confirmed': True,
                    'approved': False,
                    'confirm_time': current_time,
                    'response': 'admin_rejected'
                })
                
                # 刷新控制台
                force_refresh_console()
                
                # 通知前端
                socketio.emit('vm_force_reboot_rejected', {
                    'confirm_id': confirm_id,
                    'message': '管理员拒绝了强制重启请求',
                    'timestamp': current_time.isoformat()
                })
                
                message = f"❌ 已拒绝强制重启 (确认ID: {confirm_id[:8]}...)"
            
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
                'client_ip': info['client_ip'],
                'request_time': info['request_time'].strftime('%H:%M:%S'),
                'elapsed_seconds': elapsed,
                'remaining_seconds': remaining,
                'remaining_formatted': f"{remaining//60}:{remaining%60:02d}"
            })
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head><title>强制重启确认</title>
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
            <h1>⚡ 强制重启确认</h1>
            <p>服务器: {LOCAL_IP} | 当前时间: {datetime.now().strftime("%H:%M:%S")}</p>
            
            <div class="manual-input">
                <h3>手动输入确认ID</h3>
                <form method="post" style="margin: 10px 0;">
                    <input type="text" name="confirm_id" placeholder="输入确认ID" required>
                    <button type="submit" name="action" value="approve" class="approve">允许</button>
                    <button type="submit" name="action" value="reject" class="reject">拒绝</button>
                </form>
            </div>
            
            <h2>待处理请求 ({len(pending_requests)})</h2>
            
            {f'''
            {'<div class="empty">暂无待处理请求</div>' if not pending_requests else ''}
            
            {''.join([f'''
            <div class="request">
                <h3>请求 #{i+1}</h3>
                <p><strong>确认ID:</strong> {req['confirm_id']}</p>
                <p><strong>客户端IP:</strong> {req['client_ip']}</p>
                <p><strong>请求时间:</strong> {req['request_time']}</p>
                <p><strong>剩余时间:</strong> <span class="timer">{req['remaining_formatted']}</span></p>
                <div class="buttons">
                    <form method="post" style="display: inline;">
                        <input type="hidden" name="confirm_id" value="{req['confirm_id']}">
                        <button type="submit" name="action" value="approve" class="approve">✅ 允许重启</button>
                        <button type="submit" name="action" value="reject" class="reject">❌ 拒绝重启</button>
                    </form>
                </div>
            </div>
            ''' for i, req in enumerate(pending_requests)])}
            '''}
            
            <hr>
            <p style="color: #666; font-size: 12px;">
                注意：强制重启可能导致数据丢失，请谨慎操作。<br>
                页面每10秒自动刷新，剩余时间不足时会自动允许重启。
            </p>
        </div>
    </body>
    </html>'''

@app.route('/api/force-reboot/status/<confirm_id>', methods=['GET'])
def get_force_reboot_status(confirm_id):
    """获取强制重启确认状态"""
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
            'remaining_seconds': remaining
        })
    else:
        return jsonify({
            'found': False,
            'message': '确认ID不存在或已过期'
        })

def execute_force_reboot(confirm_id, client_ip, approved):
    """执行强制重启"""
    if not approved:
        return
    
    # 更新状态
    vm_status['is_rebooting'] = True
    vm_status['last_error'] = None
    
    def run_force_reboot():
        try:
            # 这里调用你的强制重启函数
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
            
            logger.info(f"强制重启任务完成: {message}")
            
        except Exception as e:
            vm_status['is_rebooting'] = False
            vm_status['last_error'] = str(e)
            logger.error(f"强制重启后台任务错误: {str(e)}")
            
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

@app.route('/api/performance', methods=['GET'])
def get_performance():
    """获取系统性能数据"""
    performance_data = get_system_performance()
    return jsonify(performance_data)

# 新增：获取页面访问统计API
@app.route('/api/page/stats', methods=['GET'])
def get_page_stats():
    """获取页面访问统计"""
    return jsonify({
        'current': page_user_count,
        'max': MAX_PAGE_USERS,
        'is_full': page_user_count >= MAX_PAGE_USERS,
        'connected_users': len(page_connected_users)
    })

# 新增：获取VNC连接统计API
@app.route('/api/vnc/stats', methods=['GET'])
def get_vnc_stats():
    """获取VNC连接统计"""
    return jsonify(vnc_proxy.get_connection_stats())

@app.route('/api/feedback', methods=['GET'])
def get_feedback():
    """获取所有反馈"""
    feedback_data = load_feedback_data()
    return jsonify(feedback_data)

@app.route('/api/feedback', methods=['POST'])
def submit_feedback():
    """提交反馈"""
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        
        if not content:
            return jsonify({'success': False, 'message': '反馈内容不能为空'})
        
        feedback_data = load_feedback_data()
        
        feedback = {
            'id': str(uuid.uuid4()),
            'content': content,
            'author': '用户',  # 可以扩展为登录用户
            'timestamp': datetime.now().isoformat(),
            'replies': []
        }
        
        feedback_data['feedbacks'].append(feedback)
        
        if save_feedback_data(feedback_data):
            return jsonify({'success': True, 'message': '反馈提交成功'})
        else:
            return jsonify({'success': False, 'message': '保存反馈失败'})
            
    except Exception as e:
        logger.error(f"提交反馈失败: {e}")
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'})

@app.route('/api/feedback/reply', methods=['POST'])
def submit_reply():
    """回复反馈"""
    try:
        data = request.get_json()
        feedback_id = data.get('feedback_id')
        content = data.get('content', '').strip()
        
        if not feedback_id or not content:
            return jsonify({'success': False, 'message': '反馈ID和回复内容不能为空'})
        
        feedback_data = load_feedback_data()
        
        # 查找对应的反馈
        for feedback in feedback_data['feedbacks']:
            if feedback['id'] == feedback_id:
                reply = {
                    'id': str(uuid.uuid4()),
                    'content': content,
                    'author': '管理员',  # 可以扩展为登录用户
                    'timestamp': datetime.now().isoformat()
                }
                feedback['replies'].append(reply)
                break
        
        if save_feedback_data(feedback_data):
            return jsonify({'success': True, 'message': '回复成功'})
        else:
            return jsonify({'success': False, 'message': '保存回复失败'})
            
    except Exception as e:
        logger.error(f"提交回复失败: {e}")
        return jsonify({'success': False, 'message': f'服务器错误: {str(e)}'})

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

if __name__ == '__main__':
    # 清屏并显示启动信息
    clear_console()
    
    print("=" * 80)
    print(" " * 30 + "🖥️  虚拟机远程控制系统  byB站剠歼刭")
    print("=" * 80)
    print(f"虚拟机名称: {vm_status['vm_name']}")
    print(f"配置文件: {VMX_PATH}")
    print(f"vmrun路径: {VMRUN_PATH}")
    print(f"VMware路径: {VMWARE_EXE_PATH}")
    print(f"VNC服务器: {VNC_HOST}:{VNC_PORT}")
    print(f"公网VNC地址: http://3e66e9dc.r18.vip.cpolar.cn/vnc.html")
    print(f"本地访问地址: http://127.0.0.1:5000")
    print(f"网络访问地址: http://{LOCAL_IP}:5000")
    print(f"强制重启管理: http://{LOCAL_IP}:5000/admin/force-reboot-confirm")
    print("请确保防火墙已放行5000端口")
    print("=" * 80)
    
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
    
    print("=" * 80)
    print("启动控制台自动刷新...")
    
    # 启动控制台自动刷新
    start_console_refresh()
    
    # 等待2秒让控制台刷新显示
    time.sleep(2)
    
    # 启动服务器
    try:
        print("\n启动SocketIO服务器...")
        print("按 Ctrl+C 停止程序")
        print("-" * 80)
        
        socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n正在停止系统...")
        stop_console_refresh()
        print("系统已停止")
    except Exception as e:
        print(f"启动SocketIO服务器失败: {e}")
        print("尝试使用Flask开发服务器")
        stop_console_refresh()
        app.run(host='0.0.0.0', port=5000, debug=False)