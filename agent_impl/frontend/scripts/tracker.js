/**
 * Crushe Tracker · 前端埋点 SDK
 *
 * 职责：
 *   - anonymous_id: localStorage UUID, 跨页共享
 *   - session_id:   sessionStorage UUID, 标签页生命周期内
 *   - 批量/定时 flush, pagehide 用 sendBeacon 兜底
 *
 * 使用：
 *   <script src="/scripts/tracker.js"></script>
 *   Tracker.track('splash_view');
 *   Tracker.track('description_submit', { text_len: 123 });
 *
 * 后端契约: POST /api/track
 *   { anonymous_id, user_id?, events: [{event_name, session_id, props, ts_client}] }
 */
(function (root) {
    'use strict';

    var ANON_KEY = 'crushe_tracker_anon_id';
    var SESSION_KEY = 'crushe_tracker_session_id';
    var USER_KEY = 'crushe_tracker_user_id';
    var ENDPOINT = '/api/track';
    var FLUSH_INTERVAL_MS = 5000;
    var FLUSH_SIZE = 10;
    var MAX_BATCH = 50;

    function generateUuid() {
        try {
            if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
                return crypto.randomUUID();
            }
        } catch (_) { /* fallthrough */ }
        var tpl = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
        return tpl.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    function readLocal(key) {
        try { return localStorage.getItem(key); } catch (_) { return null; }
    }
    function writeLocal(key, value) {
        try { localStorage.setItem(key, value); } catch (_) { /* ignore */ }
    }
    function readSession(key) {
        try { return sessionStorage.getItem(key); } catch (_) { return null; }
    }
    function writeSession(key, value) {
        try { sessionStorage.setItem(key, value); } catch (_) { /* ignore */ }
    }

    function getAnonymousId() {
        var id = readLocal(ANON_KEY);
        if (!id) {
            id = generateUuid();
            writeLocal(ANON_KEY, id);
        }
        return id;
    }

    function getSessionId() {
        var id = readSession(SESSION_KEY);
        if (!id) {
            id = generateUuid();
            writeSession(SESSION_KEY, id);
        }
        return id;
    }

    function getUserId() {
        return readLocal(USER_KEY) || null;
    }

    function setUserId(uid) {
        if (uid && typeof uid === 'string') {
            writeLocal(USER_KEY, uid);
        } else {
            try { localStorage.removeItem(USER_KEY); } catch (_) { /* ignore */ }
        }
    }

    var queue = [];
    var flushTimer = null;

    function enqueue(eventName, props) {
        if (!eventName || typeof eventName !== 'string') return;
        queue.push({
            event_name: eventName,
            session_id: getSessionId(),
            props: props || {},
            ts_client: new Date().toISOString()
        });
        if (queue.length >= FLUSH_SIZE) {
            flush(false);
        } else {
            ensureTimer();
        }
    }

    function ensureTimer() {
        if (flushTimer) return;
        flushTimer = setTimeout(function () {
            flushTimer = null;
            flush(false);
        }, FLUSH_INTERVAL_MS);
    }

    function buildPayload(batch) {
        return {
            anonymous_id: getAnonymousId(),
            user_id: getUserId(),
            events: batch
        };
    }

    function flush(useBeacon) {
        if (queue.length === 0) return;
        var batch = queue.splice(0, MAX_BATCH);
        var payload = buildPayload(batch);
        try {
            if (useBeacon && typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
                var blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
                navigator.sendBeacon(ENDPOINT, blob);
                return;
            }
        } catch (_) { /* fall through to fetch */ }

        try {
            fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true,
                credentials: 'same-origin'
            }).catch(function () {
                // 失败的事件不重试（避免雪崩），直接丢弃
            });
        } catch (_) { /* ignore */ }
    }

    function track(eventName, props) {
        try { enqueue(eventName, props); } catch (_) { /* ignore */ }
    }

    function installLifecycleHooks() {
        if (typeof window === 'undefined' || !window.addEventListener) return;
        var flushOnExit = function () { flush(true); };
        window.addEventListener('pagehide', flushOnExit);
        // 某些 iOS WebView pagehide 不触发，visibilitychange 兜底
        document.addEventListener('visibilitychange', function () {
            if (document.visibilityState === 'hidden') flush(true);
        });
    }

    installLifecycleHooks();

    root.Tracker = {
        track: track,
        flush: function () { flush(false); },
        getAnonymousId: getAnonymousId,
        getSessionId: getSessionId,
        setUserId: setUserId,
        getUserId: getUserId,
        _queue: queue  // for debug
    };
})(typeof window !== 'undefined' ? window : this);
