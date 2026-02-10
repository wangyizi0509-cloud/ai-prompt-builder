#!/usr/bin/env python3
import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT_DIR)

from dotenv import load_dotenv
from langgraph.checkpoint.memory import MemorySaver
from graph.workflow import compile_workflow
from graph.state import create_initial_state

load_dotenv()

checkpointer = MemorySaver()
app = compile_workflow(checkpointer=checkpointer)
thread_id = 'test_conversation_20_rounds'
config = {'configurable': {'thread_id': thread_id}}

script = [
    '你好，我是新用户，想了解一下这个系统',
    '我最近遇到一个女生，想和她成为朋友',
    '我们是在图书馆认识的',
    '她是大学生，比我小一届',
    '我们经常一起自习'
]

current_state = None
stats = {'total': 0, 'success': 0, 'interrupt': 0, 'error': 0}

for i, user_input in enumerate(script, 1):
    stats['total'] += 1
    print(f'第 {i}/{len(script)} 轮: {user_input[:30]}...')
    try:
        if current_state is None:
            state_input = create_initial_state(user_input)
        else:
            state_input = {**current_state, 'user_message': user_input}
        
        result = app.invoke(state_input, config=config)
        
        if '__interrupt__' in result:
            stats['interrupt'] += 1
            print(f'  → 触发中断')
        else:
            stats['success'] += 1
            print(f'  → 正常完成')
        
        current_state = result
    except Exception as e:
        stats['error'] += 1
        print(f'  → 错误: {str(e)[:50]}...')
        continue

print(f'\n统计: 总计 {stats["total"]}, 成功 {stats["success"]}, 中断 {stats["interrupt"]}, 错误 {stats["error"]}')
