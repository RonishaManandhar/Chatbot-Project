(function () {

    console.log("✅ rebuilt widget.js loaded");

    const ACTIVE_TICKET_KEY = "support_widget_active_ticket_id";

    const embeddedRoot = document.getElementById("support-widget-embedded");

    const isEmbeddedMode = !!embeddedRoot;

    const root =
        embeddedRoot ||
        document.getElementById("support-widget-root") ||
        document.body;

    const btn = document.createElement("button");

    btn.id = "support-widget-button";
    btn.innerText = "💬";

    if (isEmbeddedMode) {
        btn.style.display = "none";
    }

    const panel = document.createElement("div");

    panel.id = "support-widget-panel";

    panel.style.display =
        isEmbeddedMode
            ? "block"
            : "none";

    panel.innerHTML = `
        <div id="support-widget-header">
            <h3>Customer Support</h3>

            <div id="support-widget-header-actions">

                <button id="support-widget-header-login">
                    Login
                </button>

                <button id="support-widget-header-support">
                    Support
                </button>

                <button id="support-widget-close">
                    ×
                </button>

            </div>
        </div>

        <div id="support-widget-messages"></div>

        <div id="support-widget-input-area">

            <input
                id="support-widget-file"
                type="file"
                style="display:none;"
                accept=".png,.jpg,.jpeg,.gif,.pdf,.doc,.docx"
            />

            <button
                id="support-widget-attach"
                type="button"
            >
                📎
            </button>

            <input
                id="support-widget-input"
                type="text"
                placeholder="Type your message..."
            />

            <button
                id="support-widget-send"
                type="button"
            >
                Send
            </button>

        </div>
    `;

    root.appendChild(btn);
    root.appendChild(panel);

    const messagesEl =
        document.getElementById("support-widget-messages");

    const inputEl =
        document.getElementById("support-widget-input");

    const sendBtn =
        document.getElementById("support-widget-send");

    const attachBtn =
        document.getElementById("support-widget-attach");

    const fileInput =
        document.getElementById("support-widget-file");

    const closeBtn =
        document.getElementById("support-widget-close");

    const loginBtn =
        document.getElementById("support-widget-header-login");

    const supportBtn =
        document.getElementById("support-widget-header-support");

    let isAuthenticated = false;

    let activeTicketId = null;

    let historyLoaded = false;

    const socket = LiveChatCore.initSocket();

    function saveActiveTicket(ticketId) {

        activeTicketId = String(ticketId);

        localStorage.setItem(
            ACTIVE_TICKET_KEY,
            activeTicketId
        );
    }

    function clearActiveTicket() {

        activeTicketId = null;

        localStorage.removeItem(
            ACTIVE_TICKET_KEY
        );
    }

    function loadStoredTicket() {

        activeTicketId =
            localStorage.getItem(ACTIVE_TICKET_KEY);

        return activeTicketId;
    }

    function addMessage(text, side = "left", html = false, type = "normal") {

        LiveChatCore.addChatBubble({
            container: messagesEl,
            message: text,
            side: side,
            html: html,
            type: type,
            name:
                side === "right"
                    ? "You"
                    : "Support"
        });
    }

    function clearMessages() {

        messagesEl.innerHTML = "";
    }

    function showTyping() {

        const row = document.createElement("div");

        row.id = "widget-typing";

        row.className = "chat-row chat-left";

        row.innerHTML = `
            <div class="chat-bubble customer-bubble">
                Typing...
            </div>
        `;

        messagesEl.appendChild(row);

        LiveChatCore.scrollBottom(messagesEl);
    }

    function removeTyping() {

        const row =
            document.getElementById("widget-typing");

        if (row) {
            row.remove();
        }
    }

    function loginRedirect() {

        window.location.href =
            "/login?next=/customer/chat";
    }

    function removeResolutionPrompt() {

        const existing =
            document.querySelector(".resolution-actions");

        if (existing) {
            existing.remove();
        }
    }

    function showResolutionPrompt(ticketId) {

        removeResolutionPrompt();

        const wrap = document.createElement("div");

        wrap.className = "resolution-actions";

        wrap.style.marginTop = "10px";

        wrap.innerHTML = `
            <div style="margin-bottom:8px;">
                Did this solve your issue?
            </div>

            <button
                class="support-btn"
                id="widget-solved-btn"
            >
                Yes
            </button>

            <button
                class="support-btn"
                id="widget-reopen-btn"
            >
                No - Reopen
            </button>
        `;

        messagesEl.appendChild(wrap);

        LiveChatCore.scrollBottom(messagesEl);

        document
            .getElementById("widget-solved-btn")
            .onclick = async function () {

                const result =
                    await LiveChatCore.confirmSolved(ticketId);

                if (!result.ok) {

                    addMessage(
                        "Could not confirm solved right now.",
                        "left",
                        false,
                        "system"
                    );

                    return;
                }

                clearActiveTicket();

                removeResolutionPrompt();

                addMessage(
                    "✅ Glad your issue was resolved.",
                    "left",
                    false,
                    "system"
                );

                addMessage(
                    "You can start a new chat anytime.",
                    "left",
                    false,
                    "system"
                );
            };

        document
            .getElementById("widget-reopen-btn")
            .onclick = async function () {

                const result =
                    await LiveChatCore.reopenTicket(ticketId);

                if (!result.ok) {

                    addMessage(
                        "Could not reopen ticket right now.",
                        "left",
                        false,
                        "system"
                    );

                    return;
                }

                removeResolutionPrompt();

                addMessage(
                    "🔄 Your support ticket has been reopened.",
                    "left",
                    false,
                    "system"
                );

                LiveChatCore.joinTicketRoom(ticketId);
            };
    }

    async function loadExistingConversation(ticketId) {

        clearMessages();

        const result =
            await LiveChatCore.fetchTicketComments(ticketId);

        if (!result.ok || !result.data.ok) {

            clearActiveTicket();

            addMessage(
                "Previous ticket no longer exists.",
                "left",
                false,
                "system"
            );

            return;
        }

        LiveChatCore.joinTicketRoom(ticketId);

        addMessage(
            "Connected to your support ticket.",
            "left",
            false,
            "system"
        );

        const comments =
            result.data.comments || [];

        for (const c of comments) {

            const role =
                String(c.role || "").toLowerCase();

            const isCustomer =
                role === "customer";

            const isAttachment =
                String(c.message || "")
                    .includes("Attachment uploaded:");

            addMessage(
                isCustomer
                    ? c.message
                    : `${c.author}: ${c.message}`,
                isCustomer
                    ? "right"
                    : "left",
                isAttachment
            );
        }

        const statusResult =
            await LiveChatCore.fetchTicketStatus(ticketId);

        if (
            statusResult.ok &&
            statusResult.data.ok &&
            String(statusResult.data.status).toLowerCase() === "closed"
        ) {
            showResolutionPrompt(ticketId);
        }
    }

    async function loadAiHistory() {

        clearMessages();

        const result =
            await LiveChatCore.fetchChatHistory();

        if (!result.ok) {

            addMessage(
                "Could not load history.",
                "left",
                false,
                "system"
            );

            return;
        }

        const messages =
            result.data.messages || [];

        if (messages.length === 0) {

            addMessage(
                "Welcome! Ask a question or talk to support.",
                "left",
                false,
                "system"
            );

            return;
        }

        for (const m of messages) {

            const role =
                String(m.role || "").toLowerCase();

            addMessage(
                m.message,
                role === "user"
                    ? "right"
                    : "left"
            );
        }
    }

    async function createSupportTicket(message) {

        const result =
            await LiveChatCore.escalateSupport(message);

        if (!result.ok) {

            addMessage(
                "Could not create support ticket.",
                "left",
                false,
                "system"
            );

            return;
        }

        const data = result.data;

        if (data.needs_login === true) {

            addMessage(
                "Please login first.",
                "left",
                false,
                "system"
            );

            return;
        }

        if (data.ticket_id) {

            saveActiveTicket(data.ticket_id);

            LiveChatCore.joinTicketRoom(
                data.ticket_id
            );
        }

        addMessage(
            data.reply || "Support ticket created.",
            "left",
            false,
            "system"
        );
    }

    async function sendMessage() {

        const text =
            (inputEl.value || "").trim();

        if (!text) {
            return;
        }

        inputEl.value = "";

        removeResolutionPrompt();

        if (activeTicketId) {

            const result =
                await LiveChatCore.sendTicketComment(
                    activeTicketId,
                    text
                );

            if (!result.ok) {

                addMessage(
                    "Could not send message.",
                    "left",
                    false,
                    "system"
                );
            }

            return;
        }

        addMessage(text, "right");

        showTyping();

        const result =
            await LiveChatCore.sendAiMessage(text);

        removeTyping();

        if (!result.ok) {

            addMessage(
                "AI unavailable right now.",
                "left",
                false,
                "system"
            );

            return;
        }

        const data = result.data;

        addMessage(
            data.reply || "No response available.",
            "left"
        );

        if (data.ask_resolved === true) {

            addMessage(
                "Glad I could help.",
                "left",
                false,
                "system"
            );
        }

        if (data.needs_human === true) {

            const btn =
                document.createElement("button");

            btn.className = "support-btn";

            btn.innerText =
                "Talk to Support";

            btn.onclick = async function () {

                btn.remove();

                await createSupportTicket(text);
            };

            messagesEl.appendChild(btn);

            LiveChatCore.scrollBottom(messagesEl);
        }
    }

    async function uploadFile(file) {

        if (!activeTicketId) {

            addMessage(
                "Please enter support chat first.",
                "left",
                false,
                "system"
            );

            return;
        }

        const formData = new FormData();

        formData.append(
            "attachment",
            file
        );

        addMessage(
            "Uploading attachment...",
            "left",
            false,
            "system"
        );

        const result =
            await LiveChatCore.uploadAttachment(
                activeTicketId,
                formData
            );

        if (!result.ok || !result.data.ok) {

            addMessage(
                "Could not upload attachment.",
                "left",
                false,
                "system"
            );

            return;
        }

        addMessage(
            result.data.message,
            "right",
            true
        );
    }

    async function init() {

        const me =
            await LiveChatCore.fetchMe();

        isAuthenticated =
            me.ok &&
            me.data &&
            me.data.is_authenticated === true;

        loadStoredTicket();

        if (isAuthenticated) {

            const active =
                await LiveChatCore.fetchActiveTicket();

            if (
                active.ok &&
                active.data &&
                active.data.has_active === true
            ) {

                saveActiveTicket(
                    active.data.ticket_id
                );

                await loadExistingConversation(
                    active.data.ticket_id
                );

            } else {

                clearActiveTicket();

                await loadAiHistory();
            }

        } else {

            clearMessages();

            addMessage(
                "You are chatting as guest.",
                "left",
                false,
                "system"
            );

            addMessage(
                "Login required for live support.",
                "left",
                false,
                "system"
            );
        }

        historyLoaded = true;
    }

    socket.on("connect", function () {

        if (activeTicketId) {

            LiveChatCore.joinTicketRoom(
                activeTicketId
            );
        }
    });

    socket.on("agent_joined", function (data) {

        if (!data || !data.message) return;

        addMessage(
            data.message,
            "left",
            false,
            "system"
        );
    });

    socket.on("new_comment", function (data) {

        if (!data || !data.message) {
            return;
        }

        const senderRole =
            String(data.sender_role || "").toLowerCase();

        const isCustomer =
            senderRole === "customer";

        addMessage(
            isCustomer
                ? data.message
                : `${data.sender_name}: ${data.message}`,
            isCustomer
                ? "right"
                : "left",
            data.is_attachment === true
        );
    });

    socket.on("ticket_closed", function (data) {

        if (!data || !data.message) return;

        addMessage(
            data.message,
            "left",
            false,
            "system"
        );

        if (activeTicketId) {
            showResolutionPrompt(activeTicketId);
        }
    });

    socket.on("ticket_reopened", function (data) {

        if (!data || !data.message) return;

        addMessage(
            data.message,
            "left",
            false,
            "system"
        );
    });

    btn.addEventListener("click", function () {

        panel.style.display =
            panel.style.display === "block"
                ? "none"
                : "block";
    });

    closeBtn.addEventListener("click", function () {

        panel.style.display = "none";
    });

    sendBtn.addEventListener("click", sendMessage);

    inputEl.addEventListener("keydown", function (e) {

        if (e.key === "Enter") {
            sendMessage();
        }
    });

    attachBtn.addEventListener("click", function () {

        fileInput.click();
    });

    fileInput.addEventListener("change", async function () {

        const file =
            fileInput.files &&
            fileInput.files[0];

        if (!file) return;

        await uploadFile(file);

        fileInput.value = "";
    });

    loginBtn.addEventListener("click", loginRedirect);

    supportBtn.addEventListener("click", async function () {

        if (!isAuthenticated) {

            loginRedirect();

            return;
        }

        if (activeTicketId) {

            addMessage(
                "You already have an active support ticket.",
                "left",
                false,
                "system"
            );

            return;
        }

        await createSupportTicket(
            "Customer requested support."
        );
    });

    init();

})();