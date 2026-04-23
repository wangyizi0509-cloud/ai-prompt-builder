-- 埋点事件表：记录销售漏斗 / 产品行为事件
-- 设备维度：anonymous_id（前端 localStorage UUID），登录/付费后可补 user_id
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anonymous_id TEXT NOT NULL,
    user_id TEXT,
    session_id TEXT NOT NULL,
    event_name TEXT NOT NULL,
    props JSONB DEFAULT '{}'::jsonb,
    ua TEXT,
    referrer TEXT,
    source TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_event_time
    ON public.events(event_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_anon_time
    ON public.events(anonymous_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_user_time
    ON public.events(user_id, created_at DESC) WHERE user_id IS NOT NULL;
