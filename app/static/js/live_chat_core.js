// static/js/live_chat_core.js

window.LiveChatCore = (function () {
    let socketInstance = null;
    const renderedEvents = new Set();

    function initSocket() {
        if (socketInstance) return socketInstance;

        socketInstance = io({
            reconnection: true,
            reconnectionAttempts: 20,
            reconnectionDelay: 1000
        });

        socketInstance.on("connect", function () {
            console.log("✅ Socket connected");
        });

        socketInstance.on("disconnect", function () {
            console.log("❌ Socket disconnected");
        });

        return socketInstance;
    }

    function joinTicketRoom(ticketId) {
        if (!ticketId) return;

        initSocket().emit("join_ticket_room", {
            ticket_id: String(ticketId)
        });
    }

    function joinNotificationRoom(userId) {
        if (!userId) return;

        initSocket().emit("join_notification_room", {
            user_id: String(userId)
        });
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) return "";

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatTime(value) {
        if (!value) {
            return new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit"
            });
        }

        const parsed = new Date(value);

        if (isNaN(parsed.getTime())) return String(value);

        return parsed.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        });
    }

    function scrollBottom(container) {
        if (!container) return;
        container.scrollTop = container.scrollHeight;
    }

    function makeEventKey(prefix, data) {
        if (!data) return null;

        if (data.id) return `${prefix}_id_${data.id}`;

        if (data.ticket_id && data.comment_id) {
            return `${prefix}_${data.ticket_id}_${data.comment_id}`;
        }

        if (data.comment_id) return `${prefix}_comment_${data.comment_id}`;

        if (data.ticket_id && data.message) {
            return `${prefix}_${data.ticket_id}_${data.message}`;
        }

        if (data.user_id && data.message && data.created_at) {
            return `${prefix}_${data.user_id}_${data.message}_${data.created_at}`;
        }

        return `${prefix}_${JSON.stringify(data)}`;
    }

    function hasRendered(key) {
        if (!key) return false;

        if (renderedEvents.has(key)) return true;

        renderedEvents.add(key);
        return false;
    }

    function clearRenderedEvents() {
        renderedEvents.clear();
    }

    function addChatBubble(options) {
        const container = options.container;

        if (!container) return null;

        const side = options.side || "left";
        const message = options.message || "";
        const name = options.name || "";
        const type = options.type || "normal";
        const html = options.html === true;
        const createdAt = options.created_at || null;

        const row = document.createElement("div");
        row.className = side === "right"
            ? "chat-row chat-right"
            : "chat-row chat-left";

        const bubble = document.createElement("div");
        bubble.classList.add("chat-bubble");

        if (type === "system") {
            bubble.classList.add("system-bubble");
        } else if (side === "right") {
            bubble.classList.add("agent-bubble");
        } else {
            bubble.classList.add("customer-bubble");
        }

        let content = "";

        if (type !== "system" && name) {
            content += `<strong>${escapeHtml(name)}</strong>`;
        }

        if (html) {
            const safeMessage = String(message || "")
                .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "")
                .replace(/on\w+="[^"]*"/gi, "")
                .replace(/on\w+='[^']*'/gi, "")
                .replace(/javascript:/gi, "");

            content += `<div>${safeMessage}</div>`;
        } else {
            content += `<div>${escapeHtml(message)}</div>`;
        }

        content += `<div class="chat-time">${formatTime(createdAt)}</div>`;

        bubble.innerHTML = content;
        row.appendChild(bubble);
        container.appendChild(row);

        scrollBottom(container);

        return row;
    }

    async function api(url, options = {}) {
        const finalOptions = {
            headers: {
                "Content-Type": "application/json"
            },
            ...options
        };

        if (options.body instanceof FormData) {
            delete finalOptions.headers;
        }

        try {
            const response = await fetch(url, finalOptions);

            let data = {};

            try {
                data = await response.json();
            } catch (e) {
                data = {};
            }

            return {
                ok: response.ok,
                status: response.status,
                data: data
            };

        } catch (e) {
            console.error("API ERROR:", e);

            return {
                ok: false,
                status: 500,
                data: {
                    ok: false
                }
            };
        }
    }

    function fetchMe() {
        return api("/customer/api/me", {
            method: "GET"
        });
    }

    function fetchActiveTicket() {
        return api("/customer/api/ticket/active", {
            method: "GET"
        });
    }

    function fetchTicketStatus(ticketId) {
        return api(`/customer/api/ticket/status/${ticketId}`, {
            method: "GET"
        });
    }

    function fetchTicketComments(ticketId) {
        return api(`/customer/api/ticket/comments/${ticketId}`, {
            method: "GET"
        });
    }

    function fetchChatHistory() {
        return api("/customer/api/chat/history", {
            method: "GET"
        });
    }

    function sendAiMessage(message, options = {}) {
        return api("/customer/api/chat", {
            method: "POST",
            body: JSON.stringify({
                message: message,
                ...options
            })
        });
    }

    function sendResolutionResult(solved, sourceType, originalMessage) {
        return api("/customer/api/chat/resolution", {
            method: "POST",
            body: JSON.stringify({
                solved: solved === true,
                source_type: sourceType || "",
                original_message: originalMessage || ""
            })
        });
    }

    function escalateSupport(message) {
        return api("/customer/api/escalate", {
            method: "POST",
            body: JSON.stringify({
                message: message || "Customer requested support."
            })
        });
    }

    function sendTicketComment(ticketId, message) {
        return api(`/customer/api/ticket/comment/${ticketId}`, {
            method: "POST",
            body: JSON.stringify({
                message: message
            })
        });
    }

    function reopenTicket(ticketId) {
        return api(`/customer/api/ticket/reopen/${ticketId}`, {
            method: "POST"
        });
    }

    function confirmSolved(ticketId) {
        return api(`/customer/api/ticket/confirm-solved/${ticketId}`, {
            method: "POST"
        });
    }

    function clearChatHistory() {
        return api("/customer/api/chat/clear", {
            method: "POST"
        });
    }

    function saveSelectedFaq(question, answer, originalMessage) {
        return api("/customer/api/chat/faq-selected", {
            method: "POST",
            body: JSON.stringify({
                question: question,
                answer: answer,
                original_message: originalMessage
            })
        });
    }

    function uploadAttachment(ticketId, file) {
        const formData = new FormData();
        formData.append("attachment", file);

        return api(`/customer/api/ticket/upload/${ticketId}`, {
            method: "POST",
            body: formData
        });
    }

    function normaliseCommentEvent(data) {
        if (!data) return null;

        return {
            ticketId: data.ticket_id || null,
            commentId: data.comment_id || data.id || null,
            message: data.message || "",
            senderName: data.sender_name || data.author || "Support",
            senderRole: String(data.sender_role || data.role || "").toLowerCase(),
            authorId: data.author_id || null,
            isAttachment:
                data.is_attachment === true ||
                String(data.message || "").includes("<a ") ||
                String(data.message || "").includes("<strong>") ||
                String(data.message || "").includes("<br"),
            createdAt: data.created_at || null
        };
    }

    function renderCommentEvent(container, data, currentUserId) {
        const event = normaliseCommentEvent(data);

        if (!event || !event.message) return;

        const key = makeEventKey("comment", {
            comment_id: event.commentId,
            ticket_id: event.ticketId,
            message: event.message
        });

        if (hasRendered(key)) return;

        const isMine =
            currentUserId &&
            event.authorId &&
            Number(currentUserId) === Number(event.authorId);

        const isSupportContext =
            String(event.message || "").includes("Current AI / FAQ Conversation") ||
            String(event.message || "").includes("Previous AI / FAQ Conversation");

        if (isSupportContext && isMine) {
            return;
        }

        if (isSupportContext) {
            addChatBubble({
                container: container,
                message: event.message,
                side: "left",
                name: "Conversation Context",
                html: true,
                type: "system",
                created_at: event.createdAt
            });
            return;
        }

        const isCustomer = event.senderRole === "customer";

        addChatBubble({
            container: container,
            message: event.message,
            side: isMine || isCustomer ? "right" : "left",
            name: isMine ? "You" : event.senderName,
            html: event.isAttachment,
            type: "normal",
            created_at: event.createdAt
        });
    }

    function renderChatMessage(container, chat, currentUserId) {
        if (!chat || !chat.message) return;

        const key = makeEventKey("chat", chat);

        if (hasRendered(key)) return;

        const role = String(chat.role || "").toLowerCase();

        if (role === "system") {
            addChatBubble({
                container: container,
                message: chat.message,
                side: "left",
                name: "System",
                html: true,
                type: "system",
                created_at: chat.created_at
            });
            return;
        }

        addChatBubble({
            container: container,
            message: chat.message,
            side: role === "user" ? "right" : "left",
            name: role === "user" ? "You" : "AI Assistant",
            html: true,
            type: "normal",
            created_at: chat.created_at
        });
    }

    function updateBadge(id, count) {
        const badge = document.getElementById(id);

        if (!badge) return;

        const number = Number(count || 0);

        badge.innerText = number;
        badge.style.display = number > 0 ? "inline-block" : "none";
    }

    function incrementBadge(id, amount = 1) {
        const badge = document.getElementById(id);

        if (!badge) return;

        const current = Number((badge.innerText || "0").trim()) || 0;

        updateBadge(id, current + amount);
    }

    function requestSoftRefresh(reason) {
        const event = new CustomEvent("livechat:soft-refresh", {
            detail: {
                reason: reason || "updated"
            }
        });

        window.dispatchEvent(event);
    }

    return {
        initSocket,
        joinTicketRoom,
        joinNotificationRoom,
        escapeHtml,
        formatTime,
        scrollBottom,
        makeEventKey,
        hasRendered,
        clearRenderedEvents,
        addChatBubble,
        renderCommentEvent,
        normaliseCommentEvent,
        renderChatMessage,
        updateBadge,
        incrementBadge,
        requestSoftRefresh,
        api,
        fetchMe,
        fetchActiveTicket,
        fetchTicketStatus,
        fetchTicketComments,
        fetchChatHistory,
        sendAiMessage,
        sendResolutionResult,
        escalateSupport,
        sendTicketComment,
        reopenTicket,
        confirmSolved,
        clearChatHistory,
        saveSelectedFaq,
        uploadAttachment
    };
})();