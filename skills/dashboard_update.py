"""
Dashboard Update Skill
允许 Agent 更新 Dashboard 显示的信息

SKILL CONTRACT:
- 更新 Dashboard 的待办事项、天气、Worker 状态等
- 返回结构化结果
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Dashboard 数据存储路径
DASHBOARD_DATA_FILE = Path("dashboard_data.json")


def _load_dashboard_data() -> Dict[str, Any]:
    """加载当前 dashboard 数据"""
    if not DASHBOARD_DATA_FILE.exists():
        return _get_default_data()
    try:
        with open(DASHBOARD_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return _get_default_data()


def _save_dashboard_data(data: Dict[str, Any]):
    """保存 dashboard 数据"""
    with open(DASHBOARD_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_default_data() -> Dict[str, Any]:
    """获取默认数据"""
    return {
        "weather": {
            "location": "Unknown",
            "current": {
                "temp": 22,
                "condition": "sunny",
                "humidity": 65,
                "wind": "3级"
            },
            "forecast": [
                {"day": "明天", "condition": "cloudy", "high": 23, "low": 18},
                {"day": "后天", "condition": "rainy", "high": 20, "low": 16},
                {"day": "周五", "condition": "sunny", "high": 25, "low": 19}
            ]
        },
        "todos": [],
        "workers": [
            {"id": "worker_1", "name": "Worker-1", "status": "offline", "statusText": "离线"},
            {"id": "worker_2", "name": "Worker-2", "status": "offline", "statusText": "离线"},
            {"id": "worker_3", "name": "Worker-3", "status": "offline", "statusText": "离线"}
        ],
        "system_message": "",
        "last_updated": datetime.now().isoformat()
    }


def execute(args: Optional[str] = None) -> Dict[str, Any]:
    """
    更新 Dashboard 信息

    Args:
        args: 更新指令，格式: action||data
              例如:
              - "add_todo||买菜"
              - "complete_todo||12345"
              - "update_weather||{\"temp\": 25, \"condition\": \"sunny\"}"
              - "update_worker||worker_1||working"
              - "clear_todos"
              - "set_message||系统正常运行中"

    Returns:
        Dict: {success, data, message, error}
    """
    try:
        if not args:
            return {
                "success": False,
                "error": "Missing arguments",
                "message": "请提供更新指令，格式: action||data",
                "data": None
            }

        # 解析参数
        parts = [p.strip() for p in args.split("||")]
        action = parts[0].lower()
        
        data = _load_dashboard_data()
        
        # 执行相应操作
        if action == "add_todo":
            if len(parts) < 2:
                return {"success": False, "error": "Missing todo text", "message": "请提供待办事项内容", "data": None}
            
            todo = {
                "id": int(datetime.now().timestamp() * 1000),
                "text": parts[1],
                "done": False,
                "created": datetime.now().isoformat()
            }
            data["todos"].append(todo)
            _save_dashboard_data(data)
            return {
                "success": True,
                "message": f"已添加待办: {parts[1]}",
                "data": {"todo": todo, "total": len(data["todos"])}
            }
        
        elif action == "complete_todo":
            if len(parts) < 2:
                return {"success": False, "error": "Missing todo id", "message": "请提供待办ID", "data": None}
            
            todo_id = int(parts[1])
            for todo in data["todos"]:
                if todo["id"] == todo_id:
                    todo["done"] = True
                    _save_dashboard_data(data)
                    return {"success": True, "message": f"已完成: {todo['text']}", "data": {"todo": todo}}
            
            return {"success": False, "error": "Todo not found", "message": "找不到该待办事项", "data": None}
        
        elif action == "delete_todo":
            if len(parts) < 2:
                return {"success": False, "error": "Missing todo id", "message": "请提供待办ID", "data": None}
            
            todo_id = int(parts[1])
            data["todos"] = [t for t in data["todos"] if t["id"] != todo_id]
            _save_dashboard_data(data)
            return {"success": True, "message": "已删除待办事项", "data": {"total": len(data["todos"])}}
        
        elif action == "clear_todos":
            data["todos"] = []
            _save_dashboard_data(data)
            return {"success": True, "message": "已清空所有待办事项", "data": {"total": 0}}
        
        elif action == "update_weather":
            if len(parts) < 2:
                return {"success": False, "error": "Missing weather data", "message": "请提供天气数据", "data": None}
            
            try:
                weather_update = json.loads(parts[1])
                data["weather"]["current"].update(weather_update)
                _save_dashboard_data(data)
                return {"success": True, "message": "天气信息已更新", "data": {"weather": data["weather"]}}
            except json.JSONDecodeError:
                return {"success": False, "error": "Invalid JSON", "message": "天气数据格式错误", "data": None}
        
        elif action == "update_forecast":
            if len(parts) < 2:
                return {"success": False, "error": "Missing forecast data", "message": "请提供预报数据", "data": None}
            
            try:
                forecast = json.loads(parts[1])
                data["weather"]["forecast"] = forecast
                _save_dashboard_data(data)
                return {"success": True, "message": "天气预报已更新", "data": {"forecast": forecast}}
            except json.JSONDecodeError:
                return {"success": False, "error": "Invalid JSON", "message": "预报数据格式错误", "data": None}
        
        elif action == "update_worker":
            if len(parts) < 3:
                return {"success": False, "error": "Missing worker info", "message": "格式: update_worker||worker_id||status", "data": None}
            
            worker_id = parts[1]
            status = parts[2].lower()
            
            status_map = {
                "working": {"status": "active", "statusText": "工作中"},
                "active": {"status": "active", "statusText": "工作中"},
                "busy": {"status": "active", "statusText":"忙碌"},
                "idle": {"status": "idle", "statusText": "闲置"},
                "free": {"status": "idle", "statusText": "闲置"},
                "offline": {"status": "offline", "statusText": "离线"},
                "down": {"status": "offline", "statusText": "离线"}
            }
            
            worker_status = status_map.get(status, {"status": "idle", "statusText": status})
            
            for worker in data["workers"]:
                if worker["id"] == worker_id:
                    worker.update(worker_status)
                    _save_dashboard_data(data)
                    return {"success": True, "message": f"Worker {worker_id} 状态已更新为 {worker_status['statusText']}", "data": {"worker": worker}}
            
            return {"success": False, "error": "Worker not found", "message": f"找不到 Worker {worker_id}", "data": None}
        
        elif action == "set_message":
            if len(parts) < 2:
                return {"success": False, "error": "Missing message", "message": "请提供消息内容", "data": None}
            
            data["system_message"] = parts[1]
            _save_dashboard_data(data)
            return {"success": True, "message": "系统消息已设置", "data": {"message": parts[1]}}
        
        elif action == "get":
            # 获取当前 dashboard 数据
            return {"success": True, "message": "获取 Dashboard 数据成功", "data": data}
        
        else:
            return {
                "success": False,
                "error": "Unknown action",
                "message": f"未知操作: {action}。可用操作: add_todo, complete_todo, delete_todo, clear_todos, update_weather, update_forecast, update_worker, set_message, get",
                "data": None
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"更新 Dashboard 时出错: {str(e)}",
            "data": None
        }


def register_skills(skill_manager):
    """
    注册此技能
    
    允许 Agent 通过技能调用来更新 Dashboard 显示的信息。
    
    常用操作:
    - add_todo: 添加待办事项
    - complete_todo: 完成待办事项
    - update_worker: 更新 Worker 状态
    - update_weather: 更新天气信息
    - set_message: 设置系统消息
    
    示例:
      <call_skill>dashboard_update:add_todo||买牛奶</call_skill>
      <call_skill>dashboard_update:update_worker||worker_1||working</call_skill>
      <call_skill>dashboard_update:set_message||系统运行正常</call_skill>
    """
    skill_manager.register(
        "dashboard_update",
        "更新 Dashboard 显示的信息（待办、天气、Worker状态）。Agent 可以通过此技能控制 Dashboard 的显示内容。",
        execute
    )
