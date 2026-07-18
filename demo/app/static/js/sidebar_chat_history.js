// static/js/sidebar_chat_history.js

(function () {
    "use strict";

    console.log("✅ sidebar_chat_history.js loaded");

    const historyBox = document.getElementById(
        "supportRequestHistory"
    );

    const searchBox = document.getElementById(
        "supportHistorySearch"
    );

    if (!historyBox) {
        return;
    }

    async function api(url) {
        try {
            const response = await fetch(url, {
                method: "GET",
                credentials: "same-origin"
            });

            let data = {};

            try {
                data = await response.json();
            } catch (error) {
                data = {};
            }

            return {
                ok: response.ok,
                status: response.status,
                data: data
            };

        } catch (error) {
            console.error(
                "Sidebar history API error:",
                error
            );

            return {
                ok: false,
                status: 500,
                data: {}
            };
        }
    }

    function escapeHtml(value) {
        if (
            value === null ||
            value === undefined
        ) {
            return "";
        }

        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function buildChatUrl(sessionId) {
        return (
            "/customer/chat?session_id=" +
            encodeURIComponent(sessionId)
        );
    }

    async function loadSidebarChatHistory(
        searchValue = ""
    ) {
        historyBox.innerHTML = `
            <div style="
                font-size:12px;
                color:#777;
                padding:8px;
            ">
                Loading chat history...
            </div>
        `;

        const query = searchValue
            ? `?search=${encodeURIComponent(searchValue)}`
            : "";

        const response = await api(
            `/customer/api/chat/sessions${query}`
        );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            historyBox.innerHTML = `
                <div style="
                    font-size:12px;
                    color:#dc3545;
                    padding:8px;
                ">
                    Could not load chat history.
                </div>
            `;

            return;
        }

        const sessions = (
            response.data.sessions || []
        );

        if (sessions.length === 0) {
            historyBox.innerHTML = `
                <div style="
                    font-size:12px;
                    color:#777;
                    padding:8px;
                ">
                    No chat history yet.
                </div>
            `;

            return;
        }

        historyBox.innerHTML = sessions
            .map(function (session) {
                const title =
                    session.title ||
                    session.issue_type ||
                    "IT Support Chat";

                const status =
                    session.ticket_status ||
                    session.status ||
                    "Active";

                const label = session.ticket_number
                    ? `Ticket #${session.ticket_number}`
                    : `Chat ${session.id}`;

                return `
                    <a
                        href="${buildChatUrl(session.id)}"
                        class="sidebar-chat-history-item"
                        data-session-id="${session.id}"
                        style="
                            display:block;
                            padding:9px 10px;
                            margin-bottom:7px;
                            border:1px solid #e5e7eb;
                            border-radius:8px;
                            background:#fff;
                            text-decoration:none;
                            color:#111827;
                        "
                    >
                        <div style="
                            font-size:13px;
                            font-weight:600;
                            white-space:nowrap;
                            overflow:hidden;
                            text-overflow:ellipsis;
                        ">
                            ${escapeHtml(title)}
                        </div>

                        <div style="
                            margin-top:4px;
                            font-size:11px;
                            color:#6b7280;
                            display:flex;
                            justify-content:space-between;
                            gap:8px;
                        ">
                            <span>
                                ${escapeHtml(label)}
                            </span>

                            <span>
                                ${escapeHtml(status)}
                            </span>
                        </div>
                    </a>
                `;
            })
            .join("");
    }

    if (searchBox) {
        let searchTimer = null;

        searchBox.addEventListener(
            "input",
            function () {
                clearTimeout(searchTimer);

                searchTimer = setTimeout(
                    function () {
                        loadSidebarChatHistory(
                            (
                                searchBox.value ||
                                ""
                            ).trim()
                        );
                    },
                    250
                );
            }
        );
    }

    window.addEventListener(
        "livechat:soft-refresh",
        function () {
            loadSidebarChatHistory(
                searchBox
                    ? searchBox.value.trim()
                    : ""
            );
        }
    );

    window.addEventListener(
        "customer-rating-updated",
        function () {
            loadSidebarChatHistory(
                searchBox
                    ? searchBox.value.trim()
                    : ""
            );
        }
    );

    loadSidebarChatHistory();
})();