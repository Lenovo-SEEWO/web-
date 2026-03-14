from flask import Flask, request, jsonify
import subprocess
import logging
import threading
from datetime import datetime
import os
import socket
import time
import psutil
import json
import uuid

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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# VMware配置
VMRUN_PATH = r"C:\MV\vmrun.exe"
VMWARE_EXE_PATH = r"C:\MV\vmware.exe"
VMX_PATH = r"E:\Hypv\战神CF极致高帧版（W10）.vmx"

# 虚拟机状态跟踪
vm_status = {
    'last_start_time': None,
    'is_running': False,
    'last_error': None,
    'vm_name': '战神CF极致高帧版（W10）',
    'vmware_opened': False
}

# 反馈数据存储
FEEDBACK_FILE = "feedback_data.json"

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
            .progress-disk {
                background: linear-gradient(90deg, #FF9800, #FFC107);
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
        </style>
    </head>
    <body>
        <div class="container">
            <!-- 菜单按钮 -->
            <div class="menu-container">
                <button class="menu-btn" id="menuBtn">☰</button>
                <div class="dropdown-menu" id="dropdownMenu">
                    <a class="menu-item" href="#" onclick="showFeedbackModal()">反馈/建议</a>
                    <a class="menu-item" href="#" onclick="showFeedbackList()">我的反馈/建议</a>
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
                    <span class="status-value">''' + LOCAL_IP + '''</span>
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

        <script>
            const startBtn = document.getElementById('startBtn');
            const loading = document.getElementById('loading');
            const statusMessage = document.getElementById('statusMessage');
            const menuBtn = document.getElementById('menuBtn');
            const dropdownMenu = document.getElementById('dropdownMenu');
            const feedbackModal = document.getElementById('feedbackModal');
            const feedbackListModal = document.getElementById('feedbackListModal');
            
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
                    
                } catch (error) {
                    console.error('获取性能数据失败:', error);
                    document.getElementById('performanceTimestamp').textContent = '更新失败';
                }
            }
            
            // 定期更新状态
            setInterval(updateStatus, 3000);
            updateStatus(); // 初始更新
            
            // 定期更新性能数据（更频繁）
            setInterval(updatePerformance, 2000);
            updatePerformance(); // 初始更新
            
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

if __name__ == '__main__':
    print("=" * 50)
    print("虚拟机远程控制系统 - 完整版（含反馈系统）")
    print("=" * 50)
    print(f"虚拟机名称: {vm_status['vm_name']}")
    print(f"配置文件: {VMX_PATH}")
    print(f"vmrun路径: {VMRUN_PATH}")
    print(f"VMware路径: {VMWARE_EXE_PATH}")
    print(f"本地访问地址: http://127.0.0.1:5000")
    print(f"网络访问地址: http://{LOCAL_IP}:5000")
    print("请确保防火墙已放行5000端口")
    print("=" * 50)
    
    # 检查依赖
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
    
    # 启动服务器
    try:
        from waitress import serve
        print("使用Waitress生产服务器...")
        serve(app, host='0.0.0.0', port=5000, threads=4)
    except ImportError:
        print("使用Flask开发服务器")
        app.run(host='0.0.0.0', port=5000, debug=False)