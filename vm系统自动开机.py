import subprocess
import time
import os
import psutil
import signal
import logging

# ====== 配置区域 ======
VMX_FILE_PATH = r"E:\Hypv\战神CF极致高帧版（W10）.vmx"
VMRUN_PATH = r"C:\MV\vmrun.exe"
VMWARE_PROCESS_NAMES = ["vmware.exe", "vmware-vmx.exe"]
CHECK_INTERVAL = 15
SHUTDOWN_CONFIRM_DELAY = 5
AUTO_START_ON_INIT = True  # 新增：脚本启动时如果虚拟机已关机，是否自动启动
# =====================

# 设置日志（移除了文件日志，只保留控制台输出）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # 只保留控制台输出，移除FileHandler
    ]
)
logger = logging.getLogger(__name__)

# 状态映射字典
STATUS_MAP = {
    "running": "Windows虚拟机系统正在运行中",
    "off": "Windows虚拟机系统已关机",
    "unknown": "未知状态",
    "error": "错误状态"
}

# 全局标志，用于控制监控循环
monitoring_active = True

def run_command_with_timeout(cmd, timeout=10):
    """带超时的命令执行函数"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            encoding='utf-8',
            errors='ignore'
        )
        return result
    except subprocess.TimeoutExpired:
        logger.warning(f"命令执行超时: {' '.join(cmd)}")
        return None
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        return None

def get_vm_power_state(vmx_path):
    """使用vmrun list命令检查虚拟机状态"""
    result = run_command_with_timeout([VMRUN_PATH, "list"], timeout=10)
    
    if result is None:
        logger.error("vmrun list命令执行失败")
        return "error"
    
    if result.returncode != 0:
        logger.error(f"vmrun list命令返回错误: {result.stderr}")
        return "error"
    
    # 检查我们的虚拟机是否在运行列表中
    vm_path_lower = vmx_path.lower()
    output_lower = result.stdout.lower() if result.stdout else ""
    
    if vm_path_lower in output_lower:
        return "running"
    else:
        return "off"

def is_vm_running_by_process(vmx_path):
    """通过进程检测虚拟机状态（备用方法）"""
    try:
        vm_name = os.path.basename(vmx_path)
        
        for proc in psutil.process_iter(['name', 'cmdline']):
            try:
                if proc.info['name'] and any(name in proc.info['name'].lower() for name in ['vmware', 'vmplayer']):
                    if proc.info['cmdline']:
                        cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                        if vmx_path.lower() in cmdline or vm_name.lower() in cmdline:
                            return "running"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return "off"
    except Exception as e:
        logger.error(f"进程检测失败: {e}")
        return "unknown"

def get_vm_power_state_combined(vmx_path):
    """综合使用vmrun和进程检测"""
    vmrun_result = get_vm_power_state(vmx_path)
    
    chinese_status = STATUS_MAP.get(vmrun_result, vmrun_result)
    logger.info(f"vmrun检测结果: {chinese_status}")
    
    if vmrun_result == "error":
        process_result = is_vm_running_by_process(vmx_path)
        chinese_process_status = STATUS_MAP.get(process_result, process_result)
        logger.info(f"进程检测结果: {chinese_process_status}")
        return process_result
    
    return vmrun_result

def stop_vmware_process(process_names):
    """终止VMware主进程"""
    killed_processes = []
    
    for proc in psutil.process_iter():
        try:
            if proc.name() in process_names:
                logger.info(f"尝试终止进程: {proc.name()} (PID: {proc.pid})")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                    logger.info(f"已终止进程: {proc.name()}")
                    killed_processes.append(proc.name())
                except psutil.TimeoutExpired:
                    logger.warning(f"进程 {proc.name()} 终止超时，尝试强制杀死")
                    proc.kill()
                    logger.info(f"已强制杀死进程: {proc.name()}")
                    killed_processes.append(proc.name())
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"进程已不存在或无权限访问: {e}")
        except Exception as e:
            logger.error(f"处理进程 {proc.name()} 时出错: {e}")
    
    return killed_processes

def start_vm(vmx_path):
    """启动虚拟机"""
    try:
        logger.info(f"正在启动虚拟机: {vmx_path}")
        result = run_command_with_timeout([VMRUN_PATH, "start", vmx_path, "gui"], timeout=30)
        
        if result is None:
            logger.error("启动虚拟机命令执行失败")
            return False
            
        if result.returncode == 0:
            logger.info("虚拟机启动成功")
            return True
        else:
            logger.error(f"启动虚拟机失败，错误信息: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"启动虚拟机时发生错误: {e}")
        return False

def wait_for_vm_shutdown(vmx_path, timeout=60):
    """等待虚拟机完全关闭，带超时"""
    logger.info("等待虚拟机关闭...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if not monitoring_active:
            logger.info("监控已停止，退出等待")
            return False
            
        state = get_vm_power_state_combined(vmx_path)
        chinese_state = STATUS_MAP.get(state, state)
        if state == "off":
            logger.info("虚拟机已关闭。")
            return True
        logger.info(f"当前状态: {chinese_state}, 继续等待...")
        time.sleep(3)
    
    logger.warning("等待虚拟机关闭超时。")
    return False

def test_vmrun_command():
    """测试vmrun命令是否正常工作"""
    logger.info("测试vmrun命令...")
    result = run_command_with_timeout([VMRUN_PATH, "list"], timeout=10)
    
    if result is None:
        logger.error("无法执行vmrun命令")
        return False
        
    if result.returncode == 0:
        logger.info("vmrun命令测试成功")
        logger.info(f"vmrun输出: {result.stdout[:200]}...")
        return True
    else:
        logger.error(f"vmrun命令测试失败: {result.stderr}")
        return False

def start_vm_if_needed(vmx_path):
    """如果需要，启动虚拟机（脚本启动时检查）"""
    current_state = get_vm_power_state_combined(vmx_path)
    
    if current_state == "off":
        logger.info("检测到虚拟机已关机，尝试启动...")
        if start_vm(vmx_path):
            logger.info("虚拟机启动成功")
            return True
        else:
            logger.error("虚拟机启动失败")
            return False
    elif current_state == "running":
        logger.info("虚拟机已在运行中，无需启动")
        return True
    else:
        logger.warning(f"无法确定虚拟机状态: {current_state}")
        return False

def monitor_vm_state(vmx_path):
    """监控虚拟机状态的主循环"""
    previous_state = get_vm_power_state_combined(vmx_path)
    chinese_prev_state = STATUS_MAP.get(previous_state, previous_state)
    logger.info(f"初始状态: {chinese_prev_state}")
    
    consecutive_errors = 0
    
    while monitoring_active:
        try:
            if not monitoring_active:
                break
                
            current_state = get_vm_power_state_combined(vmx_path)
            chinese_curr_state = STATUS_MAP.get(current_state, current_state)
            chinese_prev_state_display = STATUS_MAP.get(previous_state, previous_state)
            
            if current_state == "error":
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    logger.error("连续多次状态检测失败，尝试重置监控")
                    time.sleep(10)
                    consecutive_errors = 0
            else:
                consecutive_errors = 0
            
            logger.info(f"当前状态: {chinese_curr_state}, 上次状态: {chinese_prev_state_display}")

            # 检测状态从"运行"变为"关闭"
            if previous_state == "running" and current_state == "off":
                logger.info("检测到虚拟机关机事件，等待确认是否为重启...")
                
                wait_start = time.time()
                while time.time() - wait_start < SHUTDOWN_CONFIRM_DELAY:
                    if not monitoring_active:
                        logger.info("监控已停止，退出等待")
                        break
                    time.sleep(1)
                
                if not monitoring_active:
                    break
                    
                current_state_after_delay = get_vm_power_state_combined(vmx_path)
                chinese_delayed_state = STATUS_MAP.get(current_state_after_delay, current_state_after_delay)
                logger.info(f"延迟后状态: {chinese_delayed_state}")
                
                if current_state_after_delay == "off":
                    logger.info("确认为关机事件，非重启。开始执行自动化流程...")
                    
                    if not wait_for_vm_shutdown(vmx_path):
                        logger.warning("虚拟机未能正常关闭，跳过本次操作。")
                        previous_state = current_state_after_delay
                        continue
                    
                    logger.info("正在关闭VMware主程序...")
                    killed_processes = stop_vmware_process(VMWARE_PROCESS_NAMES)
                    
                    if killed_processes:
                        logger.info(f"已终止 {len(killed_processes)} 个VMware进程")
                        time.sleep(2)
                    else:
                        logger.info("未找到需要终止的VMware进程")
                    
                    logger.info("正在启动虚拟机...")
                    if start_vm(vmx_path):
                        logger.info("自动化流程执行完毕。")
                    else:
                        logger.error("启动虚拟机失败，请检查配置。")
                else:
                    logger.info("虚拟机状态已恢复为运行，判定为重启事件，不执行操作。")

            previous_state = current_state
            
            sleep_start = time.time()
            while time.time() - sleep_start < CHECK_INTERVAL:
                if not monitoring_active:
                    logger.info("监控已停止，退出循环")
                    break
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("收到键盘中断信号")
            break
        except Exception as e:
            logger.error(f"监控过程中发生错误: {e}")
            time.sleep(5)

def signal_handler(signum, frame):
    """信号处理函数，用于优雅退出"""
    global monitoring_active
    logger.info(f"收到信号 {signum}，准备停止监控...")
    monitoring_active = False

def main():
    global monitoring_active
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    if not os.path.exists(VMRUN_PATH):
        logger.error(f"错误：找不到vmrun程序: {VMRUN_PATH}")
        return
    
    if not os.path.exists(VMX_FILE_PATH):
        logger.error(f"错误：找不到虚拟机配置文件: {VMX_FILE_PATH}")
        return
    
    if not test_vmrun_command():
        logger.warning("vmrun命令测试失败，将仅使用进程检测方法")
    
    logger.info("=== 虚拟机自动重启监控程序 ===")
    logger.info(f"虚拟机文件: {VMX_FILE_PATH}")
    logger.info(f"vmrun路径: {VMRUN_PATH}")
    logger.info("程序开始运行，按Ctrl+C停止监控")
    
    # 新增：脚本启动时检查虚拟机状态，如果已关机则启动
    if AUTO_START_ON_INIT:
        logger.info("检测到AUTO_START_ON_INIT已启用，检查虚拟机状态...")
        start_vm_if_needed(VMX_FILE_PATH)
    
    try:
        monitor_vm_state(VMX_FILE_PATH)
    except Exception as e:
        logger.error(f"监控过程发生异常: {e}")
    finally:
        monitoring_active = False
        logger.info("监控程序已停止")

if __name__ == "__main__":
    import sys
    main()