// static/js/customer_support_box.js

(function () {
    console.log("✅ customer_support_box.js loaded");

    const embeddedRoot = document.getElementById("support-widget-embedded");
    const isEmbeddedMode = !!embeddedRoot;
    const root =
        embeddedRoot ||
        document.getElementById("support-widget-root") ||
        document.body;

    let currentTicketId = null;
    let currentTicketNumber = null;
    let currentUserId = null;
    let isAuthenticated = false;
    let currentTicketClosed = false;
    let pendingSupportStart = false;
    let lastOriginalMessage = "";
    let lastLocalProgressMessage = "";
    let lastLocalProgressTime = 0;

    let currentLanguage = localStorage.getItem("chatbot_chat_language") || "en";

    const TEXT = {
        en: {
            title: "Customer Support",
            loading: "Loading...",
            login: "Login",
            support: "Support",
            input: "Type your message...",
            send: "Send",
            aiOnline: "AI assistant online",
            hello: "Hello 👋 Ask a question or click Support if you need help from an agent.",
            helloShort: "Hello 👋 Ask a question to begin.",
            faqTitle: "Related FAQ Suggestions",
            faqInstruction: "Please choose the question that best matches your issue.",
            solvedQuestion: "Did this solve your issue?",
            yes: "Yes",
            no: "No",
            thankYou: "✅ Thank you. I’m glad your issue was solved. You can start a new chat anytime.",
            noAnswer: "No answer available.",
            maintenanceTitle: "System Maintenance",
            maintenanceMessage: "The chatbot is currently under maintenance.",
            aiUnavailable: "AI temporarily unavailable.",
            needMoreHelp: "Need more help?",
            connectHuman: "I can connect you to a human support agent.",
            talkHuman: "Talk to Human Support",
            loginRequired: "Login required",
            loginHuman: "Please login to continue with human support.",
            loginSupport: "Please login or sign up to talk to a support agent.",
            connectSupportFail: "Could not connect to support.",
            connectFirst: "Please connect to support first.",
            uploadFail: "Upload failed.",
            messageFail: "Message failed to send.",
            ticketClosed: "This ticket is closed.",
            reopenFail: "Could not reopen ticket.",
            confirmFail: "Could not confirm ticket.",
            openFaqFail: "Could not open this FAQ answer."
        },
        ne: {
            title: "ग्राहक सहायता",
            loading: "लोड हुँदैछ...",
            login: "लगइन",
            support: "सहायता",
            input: "आफ्नो सन्देश लेख्नुहोस्...",
            send: "पठाउनुहोस्",
            aiOnline: "AI सहायक अनलाइन छ",
            hello: "नमस्ते 👋 प्रश्न सोध्नुहोस् वा एजेन्टसँग कुरा गर्न Support थिच्नुहोस्।",
            helloShort: "नमस्ते 👋 सुरु गर्न प्रश्न सोध्नुहोस्।",
            faqTitle: "सम्बन्धित FAQ सुझावहरू",
            faqInstruction: "कृपया तपाईंको समस्यासँग मिल्ने प्रश्न छान्नुहोस्।",
            solvedQuestion: "के यसले तपाईंको समस्या समाधान गर्‍यो?",
            yes: "हो",
            no: "होइन",
            thankYou: "✅ धन्यवाद। तपाईंको समस्या समाधान भएकोमा खुशी लाग्यो। तपाईं फेरि नयाँ च्याट सुरु गर्न सक्नुहुन्छ।",
            noAnswer: "उत्तर उपलब्ध छैन।",
            maintenanceTitle: "सिस्टम मर्मत",
            maintenanceMessage: "च्याटबोट अहिले मर्मतमा छ।",
            aiUnavailable: "AI अहिले उपलब्ध छैन।",
            needMoreHelp: "थप सहयोग चाहिन्छ?",
            connectHuman: "म तपाईंलाई मानव सपोर्ट एजेन्टसँग जोड्न सक्छु।",
            talkHuman: "मानव सपोर्टसँग कुरा गर्नुहोस्",
            loginRequired: "लगइन आवश्यक छ",
            loginHuman: "मानव सपोर्ट जारी राख्न कृपया लगइन गर्नुहोस्।",
            loginSupport: "सपोर्ट एजेन्टसँग कुरा गर्न कृपया लगइन वा साइन अप गर्नुहोस्।",
            connectSupportFail: "सपोर्टमा जडान गर्न सकिएन।",
            connectFirst: "कृपया पहिले सपोर्टमा जडान गर्नुहोस्।",
            uploadFail: "अपलोड असफल भयो।",
            messageFail: "सन्देश पठाउन असफल भयो।",
            ticketClosed: "यो टिकट बन्द छ।",
            reopenFail: "टिकट फेरि खोल्न सकिएन।",
            confirmFail: "टिकट पुष्टि गर्न सकिएन।",
            openFaqFail: "यो FAQ उत्तर खोल्न सकिएन।"
        }
    };

    function t(key) {
        return (TEXT[currentLanguage] && TEXT[currentLanguage][key]) || TEXT.en[key] || key;
    }

    const supportTabId =
        "tab_" + Date.now() + "_" + Math.random().toString(36).substring(2);

    const supportSyncChannel =
        "BroadcastChannel" in window
            ? new BroadcastChannel("chatbot_customer_support_sync")
            : null;

    const processedSyncKeys = new Set();

    const socket = LiveChatCore.initSocket();

    const launcher = document.createElement("button");
    launcher.id = "support-widget-launcher";
    launcher.innerHTML = "💬";

    if (isEmbeddedMode) {
        launcher.style.display = "none";
    }

    const panel = document.createElement("div");
    panel.id = "support-widget-panel";

    if (isEmbeddedMode) {
        panel.classList.add("open");
    }

    panel.innerHTML = `
        <div class="support-widget-shell">
            <div class="support-widget-header">
                <div>
                    <div class="support-widget-title" id="supportWidgetTitle">${t("title")}</div>
                    <div class="support-widget-subtitle" id="supportConnectionStatus">
                        ${t("loading")}
                    </div>
                </div>

                <div class="support-widget-header-actions">
                    <button id="supportLoginBtn" class="support-widget-header-btn" type="button">
                        ${t("login")}
                    </button>

                    <button id="supportLanguageBtn" class="support-widget-header-btn support-language-btn" type="button">
                        ${currentLanguage === "ne" ? "नेपाली" : "EN"}
                    </button>

                    <button id="supportHeaderSupportBtn" class="support-widget-header-btn" type="button">
                        ${t("support")}
                    </button>

                    ${isEmbeddedMode
            ? ""
            : `
                                <button id="supportCloseBtn" class="support-widget-header-btn" type="button">
                                    ✕
                                </button>
                            `
        }
                </div>
            </div>

            <div class="support-widget-messages" id="supportMessages"></div>

            <div class="support-widget-ticket-bar" id="supportTicketBar" style="display:none;">
                <div id="supportTicketText"></div>

                <div class="support-ticket-actions" id="supportClosedActions" style="display:none;">
                    <button type="button" id="supportReopenBtn" class="support-mini-btn">
                        ${t("yes")}, reopen
                    </button>

                    <button type="button" id="supportSolvedBtn" class="support-mini-btn support-mini-btn-success">
                        ${t("yes")}, solved
                    </button>
                </div>
            </div>

            <div class="support-widget-footer">
                <div class="support-upload-row">
                    <input
                        type="file"
                        id="supportAttachmentInput"
                        hidden
                        accept=".png,.jpg,.jpeg,.gif,.pdf,.doc,.docx"
                    >

                    <button type="button" id="supportAttachmentBtn" class="support-attachment-btn">
                        📎
                    </button>

                    <textarea id="supportInput" placeholder="${t("input")}" rows="1"></textarea>

                    <button type="button" id="supportSendBtn">
                        ${t("send")}
                    </button>
                </div>
            </div>
        </div>
    `;

    root.appendChild(launcher);
    root.appendChild(panel);

    const supportMessages = document.getElementById("supportMessages");
    const supportInput = document.getElementById("supportInput");
    const supportSendBtn = document.getElementById("supportSendBtn");
    const supportCloseBtn = document.getElementById("supportCloseBtn");
    const supportLoginBtn = document.getElementById("supportLoginBtn");
    const supportLanguageBtn = document.getElementById("supportLanguageBtn");
    const supportWidgetTitle = document.getElementById("supportWidgetTitle");
    const supportHeaderSupportBtn = document.getElementById("supportHeaderSupportBtn");
    const supportAttachmentBtn = document.getElementById("supportAttachmentBtn");
    const supportAttachmentInput = document.getElementById("supportAttachmentInput");
    const supportConnectionStatus = document.getElementById("supportConnectionStatus");
    const supportTicketBar = document.getElementById("supportTicketBar");
    const supportTicketText = document.getElementById("supportTicketText");
    const supportClosedActions = document.getElementById("supportClosedActions");
    const supportReopenBtn = document.getElementById("supportReopenBtn");
    const supportSolvedBtn = document.getElementById("supportSolvedBtn");

    function openWidget() {
        panel.classList.add("open");

        setTimeout(function () {
            LiveChatCore.scrollBottom(supportMessages);
        }, 100);
    }

    function closeWidget() {
        panel.classList.remove("open");
    }

    function clearMessages() {
        supportMessages.innerHTML = "";
        LiveChatCore.clearRenderedEvents();
    }

    function setConnectionText(text) {
        if (supportConnectionStatus) {
            supportConnectionStatus.innerText = text;
        }
    }

    function refreshStaticLanguageText() {
        if (supportWidgetTitle) {
            supportWidgetTitle.innerText = t("title");
        }

        if (supportLoginBtn) {
            supportLoginBtn.innerText = t("login");
        }

        if (supportHeaderSupportBtn) {
            supportHeaderSupportBtn.innerText = t("support");
        }

        if (supportLanguageBtn) {
            supportLanguageBtn.innerText = currentLanguage === "ne" ? "नेपाली" : "EN";
        }

        if (supportInput) {
            supportInput.placeholder = t("input");
        }

        if (supportSendBtn) {
            supportSendBtn.innerText = t("send");
        }

        if (!currentTicketId && !currentTicketClosed) {
            setConnectionText(t("aiOnline"));
        }
    }

    function disableInput(disabled) {
        supportInput.disabled = disabled;
        supportSendBtn.disabled = disabled;
        supportAttachmentBtn.disabled = disabled;
    }

    function addMessage(message, side, name, type = "normal", html = false, createdAt = null) {
        return LiveChatCore.addChatBubble({
            container: supportMessages,
            message: message,
            side: side,
            name: name || "",
            type: type,
            html: html,
            created_at: createdAt
        });
    }

    function addSystemMessage(message) {
        return addMessage(
            message,
            "left",
            "System",
            "system",
            true
        );
    }

    function removeFaqCards() {
        document.querySelectorAll(".faq-suggestion-wrap").forEach(function (card) {
            card.remove();
        });
    }

    function removeResolutionPrompt() {
        document.querySelectorAll(".faq-resolution-wrap").forEach(function (prompt) {
            prompt.remove();
        });
    }

    function removeHumanPrompt() {
        document.querySelectorAll(".human-support-wrap").forEach(function (prompt) {
            prompt.remove();
        });
    }

    function removeTemporaryPrompts() {
        removeFaqCards();
        removeResolutionPrompt();
        removeHumanPrompt();
    }

    function showThankYouEndChat(message) {
        removeTemporaryPrompts();

        addSystemMessage(
            message ||
            "✅ Thank you. I’m glad your issue was solved. You can start a new chat anytime."
        );
    }

    function showHumanSupportButton(originalMessage) {
        removeResolutionPrompt();
        removeHumanPrompt();

        const wrap = document.createElement("div");
        wrap.className = "human-support-wrap";

        wrap.innerHTML = `
            <div class="chat-row chat-left">
                <div class="chat-bubble system-bubble">
                    <strong>${t("needMoreHelp")}</strong>

                    <div style="margin-top:6px;">
                        ${t("connectHuman")}
                    </div>

                    <button
                        type="button"
                        class="support-escalate-btn faq-human-support-btn"
                        style="margin-top:10px;"
                    >
                        ${t("talkHuman")}
                    </button>
                </div>
            </div>
        `;

        supportMessages.appendChild(wrap);

        const btn = wrap.querySelector(".faq-human-support-btn");

        btn.addEventListener("click", async function () {
            btn.disabled = true;
            btn.innerText = "Connecting...";

            await startSupportWithMessage(
                originalMessage ||
                lastOriginalMessage ||
                "Customer requested human support."
            );
        });

        LiveChatCore.scrollBottom(supportMessages);
    }

    function makeSyncKey(type, message, extra = "") {
        return `${type}_${message}_${extra}`;
    }

    function alreadyProcessedSync(key) {
        if (!key) return false;

        if (processedSyncKeys.has(key)) {
            return true;
        }

        processedSyncKeys.add(key);

        setTimeout(function () {
            processedSyncKeys.delete(key);
        }, 10000);

        return false;
    }

    function broadcastSupportSync(type, payload) {
        if (!supportSyncChannel) return;

        supportSyncChannel.postMessage({
            type: type,
            payload: payload || {},
            source_tab_id: supportTabId,
            created_at: Date.now()
        });
    }

    function showSyncedSystemMessage(message, key, shouldBroadcast = true) {
        if (!message) return;

        const syncKey = key || makeSyncKey("system", message);

        if (alreadyProcessedSync(syncKey)) {
            return;
        }

        addSystemMessage(message);

        if (shouldBroadcast) {
            broadcastSupportSync("system_message", {
                key: syncKey,
                message: message
            });
        }
    }

    if (supportSyncChannel) {
        supportSyncChannel.onmessage = function (event) {
            const data = event.data || {};

            if (data.source_tab_id === supportTabId) {
                return;
            }

            if (data.type === "system_message") {
                const payload = data.payload || {};

                removeResolutionPrompt();

                showSyncedSystemMessage(
                    payload.message,
                    payload.key,
                    false
                );
            }

            if (data.type === "refresh_customer_chat") {
                restoreActiveTicket();
            }
        };
    }

    function showResolutionPrompt(sourceType, originalMessage) {
        removeResolutionPrompt();
        removeHumanPrompt();

        lastOriginalMessage = originalMessage || lastOriginalMessage || "";

        const wrap = document.createElement("div");
        wrap.className = "faq-resolution-wrap";

        wrap.innerHTML = `
            <div class="chat-row chat-left">
                <div class="chat-bubble system-bubble">
                    <strong>${t("solvedQuestion")}</strong>

                    <div style="margin-top:10px;">
                        <button type="button" class="support-mini-btn support-mini-btn-success faq-resolved-yes">
                            Yes
                        </button>

                        <button type="button" class="support-mini-btn faq-resolved-no">
                            No
                        </button>
                    </div>
                </div>
            </div>
        `;

        supportMessages.appendChild(wrap);

        const yesBtn = wrap.querySelector(".faq-resolved-yes");
        const noBtn = wrap.querySelector(".faq-resolved-no");

        yesBtn.addEventListener("click", async function () {
            yesBtn.disabled = true;
            noBtn.disabled = true;

            const response = await LiveChatCore.sendResolutionResult(
                true,
                sourceType,
                originalMessage || lastOriginalMessage
            );

            if (response.ok && response.data && response.data.message) {
                resetWidgetState(response.data.message);

                setTimeout(async function () {
                    await loadAiHistory();
                }, 800);

                return;
            }

            await LiveChatCore.clearChatHistory();
            showThankYouEndChat();
        });

        noBtn.addEventListener("click", async function () {
            yesBtn.disabled = true;
            noBtn.disabled = true;

            removeResolutionPrompt();

            const response = await LiveChatCore.sendResolutionResult(
                false,
                sourceType,
                originalMessage || lastOriginalMessage
            );

            if (
                sourceType === "faq" &&
                response.ok &&
                response.data &&
                response.data.next_step === "ai"
            ) {
                if (response.data.message) {
                    lastLocalProgressMessage = response.data.message;
                    lastLocalProgressTime = Date.now();

                    showSyncedSystemMessage(
                        response.data.message,
                        makeSyncKey(
                            "resolution_progress",
                            response.data.message,
                            originalMessage || lastOriginalMessage
                        ),
                        true
                    );
                }

                const aiResponse = await LiveChatCore.sendAiMessage(
                    originalMessage ||
                    lastOriginalMessage ||
                    "The FAQ did not solve my issue.",
                    {
                        skip_faq: true,
                        language: currentLanguage
                    }
                );

                if (!aiResponse.ok || !aiResponse.data) {
                    showHumanSupportButton(originalMessage || lastOriginalMessage);
                    return;
                }

                if (!isAuthenticated && aiResponse.data.reply) {
                    addMessage(
                        aiResponse.data.reply,
                        "left",
                        "AI Assistant",
                        "normal",
                        true
                    );
                }

                if (aiResponse.data.ask_resolved === true) {
                    showResolutionPrompt(
                        "ai",
                        aiResponse.data.original_message ||
                        originalMessage ||
                        lastOriginalMessage
                    );
                    return;
                }

                if (aiResponse.data.needs_human === true) {
                    showHumanSupportButton(
                        aiResponse.data.original_message ||
                        originalMessage ||
                        lastOriginalMessage
                    );
                    return;
                }

                return;
            }

            showHumanSupportButton(originalMessage || lastOriginalMessage);
        });

        LiveChatCore.scrollBottom(supportMessages);
    }

    function showFaqSuggestions(faqs, originalMessage) {
        removeFaqCards();
        removeResolutionPrompt();
        removeHumanPrompt();

        lastOriginalMessage = originalMessage || lastOriginalMessage || "";

        const wrap = document.createElement("div");
        wrap.className = "faq-suggestion-wrap";

        let cards = `
            <div class="chat-row chat-left">
                <div class="chat-bubble customer-bubble">
                    <strong>${t("faqTitle")}</strong>

                    <div style="margin-top:6px; margin-bottom:8px;">
                        ${t("faqInstruction")}
                    </div>
        `;

        (faqs || []).forEach(function (faq, index) {
            cards += `
                <button
                    type="button"
                    class="faq-suggestion-card"
                    data-index="${index}"
                    style="
                        display:block;
                        width:100%;
                        text-align:left;
                        border:1px solid #d1d5db;
                        background:#ffffff;
                        border-radius:10px;
                        padding:10px;
                        margin-top:8px;
                        cursor:pointer;
                        color:#111827;
                    "
                >
                    <strong>${LiveChatCore.escapeHtml(faq.question || "FAQ")}</strong>

                    ${faq.category
                    ? `<div style="font-size:11px; color:#6b7280; margin-top:4px;">${LiveChatCore.escapeHtml(faq.category)}</div>`
                    : ""
                }
                </button>
            `;
        });

        cards += `
                </div>
            </div>
        `;

        wrap.innerHTML = cards;
        supportMessages.appendChild(wrap);

        const buttons = wrap.querySelectorAll(".faq-suggestion-card");

        buttons.forEach(function (button) {
            button.addEventListener("click", async function () {
                const index = Number(button.getAttribute("data-index"));
                const faq = faqs[index];

                if (!faq) return;

                removeFaqCards();

                const response = await LiveChatCore.saveSelectedFaq(
                    faq.question,
                    faq.answer || "No answer available.",
                    originalMessage || lastOriginalMessage
                );

                if (!response.ok || !response.data || response.data.ok !== true) {
                    addSystemMessage("Could not open this FAQ answer.");
                    return;
                }

                if (!isAuthenticated) {
                    addMessage(
                        faq.question,
                        "right",
                        "You",
                        "normal",
                        false
                    );

                    addMessage(
                        faq.answer || "No answer available.",
                        "left",
                        "FAQ Answer",
                        "normal",
                        true
                    );

                    showResolutionPrompt(
                        "faq",
                        originalMessage || lastOriginalMessage
                    );
                }
            });
        });

        LiveChatCore.scrollBottom(supportMessages);
    }

    function showTicketBar() {
        if (!currentTicketId) {
            supportTicketBar.style.display = "none";
            return;
        }

        supportTicketBar.style.display = "flex";

        if (currentTicketClosed) {
            supportTicketText.innerText = `Ticket #${currentTicketNumber} closed`;
            supportClosedActions.style.display = "flex";
        } else {
            supportTicketText.innerText = `Connected to Ticket #${currentTicketNumber}`;
            supportClosedActions.style.display = "none";
        }
    }

    function resetWidgetState(message) {
        currentTicketId = null;
        currentTicketNumber = null;
        currentTicketClosed = false;
        pendingSupportStart = false;

        clearMessages();

        supportTicketBar.style.display = "none";

        disableInput(false);
        setConnectionText(t("aiOnline"));

        addSystemMessage(
            message ||
            "Support conversation finished. You can start a new chat anytime."
        );
    }

    function loginRedirect() {
        const next = window.location.pathname + window.location.search;
        window.location.href = "/login?next=" + encodeURIComponent(next);
    }

    async function loadCurrentUser() {
        const response = await LiveChatCore.fetchMe();

        if (!response.ok || !response.data) {
            return;
        }

        isAuthenticated = response.data.is_authenticated === true;
        currentUserId = response.data.user_id || null;

        if (supportLoginBtn) {
            supportLoginBtn.style.display = isAuthenticated ? "none" : "inline-block";
        }

        if (currentUserId) {
            LiveChatCore.joinNotificationRoom(currentUserId);
        }
    }

    function renderAiHistoryMessages(messages) {
        (messages || []).forEach(function (msg) {
            LiveChatCore.renderChatMessage(
                supportMessages,
                msg,
                currentUserId
            );
        });
    }

    async function loadAiHistory() {
        clearMessages();

        const response = await LiveChatCore.fetchChatHistory();

        if (!response.ok || !response.data || !response.data.messages) {
            addSystemMessage(t("helloShort"));
            return;
        }

        const messages = response.data.messages || [];

        if (messages.length === 0) {
            addSystemMessage(
                t("hello")
            );
            return;
        }

        renderAiHistoryMessages(messages);
        setConnectionText("AI assistant online");

        if (response.data.needs_resolution_prompt === true) {
            showResolutionPrompt(
                response.data.source_type || "ai",
                response.data.original_message || lastOriginalMessage
            );
        }
    }

    async function appendAiHistoryWithoutClearing() {
        const response = await LiveChatCore.fetchChatHistory();

        if (!response.ok || !response.data || !response.data.messages) {
            return;
        }

        renderAiHistoryMessages(response.data.messages || []);
    }

    async function restoreActiveTicket() {
        const response = await LiveChatCore.fetchActiveTicket();

        if (!response.ok || !response.data || response.data.has_active !== true) {
            currentTicketId = null;
            currentTicketNumber = null;
            currentTicketClosed = false;

            await loadAiHistory();

            disableInput(false);
            setConnectionText("AI assistant online");
            showTicketBar();

            return;
        }

        currentTicketId = response.data.ticket_id;
        currentTicketNumber = response.data.ticket_number;
        currentTicketClosed = String(response.data.status || "").toLowerCase() === "closed";

        LiveChatCore.joinTicketRoom(currentTicketId);

        clearMessages();

        if (currentTicketClosed) {
            disableInput(true);
            setConnectionText("Ticket closed");

            supportTicketBar.style.display = "flex";
            supportTicketText.innerText = `Ticket #${currentTicketNumber} closed`;
            supportClosedActions.style.display = "flex";

            addSystemMessage(
                "This ticket has been closed by support. Was your issue solved?"
            );

            return;
        }

        await appendAiHistoryWithoutClearing();
        await appendTicketMessagesWithoutClearing();

        showTicketBar();
    }

    async function loadTicketMessages() {
        if (!currentTicketId) return;

        clearMessages();

        await appendAiHistoryWithoutClearing();
        await appendTicketMessagesWithoutClearing();
    }

    async function appendTicketMessagesWithoutClearing() {
        if (!currentTicketId) return;

        const response = await LiveChatCore.fetchTicketComments(currentTicketId);

        if (!response.ok || !response.data || response.data.ok !== true) {
            resetWidgetState("Ticket no longer available.");
            return;
        }

        const ticket = response.data.ticket;

        if (ticket) {
            currentTicketNumber = ticket.ticket_number;
            currentTicketClosed = String(ticket.status || "").toLowerCase() === "closed";
        }

        const comments = response.data.comments || [];

        comments.forEach(function (comment) {
            LiveChatCore.renderCommentEvent(
                supportMessages,
                {
                    ticket_id: currentTicketId,
                    comment_id: comment.id,
                    message: comment.message,
                    sender_name: comment.author,
                    sender_role: comment.role,
                    author_id: comment.author_id,
                    created_at: comment.created_at,
                    is_attachment:
                        String(comment.message || "").includes("<a ") ||
                        String(comment.message || "").includes("<strong>") ||
                        String(comment.message || "").includes("<br")
                },
                currentUserId
            );
        });

        disableInput(currentTicketClosed);

        setConnectionText(
            currentTicketClosed ? "Ticket closed" : "Live support connected"
        );

        showTicketBar();
    }

    async function sendMessage() {
        const message = (supportInput.value || "").trim();

        if (!message) return;

        supportInput.value = "";

        if (currentTicketClosed) {
            addSystemMessage("This ticket is closed.");
            return;
        }

        removeTemporaryPrompts();

        if (currentTicketId) {
            const response = await LiveChatCore.sendTicketComment(
                currentTicketId,
                message
            );

            if (!response.ok || !response.data || response.data.ok !== true) {
                addSystemMessage("Message failed to send.");
            }

            return;
        }

        lastOriginalMessage = message;
        if (!isAuthenticated) {
            addMessage(
                message,
                "right",
                "You",
                "normal",
                false
            );
        }


        const response = await LiveChatCore.sendAiMessage(message, {
            language: currentLanguage
        });

        if (!response.ok || !response.data) {
            addSystemMessage("AI temporarily unavailable.");
            showHumanSupportButton(message);
            return;
        }

        const data = response.data;

        if (data.maintenance === true) {
            addSystemMessage(
                "<strong>" +
                LiveChatCore.escapeHtml(data.maintenance_title || "System Maintenance") +
                "</strong><br>" +
                LiveChatCore.escapeHtml(data.reply || "The chatbot is currently under maintenance.")
            );

            if (data.needs_human === true) {
                showHumanSupportButton(data.original_message || message);
            }

            return;
        }

        if (data.type === "faq_suggestions") {
            showFaqSuggestions(data.faqs || [], data.original_message || message);
            return;
        }

        if (data.ask_resolved === true) {
            showResolutionPrompt("ai", data.original_message || message);
        }

        if (data.needs_human === true) {
            showHumanSupportButton(data.original_message || message);
        }
    }

    function showGuestLoginButton() {
        removeHumanPrompt();

        const wrap = document.createElement("div");
        wrap.className = "human-support-wrap";

        wrap.innerHTML = `
        <div class="chat-row chat-left">
            <div class="chat-bubble system-bubble">
                <strong>Login required</strong>

                <div style="margin-top:6px;">
                    Please login to continue with human support.
                </div>

                <button
                    type="button"
                    class="support-escalate-btn guest-login-btn"
                    style="margin-top:10px;"
                >
                    Login
                </button>
            </div>
        </div>
    `;

        supportMessages.appendChild(wrap);

        const btn = wrap.querySelector(".guest-login-btn");

        btn.addEventListener("click", function () {
            loginRedirect();
        });

        LiveChatCore.scrollBottom(supportMessages);
    }
    async function startSupportWithMessage(message) {
        if (!isAuthenticated) {
            addSystemMessage(
                "Please login or sign up to talk to a support agent."
            );

            showGuestLoginButton();
            return;
        }

        if (currentTicketId) {
            addSystemMessage(`Already connected to ticket #${currentTicketNumber}`);
            return;
        }

        pendingSupportStart = true;

        const response = await LiveChatCore.escalateSupport(
            message ||
            lastOriginalMessage ||
            "Customer requested support."
        );

        pendingSupportStart = false;

        if (!response.ok || !response.data) {
            addSystemMessage("Could not connect to support.");
            return;
        }

        if (response.data.needs_login === true) {
            addSystemMessage(
                response.data.reply ||
                "Please login first to talk to support."
            );
            return;
        }

        currentTicketId = response.data.ticket_id;
        currentTicketNumber = response.data.ticket_number;
        currentTicketClosed = false;

        LiveChatCore.joinTicketRoom(currentTicketId);

        removeTemporaryPrompts();

        disableInput(false);
        setConnectionText("Live support connected");
        showTicketBar();

        await loadTicketMessages();

        addSystemMessage(
            response.data.reply ||
            `Ticket #${currentTicketNumber} created. Waiting for a support agent to join...`
        );
    }

    async function startSupport() {
        return startSupportWithMessage(
            lastOriginalMessage ||
            "Customer requested support."
        );
    }

    async function uploadAttachment(file) {
        if (!file) return;

        if (!currentTicketId) {
            addSystemMessage("Please connect to support first.");
            return;
        }

        const response = await LiveChatCore.uploadAttachment(
            currentTicketId,
            file
        );

        if (!response.ok || !response.data || response.data.ok !== true) {
            addSystemMessage("Upload failed.");
        }
    }

    async function reopenTicket() {
        if (!currentTicketId) return;

        const response = await LiveChatCore.reopenTicket(currentTicketId);

        if (!response.ok || !response.data || response.data.ok !== true) {
            addSystemMessage("Could not reopen ticket.");
            return;
        }

        currentTicketClosed = false;

        disableInput(false);
        setConnectionText("Ticket reopened");

        await loadTicketMessages();
    }

    async function markSolved() {
        if (!currentTicketId) return;

        const response = await LiveChatCore.confirmSolved(currentTicketId);

        if (!response.ok || !response.data || response.data.ok !== true) {
            addSystemMessage("Could not confirm ticket.");
            return;
        }

        resetWidgetState(
            response.data.message ||
            "Issue solved successfully."
        );
    }

    socket.on("connect", async function () {
        if (currentUserId) {
            LiveChatCore.joinNotificationRoom(currentUserId);
        }

        if (currentTicketId) {
            LiveChatCore.joinTicketRoom(currentTicketId);
            await loadTicketMessages();
        }
    });

    socket.on("customer_ai_message", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        if (currentTicketId) {
            return;
        }

        if (data.chat) {
            LiveChatCore.renderChatMessage(
                supportMessages,
                data.chat,
                currentUserId
            );
        }

        if (data.ask_resolved === true) {
            showResolutionPrompt(
                "ai",
                data.original_message || lastOriginalMessage
            );
        }

        if (data.needs_human === true) {
            showHumanSupportButton(
                data.original_message || lastOriginalMessage
            );
        }
    });

    socket.on("customer_faq_suggestions", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        if (currentTicketId) {
            return;
        }

        showFaqSuggestions(
            data.faqs || [],
            data.original_message || ""
        );
    });

    socket.on("customer_faq_answer", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        if (currentTicketId) {
            return;
        }

        removeFaqCards();

        if (data.question_chat) {
            LiveChatCore.renderChatMessage(
                supportMessages,
                data.question_chat,
                currentUserId
            );
        } else if (data.question) {
            addMessage(
                data.question,
                "right",
                "You",
                "normal",
                false
            );
        }

        if (data.answer_chat) {
            LiveChatCore.renderChatMessage(
                supportMessages,
                data.answer_chat,
                currentUserId
            );
        } else if (data.answer) {
            addMessage(
                data.answer,
                "left",
                "FAQ Answer",
                "normal",
                true
            );
        }

        if (data.ask_resolved === true) {
            showResolutionPrompt(
                "faq",
                data.original_message ||
                data.question ||
                lastOriginalMessage
            );
        }
    });

    socket.on("customer_resolution_progress", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        removeResolutionPrompt();

        const incomingMessage = data.message || "";

        if (incomingMessage) {
            showSyncedSystemMessage(
                incomingMessage,
                makeSyncKey(
                    "resolution_progress",
                    incomingMessage,
                    data.original_message || lastOriginalMessage
                ),
                true
            );
        }
    });

    socket.on("customer_human_prompt", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        if (currentTicketId) {
            return;
        }

        showHumanSupportButton(
            data.original_message || lastOriginalMessage
        );
    });

    socket.on("customer_chat_cleared", function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        resetWidgetState(
            data.message ||
            "Chat cleared. You can start a new chat anytime."
        );
    });

    socket.on("customer_live_refresh", async function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        await restoreActiveTicket();
    });

    socket.on("new_comment", async function (data) {
        if (!data || !data.message) return;

        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        if (!currentTicketId && data.ticket_id) {
            return;
        }

        LiveChatCore.renderCommentEvent(
            supportMessages,
            data,
            currentUserId
        );

        await appendTicketMessagesWithoutClearing();
    });

    socket.on("ticket_closed", async function (data) {
        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        currentTicketClosed = true;

        clearMessages();

        disableInput(true);
        setConnectionText("Ticket closed");

        supportTicketBar.style.display = "flex";
        supportTicketText.innerText =
            `Ticket #${currentTicketNumber || data.ticket_number || ""} closed`;

        supportClosedActions.style.display = "flex";

        addSystemMessage(
            "This ticket has been closed by support. Was your issue solved?"
        );
    });

    socket.on("ticket_reopened", async function (data) {
        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        currentTicketClosed = false;

        disableInput(false);
        setConnectionText("Ticket reopened");
        showTicketBar();

        await loadTicketMessages();
    });

    socket.on("ticket_confirmed_solved", async function (data) {
        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        resetWidgetState(
            data.message ||
            "✅ Thank you. Your issue has been marked as solved. You can start a new chat anytime."
        );
    });

    socket.on("support_ticket_started", async function (data) {
        if (!data) return;

        if (
            currentUserId &&
            data.user_id &&
            Number(data.user_id) !== Number(currentUserId)
        ) {
            return;
        }

        if (pendingSupportStart) return;

        currentTicketId = data.ticket_id;
        currentTicketNumber = data.ticket_number;
        currentTicketClosed = false;

        LiveChatCore.joinTicketRoom(currentTicketId);

        removeTemporaryPrompts();

        disableInput(false);
        setConnectionText("Live support connected");
        showTicketBar();

        await loadTicketMessages();
    });

    socket.on("agent_joined", async function (data) {
        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        await loadTicketMessages();
    });

    socket.on("ticket_deleted", function (data) {
        if (
            currentTicketId &&
            data.ticket_id &&
            Number(data.ticket_id) !== Number(currentTicketId)
        ) {
            return;
        }

        resetWidgetState(
            data.message ||
            "Ticket was deleted. You can start a new chat anytime."
        );
    });

    launcher.addEventListener("click", openWidget);

    if (supportCloseBtn) {
        supportCloseBtn.addEventListener("click", closeWidget);
    }

    supportSendBtn.addEventListener("click", sendMessage);

    supportInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    supportLanguageBtn.addEventListener("click", async function () {
        currentLanguage = currentLanguage === "en" ? "ne" : "en";
        localStorage.setItem("chatbot_chat_language", currentLanguage);

        refreshStaticLanguageText();

        if (!currentTicketId) {
            await loadAiHistory();
        }
    });

    supportHeaderSupportBtn.addEventListener("click", startSupport);
    supportLoginBtn.addEventListener("click", loginRedirect);

    supportAttachmentBtn.addEventListener("click", function () {
        supportAttachmentInput.click();
    });

    supportAttachmentInput.addEventListener("change", function () {
        const file = supportAttachmentInput.files[0];

        if (file) {
            uploadAttachment(file);
        }

        supportAttachmentInput.value = "";
    });

    supportReopenBtn.addEventListener("click", reopenTicket);
    supportSolvedBtn.addEventListener("click", markSolved);

    window.addEventListener("livechat:soft-refresh", async function () {
        await restoreActiveTicket();
    });

    (async function start() {
        refreshStaticLanguageText();
        await loadCurrentUser();
        await restoreActiveTicket();
    })();

    broadcastSupportSync("refresh_customer_chat", {});
})();