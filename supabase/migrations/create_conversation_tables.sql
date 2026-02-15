-- Conversation/message persistence for chat history replay.
-- Safe to run multiple times.

create table if not exists conversations (
    id uuid primary key default gen_random_uuid(),
    thread_id text not null,
    user_id uuid not null references users(id) on delete cascade,
    title text,
    is_default boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    last_message_at timestamptz
);

create unique index if not exists uq_conversations_user_thread
    on conversations(user_id, thread_id);

create unique index if not exists uq_conversations_user_default
    on conversations(user_id)
    where is_default = true;

create index if not exists idx_conversations_thread_id on conversations(thread_id);
create index if not exists idx_conversations_user_id on conversations(user_id);
create index if not exists idx_conversations_created_at on conversations(created_at);

create table if not exists conversation_turns (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    turn_id text not null,
    turn_seq bigint generated always as identity,
    created_at timestamptz not null default now(),
    unique (conversation_id, turn_id),
    unique (conversation_id, turn_seq)
);

create index if not exists idx_conversation_turns_conversation_id on conversation_turns(conversation_id);
create index if not exists idx_conversation_turns_created_at on conversation_turns(created_at);

create table if not exists conversation_messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid not null references conversations(id) on delete cascade,
    thread_id text not null,
    turn_id text not null,
    turn_seq bigint not null,
    part_index int not null,
    seq bigint not null,
    role text not null,
    kind text not null,
    content text,
    content_hash text not null,
    metadata jsonb,
    created_at timestamptz not null default now(),
    unique (conversation_id, seq),
    unique (conversation_id, turn_id, kind, role, part_index)
);

create index if not exists idx_conversation_messages_thread_id on conversation_messages(thread_id);
create index if not exists idx_conversation_messages_user_lookup on conversation_messages(conversation_id, seq);
create index if not exists idx_conversation_messages_created_at on conversation_messages(created_at);
create index if not exists idx_conversation_messages_turn on conversation_messages(conversation_id, turn_id);
