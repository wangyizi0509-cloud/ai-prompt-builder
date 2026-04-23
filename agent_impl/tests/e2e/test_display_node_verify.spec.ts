import { test, expect } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';
const EMAIL = 'test251@example.com';
const PASS = '32520463';
const ARTIFACTS = 'artifacts/display-node-verify';

test.describe('DisplayNode 统一展示节点验证', () => {
  test('SSE 流包含 DisplayNode 字段（API 层验证）', async ({ request }) => {
    // Login
    const loginRes = await request.post(`${BASE}/api/auth/login`, {
      data: { email: EMAIL, password: PASS },
    });
    expect(loginRes.ok()).toBeTruthy();
    const { token } = await loginRes.json();

    // Send message
    const uuid = crypto.randomUUID();
    const res = await request.fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      data: { message: '帮我重新做一次现状诊断，分析我和crush目前的关系阶段', session_id: uuid },
    });
    expect(res.ok()).toBeTruthy();

    const body = await res.text();
    const lines = body.split('\n').filter(l => l.startsWith('data: '));

    // Find process_event lines
    const processEvents = lines
      .map(l => { try { return JSON.parse(l.slice(6)); } catch { return null; } })
      .filter(d => d?.type === 'process_event');

    // Find final event
    const finalEvent = lines
      .map(l => { try { return JSON.parse(l.slice(6)); } catch { return null; } })
      .find(d => d?.type === 'final');

    // V1: process_event should have DisplayNode fields (if main_agent was triggered)
    if (processEvents.length > 0) {
      for (const pe of processEvents) {
        expect(pe.payload).toBeDefined();
        expect(pe.payload.event_type).toBeDefined();
        expect(pe).toHaveProperty('seq');
        expect(pe).toHaveProperty('turn_id');
        expect(pe).toHaveProperty('node_id');
        expect(pe).toHaveProperty('node_type');
      }
      console.log(`✅ process_events: ${processEvents.length}, all have DisplayNode fields`);
    } else {
      console.log('⚠️ No process_events (routed to small talk), checking final event only');
    }

    // V2: final event should have display_nodes array
    expect(finalEvent).toBeDefined();
    expect(finalEvent).toHaveProperty('turn_id');
    expect(finalEvent).toHaveProperty('turn_seq');
    expect(finalEvent).toHaveProperty('display_nodes');
    expect(Array.isArray(finalEvent.display_nodes)).toBeTruthy();

    // V3: display_nodes should be ordered by seq
    if (finalEvent.display_nodes.length > 1) {
      for (let i = 1; i < finalEvent.display_nodes.length; i++) {
        expect(finalEvent.display_nodes[i].seq).toBeGreaterThanOrEqual(
          finalEvent.display_nodes[i - 1].seq
        );
      }
    }

    // V4: Each display_node has required fields
    for (const dn of finalEvent.display_nodes) {
      expect(dn).toHaveProperty('seq');
      expect(dn).toHaveProperty('turnId');
      expect(dn).toHaveProperty('nodeId');
      expect(dn).toHaveProperty('nodeType');
      expect(dn).toHaveProperty('source');
      expect(dn).toHaveProperty('payload');
    }

    // V5: Check known node types
    const nodeTypes = finalEvent.display_nodes.map((n: any) => n.nodeType);
    const validTypes = [
      'user_message', 'reasoning', 'subgraph_thinking', 'tool_call',
      'report_card', 'inquiry_card', 'inquiry_receipt', 'ai_intermediate',
      'final_response',
    ];
    for (const nt of nodeTypes) {
      expect(validTypes).toContain(nt);
    }

    console.log(`✅ process_events: ${processEvents.length}`);
    console.log(`✅ display_nodes in final: ${finalEvent.display_nodes.length}`);
    console.log(`✅ node types: ${nodeTypes.join(', ')}`);
  });

  test('tool_call 卡片包含中文标签', async ({ request }) => {
    const loginRes = await request.post(`${BASE}/api/auth/login`, {
      data: { email: EMAIL, password: PASS },
    });
    const { token } = await loginRes.json();

    const uuid = crypto.randomUUID();
    const res = await request.fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      data: { message: '帮我做一下现状诊断', session_id: uuid },
    });
    const body = await res.text();

    const toolCallEvents = body.split('\n')
      .filter(l => l.startsWith('data: '))
      .map(l => { try { return JSON.parse(l.slice(6)); } catch { return null; } })
      .filter(d => d?.type === 'process_event' && d?.payload?.event_type === 'tool_call');

    if (toolCallEvents.length > 0) {
      for (const tc of toolCallEvents) {
        expect(tc.payload.tool_label).toBeDefined();
        expect(tc.payload.tool_label.length).toBeGreaterThan(0);
        console.log(`✅ tool: ${tc.payload.tool_name} → label: ${tc.payload.tool_label}`);
      }
    } else {
      console.log('⚠️ No tool_call events in this response (may have gone to small talk)');
    }
  });

  test('interrupt 事件包含 inquiry DisplayNode 字段', async ({ request }) => {
    const loginRes = await request.post(`${BASE}/api/auth/login`, {
      data: { email: EMAIL, password: PASS },
    });
    const { token } = await loginRes.json();

    const uuid = crypto.randomUUID();
    const res = await request.fetch(`${BASE}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      data: { message: '帮我重新做一次现状诊断', session_id: uuid },
    });
    const body = await res.text();

    const interruptEvent = body.split('\n')
      .filter(l => l.startsWith('data: '))
      .map(l => { try { return JSON.parse(l.slice(6)); } catch { return null; } })
      .find(d => d?.type === 'interrupt');

    if (interruptEvent) {
      expect(interruptEvent).toHaveProperty('seq');
      expect(interruptEvent).toHaveProperty('turn_id');
      expect(interruptEvent).toHaveProperty('node_id');
      expect(interruptEvent).toHaveProperty('node_type');
      expect(interruptEvent.node_type).toBe('inquiry_card');
      expect(interruptEvent).toHaveProperty('status', 'new');
      console.log(`✅ interrupt has DisplayNode fields: node_id=${interruptEvent.node_id}, seq=${interruptEvent.seq}`);
    } else {
      console.log('⚠️ No interrupt event (agent may not have asked questions)');
    }
  });
});
