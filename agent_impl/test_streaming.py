"""
Streaming 测试脚本
用于测试 Agent 的流式执行功能
"""

import requests
import json
import sys

def stream_chat(message, session_id="test_session", stream_mode="updates", base_url="http://localhost:8000"):
    """
    测试流式聊天接口
    
    Args:
        message: 用户消息
        session_id: 会话 ID
        stream_mode: 流模式 ("values", "updates", "messages", "debug")
        base_url: 服务器地址
    """
    url = f"{base_url}/api/chat/stream"
    data = {
        "message": message,
        "session_id": session_id,
        "stream_mode": stream_mode
    }
    
    print(f"🚀 发送消息: {message}")
    print(f"📡 流模式: {stream_mode}")
    print(f"🔗 服务器: {base_url}")
    print("-" * 60)
    
    try:
        response = requests.post(url, json=data, stream=True, timeout=300)
        response.raise_for_status()
        
        chunk_count = 0
        for line in response.iter_lines():
            if line:
                # SSE 格式: data: {...}
                if line.startswith(b"data: "):
                    json_str = line[6:].decode("utf-8")
                    try:
                        chunk = json.loads(json_str)
                        chunk_count += 1
                        
                        if chunk.get("type") == "chunk":
                            data = chunk.get("data", {})
                            print(f"\n📦 Chunk #{chunk_count}")
                            for key, value in data.items():
                                if isinstance(value, dict):
                                    print(f"  {key}:")
                                    for k, v in value.items():
                                        if k == "messages" and isinstance(v, list) and v:
                                            last_msg = v[-1]
                                            if hasattr(last_msg, "content"):
                                                print(f"    {k}: {last_msg.content[:100]}...")
                                            else:
                                                print(f"    {k}: {len(v)} messages")
                                        else:
                                            print(f"    {k}: {str(v)[:100]}")
                                else:
                                    print(f"  {key}: {str(value)[:100]}")
                        
                        elif chunk.get("type") == "info":
                            print(f"ℹ️  [{chunk.get('node')}] {chunk.get('message')}")
                        
                        elif chunk.get("type") == "done":
                            print(f"\n✅ {chunk.get('message')}")
                            final_info = chunk.get("final_state", {})
                            print(f"   消息数: {final_info.get('message_count', 0)}")
                            print(f"   有回复: {final_info.get('has_response', False)}")
                        
                        elif chunk.get("type") == "error":
                            print(f"\n❌ 错误: {chunk.get('error')}")
                            if chunk.get("traceback"):
                                print(f"\n详细错误:\n{chunk.get('traceback')}")
                    
                    except json.JSONDecodeError as e:
                        print(f"⚠️  JSON 解析错误: {e}")
                        print(f"   原始数据: {json_str[:200]}")
        
        print("-" * 60)
        print(f"✅ 完成！共收到 {chunk_count} 个 chunk")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 请求失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 Agent 流式执行")
    parser.add_argument("message", help="用户消息")
    parser.add_argument("--session-id", default="test_session", help="会话 ID")
    parser.add_argument("--stream-mode", default="updates", 
                       choices=["values", "updates", "messages", "debug"],
                       help="流模式")
    parser.add_argument("--url", default="http://localhost:8000", help="服务器地址")
    
    args = parser.parse_args()
    
    stream_chat(
        message=args.message,
        session_id=args.session_id,
        stream_mode=args.stream_mode,
        base_url=args.url
    )

