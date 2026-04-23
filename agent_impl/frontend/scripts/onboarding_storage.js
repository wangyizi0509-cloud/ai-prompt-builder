/**
 * Onboarding v2 · localStorage 共享工具
 *
 * 参考文档:agent_impl/onboarding_v2/LOCAL_STORAGE_PROTOCOL.md
 *
 * - Key:crushe_onboarding_v2
 * - 所有 stage/report/session_id 等都塞在这一个 JSON 里
 * - 纯浏览器脚本,无依赖;挂载到 window.OnboardingStorage 供 splash/onboarding/report/index 共用
 * - 本期 Agent I 先独立建立,Agent E/F 切过来时共用(Agent H 集成阶段协调)
 */
(function (root) {
    'use strict';

    var STORAGE_KEY = 'crushe_onboarding_v2';
    var PROTOCOL_VERSION = 1;

    /**
     * 生成一个 UUID v4。优先使用 crypto.randomUUID(),不支持时回退到伪随机拼接。
     */
    function generateUuid() {
        try {
            if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
                return crypto.randomUUID();
            }
        } catch (_) { /* fallthrough */ }
        // 退化方案(兼容老浏览器,不保证 RFC 4122 完全合规)
        var tpl = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
        return tpl.replace(/[xy]/g, function (c) {
            var r = (Math.random() * 16) | 0;
            var v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    }

    /**
     * 从 localStorage 读取原始字符串并 JSON.parse。
     * 异常情况(SSR/无 Storage/解析失败/version 不匹配)统一返回 null。
     */
    function safeLoad() {
        try {
            if (typeof localStorage === 'undefined') return null;
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var obj = JSON.parse(raw);
            if (!obj || typeof obj !== 'object') return null;
            // 协议版本不一致则视为失效
            if (obj.protocol_version !== PROTOCOL_VERSION) return null;
            return obj;
        } catch (e) {
            // 静默失败:localStorage 被禁用 / JSON 损坏
            return null;
        }
    }

    /**
     * 把对象 JSON.stringify 后写回 localStorage。异常时返回 false。
     */
    function safeSave(obj) {
        try {
            if (typeof localStorage === 'undefined') return false;
            if (!obj || typeof obj !== 'object') return false;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
            return true;
        } catch (e) {
            return false;
        }
    }

    var OnboardingStorage = {
        KEY: STORAGE_KEY,
        PROTOCOL_VERSION: PROTOCOL_VERSION,

        /**
         * 读取完整 onboarding 状态对象;无数据或损坏时返回 null。
         */
        load: function () {
            return safeLoad();
        },

        /**
         * 写入完整对象(会覆盖整个 key)。自动补齐 protocol_version。
         */
        save: function (data) {
            if (!data || typeof data !== 'object') return false;
            // 确保协议版本字段存在且正确
            data.protocol_version = PROTOCOL_VERSION;
            return safeSave(data);
        },

        /**
         * 删除整个 onboarding key(用于"重新诊断"或协议版本冲突)。
         */
        clear: function () {
            try {
                if (typeof localStorage !== 'undefined') {
                    localStorage.removeItem(STORAGE_KEY);
                }
            } catch (e) { /* noop */ }
        },

        /**
         * 返回当前 stage 字段;无数据则返回 null。
         * 可能值:splash / free_input / questions / report / paid / done
         */
        getStage: function () {
            var data = safeLoad();
            if (!data) return null;
            return data.stage || null;
        },

        /**
         * 更新 stage。若 storage 尚未初始化,会创建一个最小骨架。
         */
        setStage: function (stage) {
            var data = safeLoad();
            if (!data) {
                data = {
                    protocol_version: PROTOCOL_VERSION,
                    session_id: generateUuid(),
                    stage: stage,
                    free_text: '',
                    uploaded_images: [],
                    analysis: null,
                    answers: {},
                    report: null,
                    paid: false,
                    paid_at: null,
                };
            } else {
                data.stage = stage;
            }
            return safeSave(data);
        },

        /**
         * 返回 report 对象(DiagnosisReport 副本);未生成时返回 null。
         */
        getReport: function () {
            var data = safeLoad();
            if (!data) return null;
            return data.report || null;
        },

        /**
         * 返回 session_id;若不存在则**生成并持久化**一个新的 UUID。
         * 这样 splash 之前的边缘情况(直接打开 index)也有稳定 id 可用。
         */
        getSessionId: function () {
            var data = safeLoad();
            if (data && data.session_id) return data.session_id;
            var newId = generateUuid();
            if (!data) {
                data = {
                    protocol_version: PROTOCOL_VERSION,
                    session_id: newId,
                    stage: 'splash',
                    free_text: '',
                    uploaded_images: [],
                    analysis: null,
                    answers: {},
                    report: null,
                    paid: false,
                    paid_at: null,
                };
            } else {
                data.session_id = newId;
            }
            safeSave(data);
            return newId;
        },

        /**
         * 判定用户是否已付费(可进入主对话)。
         * 规则:stage === 'paid' 或 (stage === 'done' 且 paid === true)。
         */
        isPaid: function () {
            var data = safeLoad();
            if (!data) return false;
            if (data.stage === 'paid') return true;
            if (data.stage === 'done' && data.paid === true) return true;
            return false;
        },

        /**
         * 把 stage 标记为 done(onboarding 结束,不再往主聊天注入 summary)。
         * 同时把 paid 置 true(因为只有付费用户才会走到这一步),补齐 paid_at。
         */
        markDone: function () {
            var data = safeLoad();
            if (!data) {
                data = {
                    protocol_version: PROTOCOL_VERSION,
                    session_id: generateUuid(),
                    stage: 'done',
                    free_text: '',
                    uploaded_images: [],
                    analysis: null,
                    answers: {},
                    report: null,
                    paid: true,
                    paid_at: new Date().toISOString(),
                };
            } else {
                data.stage = 'done';
                if (!data.paid) {
                    data.paid = true;
                    data.paid_at = data.paid_at || new Date().toISOString();
                }
            }
            return safeSave(data);
        },
    };

    // 导出到全局(浏览器脚本风格,非 ES module)
    root.OnboardingStorage = OnboardingStorage;
})(typeof window !== 'undefined' ? window : this);
