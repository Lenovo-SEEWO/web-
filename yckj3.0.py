from flask import Flask, request, jsonify
import subprocess
import logging
import threading
from datetime import datetime
import os
import socket
import time
import psutil  # 新增：用于系统性能监控

app = Flask(__name__)

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# VMware配置
VMRUN_PATH = r"C:\MV\vmrun.exe"
VMWARE_EXE_PATH = r"C:\MV\vmware.exe"  # VMware图形界面路径
VMX_PATH = r"E:\Hypv\战神CF极致高帧版（W10）.vmx"

# 虚拟机状态跟踪
vm_status = {
    'last_start_time': None,
    'is_running': False,
    'last_error': None,
    'vm_name': '战神CF极致高帧版（W10）',
    'vmware_opened': False  # VMware图形界面是否已打开
}

def check_vm_status():
    """
    检查虚拟机状态
    返回: (是否运行, 错误信息)
    """
    try:
        # 使用vmrun list命令列出所有正在运行的虚拟机
        cmd = [VMRUN_PATH, 'list']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=30)
        
        if result.returncode == 0:
            # 检查虚拟机配置文件路径是否在运行列表中
            if VMX_PATH in result.stdout:
                logger.info(f"虚拟机正在运行: {VMX_PATH}")
                return True, None
            else:
                logger.info(f"虚拟机未运行: {VMX_PATH}")
                return False, None
        else:
            error_msg = f"检查虚拟机状态失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = "检查虚拟机状态超时"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"检查虚拟机状态异常: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def start_virtual_machine():
    """
    启动虚拟机
    返回: (是否成功, 消息)
    """
    try:
        logger.info(f"开始启动虚拟机: {VMX_PATH}")
        
        # 使用vmrun start命令启动虚拟机
        cmd = [VMRUN_PATH, 'start', VMX_PATH, 'nogui']
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=120)
        
        if result.returncode == 0:
            logger.info(f"虚拟机启动成功: {result.stdout}")
            
            # 虚拟机启动成功后，打开VMware图形界面
            try:
                if os.path.exists(VMWARE_EXE_PATH):
                    logger.info(f"正在自动打开VMware图形界面: {VMWARE_EXE_PATH}")
                    # 使用Popen而不是run，这样不会阻塞主线程
                    subprocess.Popen([VMWARE_EXE_PATH], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    vm_status['vmware_opened'] = True
                    logger.info("VMware图形界面已自动打开")
                    return True, "虚拟机启动成功并已自动打开VMware图形界面"
                else:
                    logger.warning(f"VMware图形界面程序不存在: {VMWARE_EXE_PATH}")
                    return True, "虚拟机启动成功，但未找到VMware图形界面程序"
            except Exception as e:
                logger.error(f"打开VMware图形界面失败: {str(e)}")
                return True, "虚拟机启动成功，但打开VMware图形界面失败"
        else:
            error_msg = f"启动失败: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = "虚拟机启动超时"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"启动过程中发生错误: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

def get_system_performance():
    """
    获取系统性能数据
    返回: 包含CPU、内存、磁盘等性能数据的字典
    """
    try:
        # CPU使用率
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # 内存使用情况
        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024**3), 1)
        memory_used_gb = round(memory.used / (1024**3), 1)
        memory_percent = memory.percent
        
        # 磁盘使用情况（获取C盘）
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 1)
        disk_used_gb = round(disk.used / (1024**3), 1)
        disk_percent = disk.percent
        
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
            'disk_total_gb': disk_total_gb,
            'disk_used_gb': disk_used_gb,
            'disk_percent': disk_percent,
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
            'disk_total_gb': 0,
            'disk_used_gb': 0,
            'disk_percent': 0,
            'net_sent_mb': 0,
            'net_recv_mb': 0,
            'boot_time': '未知',
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'error': str(e)
        }

# HTML页面内容
HTML_PAGE = f'''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>虚拟机远程控制系统</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .container {{
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 600px;
            width: 100%;
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
        }}
        .header h1 {{
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }}
        .header p {{
            color: #666;
            font-size: 16px;
        }}
        .btn {{
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
        }}
        .btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 10px 20px rgba(102, 126, 234, 0.3);
        }}
        .btn:disabled {{
            background: #ccc;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
        }}
        .status {{
            margin-top: 25px;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            font-weight: bold;
        }}
        .status.success {{
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }}
        .status.error {{
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }}
        .status.info {{
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }}
        .loading {{
            display: none;
            text-align: center;
            margin: 20px 0;
        }}
        .spinner {{
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .status-info {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            font-size: 14px;
        }}
        .status-item {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
        }}
        .status-label {{
            color: #666;
        }}
        .status-value {{
            font-weight: bold;
            color: #333;
        }}
        .vm-info {{
            background: #e9ecef;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .vm-info h3 {{
            margin-top: 0;
            color: #495057;
        }}
        .feature-note {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 20px;
            font-size: 14px;
            color: #856404;
        }}
        .performance-info {{
            background: #e8f4fd;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            font-size: 14px;
        }}
        .performance-info h3 {{
            margin-top: 0;
            color: #0c5460;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .progress-bar {{
            height: 10px;
            background-color: #e9ecef;
            border-radius: 5px;
            margin-top: 5px;
            overflow: hidden;
        }}
        .progress {{
            height: 100%;
            border-radius: 5px;
            transition: width 0.3s ease;
        }}
        .progress-cpu {{
            background: linear-gradient(90deg, #4CAF50, #8BC34A);
        }}
        .progress-memory {{
            background: linear-gradient(90deg, #2196F3, #03A9F4);
        }}
        .progress-disk {{
            background: linear-gradient(90deg, #FF9800, #FFC107);
        }}
        .performance-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-top: 10px;
        }}
        .performance-item {{
            margin-bottom: 10px;
        }}
        .performance-label {{
            font-weight: bold;
            color: #495057;
            margin-bottom: 5px;
        }}
        .performance-value {{
            color: #212529;
        }}
        .timestamp {{
            font-size: 12px;
            color: #6c757d;
            text-align: right;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ 虚拟机远程控制系统</h1>
            <p>安全、便捷地远程启动虚拟机</p>
        </div>
        
        <div class="feature-note">
            <strong>功能说明：</strong> 启动虚拟机后将自动打开VMware图形界面
        </div>
        
        <div class="vm-info">
            <h3>虚拟机信息</h3>
            <div class="status-item">
                <span class="status-label">虚拟机名称:</span>
                <span class="status-value">战神CF极致高帧版（W10）</span>
            </div>
            <div class="status-item">
                <span class="status-label">配置文件:</span>
                <span class="status-value">E:\\Hypv\\战神CF极致高帧版（W10）.vmx</span>
            </div>
        </div>
        
        <button class="btn" id="startBtn">
            启动虚拟机
        </button>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>正在检测虚拟机状态并启动，请稍候...</p>
        </div>
        
        <div id="statusMessage"></div>
        
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
                <span class="status-label">服务器IP:</span>
                <span class="status-value">{LOCAL_IP}</span>
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
                    <div class="performance-label">磁盘使用 (C:)</div>
                    <div class="performance-value" id="diskUsage">0 GB / 0 GB (0%)</div>
                    <div class="progress-bar">
                        <div class="progress progress-disk" id="diskProgress" style="width: 0%"></div>
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

    <script>
        const startBtn = document.getElementById('startBtn');
        const loading = document.getElementById('loading');
        const statusMessage = document.getElementById('statusMessage');
        
        // 更新状态显示
        async function updateStatus() {{
            try {{
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
                
            }} catch (error) {{
                console.error('获取状态失败:', error);
                document.getElementById('statusRunning').textContent = '连接失败';
                document.getElementById('statusRunning').style.color = '#dc3545';
            }}
        }}
        
        // 更新性能数据
        async function updatePerformance() {{
            try {{
                const response = await fetch('/api/performance');
                const data = await response.json();
                
                // 更新CPU使用率
                document.getElementById('cpuPercent').textContent = data.cpu_percent + '%';
                document.getElementById('cpuProgress').style.width = data.cpu_percent + '%';
                
                // 更新内存使用情况
                document.getElementById('memoryUsage').textContent = 
                    data.memory_used_gb + ' GB / ' + data.memory_total_gb + ' GB (' + data.memory_percent + '%)';
                document.getElementById('memoryProgress').style.width = data.memory_percent + '%';
                
                // 更新磁盘使用情况
                document.getElementById('diskUsage').textContent = 
                    data.disk_used_gb + ' GB / ' + data.disk_total_gb + ' GB (' + data.disk_percent + '%)';
                document.getElementById('diskProgress').style.width = data.disk_percent + '%';
                
                // 更新网络使用情况
                document.getElementById('networkUsage').textContent = 
                    '上传: ' + data.net_sent_mb + ' MB | 下载: ' + data.net_recv_mb + ' MB';
                
                // 更新系统启动时间
                document.getElementById('bootTime').textContent = data.boot_time;
                
                // 更新时间戳
                document.getElementById('performanceTimestamp').textContent = '更新时间: ' + data.timestamp;
                
            }} catch (error) {{
                console.error('获取性能数据失败:', error);
                document.getElementById('performanceTimestamp').textContent = '更新失败';
            }}
        }}
        
        // 定期更新状态
        setInterval(updateStatus, 3000);
        updateStatus(); // 初始更新
        
        // 定期更新性能数据（更频繁）
        setInterval(updatePerformance, 2000);
        updatePerformance(); // 初始更新
        
        startBtn.addEventListener('click', async () => {{
            // 显示加载中
            loading.style.display = 'block';
            startBtn.disabled = true;
            statusMessage.innerHTML = '';
            
            try {{
                const response = await fetch('/api/start-vm', {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }}
                }});
                
                const data = await response.json();
                
                if (data.success) {{
                    showMessage(data.message, 'success');
                }} else {{
                    showMessage(data.message, 'error');
                }}
                
            }} catch (error) {{
                console.error('请求失败:', error);
                showMessage('网络请求失败，请检查服务器状态', 'error');
            }} finally {{
                loading.style.display = 'none';
                // 状态会在下次更新时自动启用按钮
            }}
        }});
        
        function showMessage(message, type) {{
            statusMessage.innerHTML = `
                <div class="status ${{type}}">
                    ${{message}}
                </div>
            `;
        }}
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """提供主页"""
    return HTML_PAGE

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

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取虚拟机状态"""
    # 实时检查虚拟机状态
    is_running, error = check_vm_status()
    if error:
        logger.error(f"状态检查失败: {error}")
    
    return jsonify({
        'is_running': is_running,
        'last_start_time': vm_status['last_start_time'],
        'last_error': vm_status['last_error'],
        'vmware_opened': vm_status['vmware_opened'],
        'server_ip': LOCAL_IP
    })

@app.route('/api/performance', methods=['GET'])
def get_performance():
    """获取系统性能数据"""
    performance_data = get_system_performance()
    return jsonify(performance_data)

@app.route('/api/info', methods=['GET'])
def get_info():
    """获取服务器信息"""
    return jsonify({
        'server_ip': LOCAL_IP,
        'access_url': f'http://{LOCAL_IP}:5000',
        'status': 'running',
        'vm_name': vm_status['vm_name'],
        'vmx_path': VMX_PATH
    })

if __name__ == '__main__':
    print("=" * 50)
    print("VMware虚拟机远程控制系统")
    print("=" * 50)
    print(f"虚拟机名称: {vm_status['vm_name']}")
    print(f"配置文件: {VMX_PATH}")
    print(f"vmrun路径: {VMRUN_PATH}")
    print(f"VMware路径: {VMWARE_EXE_PATH}")
    print(f"本地访问地址: http://127.0.0.1:5000")
    print(f"网络访问地址: http://{LOCAL_IP}:5000")
    print("请确保防火墙已放行5000端口")
    print("=" * 50)
    
    # 检查psutil是否安装
    try:
        import psutil
        print("✓ psutil库已安装，性能监控功能可用")
    except ImportError:
        print("✗ psutil库未安装，性能监控功能将不可用")
        print("请运行: pip install psutil")
    
    # 检查vmrun.exe是否存在
    if not os.path.exists(VMRUN_PATH):
        print(f"错误: vmrun.exe不存在于 {VMRUN_PATH}")
        print("请检查路径是否正确")
        exit(1)
    
    # 检查虚拟机配置文件是否存在
    if not os.path.exists(VMX_PATH):
        print(f"警告: 虚拟机配置文件不存在于 {VMX_PATH}")
        print("启动虚拟机时可能会失败")
    
    # 检查VMware图形界面程序是否存在
    if not os.path.exists(VMWARE_EXE_PATH):
        print(f"警告: VMware图形界面程序不存在于 {VMWARE_EXE_PATH}")
        print("自动打开VMware图形界面功能将不可用")
    
    try:
        app.run(
            host='0.0.0.0',
            port=5000,
            debug=False,
            threaded=True
        )
    except Exception as e:
        print(f"启动失败: {e}")
        print("可能的原因:")
        print("1. 端口5000已被其他程序占用")
        print("2. 没有管理员权限")
        print("3. 防火墙阻止")