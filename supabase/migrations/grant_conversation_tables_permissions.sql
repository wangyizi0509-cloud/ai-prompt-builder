-- Grant permissions for conversation tables

-- Grant SELECT to anon (for unauthenticated users)
GRANT SELECT ON conversations TO anon;
GRANT SELECT ON conversation_turns TO anon;
GRANT SELECT ON conversation_messages TO anon;

-- Grant ALL PRIVILEGES to authenticated (for logged-in users)
GRANT ALL PRIVILEGES ON conversations TO authenticated;
GRANT ALL PRIVILEGES ON conversation_turns TO authenticated;
GRANT ALL PRIVILEGES ON conversation_messages TO authenticated;
