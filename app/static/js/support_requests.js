// static/js/support_requests.js

(function () {
    "use strict";

    console.log("✅ support_requests.js loaded");

    let currentUserId = null;
    let currentSessionId = null;
    let currentTicketId = null;
    let currentTicketNumber = null;
    let currentTicketClosed = false;
    let messageSendInProgress = false;

    let triageMode = false;
    let aiConversationMode = false;
    let triageStep = 0;
    let triageQuestions = [];

    let triageData = createEmptyTriageData();

    const socket = LiveChatCore.initSocket();

    const supportMessages =
        document.getElementById("supportMessages");

    const supportInput =
        document.getElementById("supportInput");

    const supportSendBtn =
        document.getElementById("supportSendBtn");

    const supportAttachmentBtn =
        document.getElementById(
            "supportAttachmentBtn"
        );

    const supportAttachmentInput =
        document.getElementById(
            "supportAttachmentInput"
        );

    const newSupportRequestBtn =
        document.getElementById(
            "newSupportRequestBtn"
        );

    const supportHistorySearch =
        document.getElementById(
            "supportHistorySearch"
        );

    const supportRequestHistory =
        document.getElementById(
            "supportRequestHistory"
        );

    const supportChatTitle =
        document.getElementById(
            "supportChatTitle"
        );

    const supportChatSubtitle =
        document.getElementById(
            "supportChatSubtitle"
        );

    const supportTicketMeta =
        document.getElementById(
            "supportTicketMeta"
        );

    const supportStatusBadge =
        document.getElementById(
            "supportStatusBadge"
        );

    const supportPriorityBadge =
        document.getElementById(
            "supportPriorityBadge"
        );

    const supportCategoryBadge =
        document.getElementById(
            "supportCategoryBadge"
        );

    const triageQuestionBank = {
        "Login / Account Access": [
            {
                key: "affected_users",
                question:
                    "Who is affected by this login issue? Only you, multiple users, or the whole team?"
            },
            {
                key: "impact",
                question:
                    "Are you completely unable to log in, or can you access some parts of the system?"
            },
            {
                key: "device",
                question:
                    "Which system, website, application, or device are you trying to access?"
            },
            {
                key: "error_message",
                question:
                    "What exact login error message do you see? If there is no error, type No."
            },
            {
                key: "tried_steps",
                question:
                    "What troubleshooting steps have you already tried?"
            },
            {
                key: "details",
                question:
                    "Please describe the login issue briefly."
            }
        ],

        "Password Reset": [
            {
                key: "affected_users",
                question:
                    "Is this password reset issue affecting only you or multiple users?"
            },
            {
                key: "impact",
                question:
                    "Are you completely locked out, or trying to change your password while logged in?"
            },
            {
                key: "device",
                question:
                    "Which account or system password are you trying to reset?"
            },
            {
                key: "error_message",
                question:
                    "Did you receive a reset email or error message?"
            },
            {
                key: "tried_steps",
                question:
                    "Have you checked spam, requested another link, or tried a different browser?"
            },
            {
                key: "details",
                question:
                    "Please describe the password reset problem briefly."
            }
        ],

        "Email Issue": [
            {
                key: "affected_users",
                question:
                    "Is this affecting only you, multiple users, or the whole team?"
            },
            {
                key: "impact",
                question:
                    "Are you unable to send email, receive email, or both?"
            },
            {
                key: "device",
                question:
                    "Which email application and device are you using?"
            },
            {
                key: "error_message",
                question:
                    "Do you see a bounce-back, login, or synchronisation error?"
            },
            {
                key: "tried_steps",
                question:
                    "What troubleshooting steps have you already tried?"
            },
            {
                key: "details",
                question:
                    "Please describe the email issue briefly."
            }
        ],

        "Network Issue": [
            {
                key: "affected_users",
                question:
                    "Is the network issue affecting only you, multiple users, or everyone?"
            },
            {
                key: "impact",
                question:
                    "Are you completely offline, or is the connection slow or intermittent?"
            },
            {
                key: "device",
                question:
                    "Are you using Wi-Fi, Ethernet, VPN, or a mobile hotspot?"
            },
            {
                key: "error_message",
                question:
                    "Do you see a network, DNS, VPN, or connection error?"
            },
            {
                key: "tried_steps",
                question:
                    "Have you restarted the device, reconnected, or tested another website?"
            },
            {
                key: "details",
                question:
                    "Please describe the network issue briefly."
            }
        ],

        "Software Issue": [
            {
                key: "affected_users",
                question:
                    "Is the software issue affecting only you or multiple users?"
            },
            {
                key: "impact",
                question:
                    "Is the application unusable, crashing, or showing a minor issue?"
            },
            {
                key: "device",
                question:
                    "What application, browser, version, and operating system are affected?"
            },
            {
                key: "error_message",
                question:
                    "What exact error message appears? If none, type No."
            },
            {
                key: "tried_steps",
                question:
                    "Have you restarted, updated, reinstalled, or cleared the cache?"
            },
            {
                key: "details",
                question:
                    "Please describe the software issue briefly."
            }
        ],

        "Hardware Issue": [
            {
                key: "affected_users",
                question:
                    "Is this affecting one device or multiple devices?"
            },
            {
                key: "impact",
                question:
                    "Is the hardware unusable, partly working, or showing a minor issue?"
            },
            {
                key: "device",
                question:
                    "What hardware is affected?"
            },
            {
                key: "error_message",
                question:
                    "Are there warning lights, beeps, messages, or visible damage?"
            },
            {
                key: "tried_steps",
                question:
                    "Have you checked power, cables, ports, and restarted the device?"
            },
            {
                key: "details",
                question:
                    "Please describe the hardware issue briefly."
            }
        ],

        "Security Issue": [
            {
                key: "affected_users",
                question:
                    "Is this affecting one account, multiple users, or the whole team?"
            },
            {
                key: "impact",
                question:
                    "Is this a suspicious login, phishing message, malware warning, or possible data exposure?"
            },
            {
                key: "device",
                question:
                    "Which account, device, email, or system is involved?"
            },
            {
                key: "error_message",
                question:
                    "What warning, suspicious message, or alert did you receive?"
            },
            {
                key: "tried_steps",
                question:
                    "Have you clicked anything, entered credentials, changed your password, or disconnected the device?"
            },
            {
                key: "details",
                question:
                    "Please describe exactly what happened."
            }
        ],

        "Printer / Peripheral": [
            {
                key: "affected_users",
                question:
                    "Is the printer or peripheral issue affecting only you or multiple users?"
            },
            {
                key: "impact",
                question:
                    "Is the device completely unavailable or partly working?"
            },
            {
                key: "device",
                question:
                    "What printer or peripheral model is affected?"
            },
            {
                key: "error_message",
                question:
                    "Do you see an error, warning light, paper jam, or connection message?"
            },
            {
                key: "tried_steps",
                question:
                    "Have you checked cables, paper, toner, power, and restarted the device?"
            },
            {
                key: "details",
                question:
                    "Please describe the issue briefly."
            }
        ],

        "Other IT Support": [
            {
                key: "affected_users",
                question:
                    "Who is affected? Only you, multiple users, or the whole team?"
            },
            {
                key: "impact",
                question:
                    "How is this affecting your work?"
            },
            {
                key: "urgency",
                question:
                    "How urgent is the issue?"
            },
            {
                key: "device",
                question:
                    "What device, system, browser, or application is affected?"
            },
            {
                key: "error_message",
                question:
                    "Are you seeing an error message?"
            },
            {
                key: "tried_steps",
                question:
                    "What troubleshooting steps have you tried?"
            },
            {
                key: "details",
                question:
                    "Please describe the issue."
            }
        ]
    };

    function createEmptyTriageData() {
        return {
            issue_type: "",
            affected_users: "",
            impact: "",
            urgency: "",
            device: "",
            error_message: "",
            tried_steps: "",
            details: ""
        };
    }

    function setInputDisabled(disabled) {
        if (supportInput) {
            supportInput.disabled = disabled;
        }

        if (supportSendBtn) {
            supportSendBtn.disabled = disabled;
        }

        if (supportAttachmentBtn) {
            supportAttachmentBtn.disabled = disabled;
        }
    }

    function setTextInputEnabled(enabled) {
        if (supportInput) {
            supportInput.disabled = !enabled;
        }

        if (supportSendBtn) {
            supportSendBtn.disabled = !enabled;
        }

        if (supportAttachmentBtn) {
            supportAttachmentBtn.disabled =
                !enabled || !currentTicketId;
        }
    }

    function clearMessages() {
        supportMessages.innerHTML = "";
        LiveChatCore.clearRenderedEvents();
    }

    function addMessage(
        message,
        side,
        name,
        type = "normal",
        html = false,
        createdAt = null
    ) {
        return LiveChatCore.addChatBubble({
            container: supportMessages,
            message: message,
            side: side,
            name: name,
            type: type,
            html: html,
            created_at: createdAt
        });
    }

    function addSystemMessage(
        message,
        html = true
    ) {
        return addMessage(
            message,
            "left",
            "AI IT Assistant",
            "system",
            html
        );
    }

    async function saveSessionMessage(
        role,
        message,
        options = {}
    ) {
        if (
            !currentSessionId ||
            !message
        ) {
            return null;
        }

        return LiveChatCore.saveChatSessionMessage(
            currentSessionId,
            {
                role: role,
                message: message,
                ticket_id: currentTicketId,
                resolution_status:
                    options.resolution_status ||
                    "Active",
                faq_matched:
                    options.faq_matched === true,
                ai_used:
                    options.ai_used === true,
                escalated:
                    options.escalated === true
            }
        );
    }

    async function persistTriageProgress(
        stage = "triage"
    ) {
        if (!currentSessionId) {
            return;
        }

        await LiveChatCore.updateTriageProgress(
            currentSessionId,
            {
                issue_type:
                    triageData.issue_type,
                triage_step:
                    triageStep,
                triage_data:
                    triageData,
                current_stage:
                    stage
            }
        );
    }

    function updateTicketMeta(ticket) {
        if (!ticket) {
            supportTicketMeta.style.display =
                "none";

            return;
        }

        supportTicketMeta.style.display =
            "flex";

        supportStatusBadge.innerText =
            ticket.status || "Open";

        supportPriorityBadge.innerText =
            ticket.priority || "Medium";

        supportCategoryBadge.innerText =
            ticket.category || "General";

        supportStatusBadge.className =
            "support-badge status-" +
            String(
                ticket.status || "open"
            )
                .toLowerCase()
                .replaceAll(" ", "-");

        supportPriorityBadge.className =
            "support-badge priority-" +
            String(
                ticket.priority || "medium"
            ).toLowerCase();

        supportCategoryBadge.className =
            "support-badge";
    }

    function updateUrlSession(sessionId) {
        const url = new URL(
            window.location.href
        );

        if (sessionId) {
            url.searchParams.set(
                "session_id",
                sessionId
            );
        } else {
            url.searchParams.delete(
                "session_id"
            );
        }

        window.history.replaceState(
            {},
            "",
            url
        );
    }

    function getRequestedSessionId() {
        const params = new URLSearchParams(
            window.location.search
        );

        const value = params.get(
            "session_id"
        );

        if (!value) {
            return null;
        }

        const number = Number(value);

        return Number.isInteger(number)
            && number > 0
            ? number
            : null;
    }

    function calculateCategory(issueType) {
        const map = {
            "Login / Account Access":
                "Account Access",
            "Password Reset":
                "Password Reset",
            "Email Issue":
                "Email",
            "Network Issue":
                "Network",
            "Software Issue":
                "Software",
            "Hardware Issue":
                "Hardware",
            "Security Issue":
                "Security",
            "Printer / Peripheral":
                "Hardware",
            "Other IT Support":
                "Help and support"
        };

        return (
            map[issueType] ||
            "Help and support"
        );
    }

    function calculatePriority() {
        const issue = String(
            triageData.issue_type || ""
        ).toLowerCase();

        const affectedUsers = String(
            triageData.affected_users || ""
        ).toLowerCase();

        const impact = String(
            triageData.impact || ""
        ).toLowerCase();

        const urgency = String(
            triageData.urgency || ""
        ).toLowerCase();

        const errorMessage = String(
            triageData.error_message || ""
        ).toLowerCase();

        const details = String(
            triageData.details || ""
        ).toLowerCase();

        if (
            issue.includes("security") ||
            details.includes("hacked") ||
            details.includes("phishing") ||
            details.includes("breach") ||
            details.includes("unauthorized") ||
            errorMessage.includes("malware")
        ) {
            return "Urgent";
        }

        if (
            affectedUsers.includes("everyone") ||
            affectedUsers.includes("whole team") ||
            affectedUsers.includes("multiple") ||
            impact.includes("completely") ||
            impact.includes("cannot work") ||
            impact.includes("unable") ||
            urgency.includes("urgent") ||
            urgency.includes("today")
        ) {
            return "High";
        }

        if (
            impact.includes("partial") ||
            impact.includes("sometimes") ||
            impact.includes("intermittent") ||
            urgency.includes("week")
        ) {
            return "Medium";
        }

        return "Low";
    }

    function buildTriageSummary() {
        const escape =
            LiveChatCore.escapeHtml;

        return `
<strong>IT Triage Summary</strong><br><br>
<strong>Issue Type:</strong> ${escape(triageData.issue_type)}<br>
<strong>Category:</strong> ${escape(calculateCategory(triageData.issue_type))}<br>
<strong>Suggested Priority:</strong> ${escape(calculatePriority())}<br>
<strong>Affected Users:</strong> ${escape(triageData.affected_users)}<br>
<strong>Impact:</strong> ${escape(triageData.impact)}<br>
<strong>Urgency:</strong> ${escape(triageData.urgency)}<br>
<strong>Device/Application/System:</strong> ${escape(triageData.device)}<br>
<strong>Error Message:</strong> ${escape(triageData.error_message)}<br>
<strong>Steps Already Tried:</strong> ${escape(triageData.tried_steps)}<br>
<strong>Details:</strong> ${escape(triageData.details)}
        `.trim();
    }

    async function createNewSession(issueType) {
        const response =
            await LiveChatCore.createChatSession({
                title:
                    issueType ||
                    "New IT Support Chat",
                issue_type:
                    issueType || ""
            });

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            return null;
        }

        currentSessionId =
            response.data.session.id;

        updateUrlSession(
            currentSessionId
        );

        return currentSessionId;
    }

    function renderStartCard() {
        clearMessages();

        currentSessionId = null;
        currentTicketId = null;
        currentTicketNumber = null;
        currentTicketClosed = false;

        triageMode = false;
        triageStep = 0;
        triageQuestions = [];
        triageData =
            createEmptyTriageData();

        updateUrlSession(null);

        supportChatTitle.innerText =
            "AI IT Triage Assistant";

        supportChatSubtitle.innerText =
            "Start a new IT support chat.";

        updateTicketMeta(null);
        setInputDisabled(true);

        supportMessages.innerHTML = `
            <div class="support-system-card">
                <h5>
                    What type of IT issue are you having?
                </h5>

                <p>
                    Select the closest option.
                    Your triage progress will be saved automatically.
                </p>

                <div class="triage-grid">
                    <button class="triage-option" data-issue="Login / Account Access">
                        <i class="fa fa-user"></i>
                        Login / Account Access
                    </button>

                    <button class="triage-option" data-issue="Password Reset">
                        <i class="fa fa-key"></i>
                        Password Reset
                    </button>

                    <button class="triage-option" data-issue="Email Issue">
                        <i class="fa fa-envelope"></i>
                        Email Issue
                    </button>

                    <button class="triage-option" data-issue="Network Issue">
                        <i class="fa fa-wifi"></i>
                        Network Issue
                    </button>

                    <button class="triage-option" data-issue="Software Issue">
                        <i class="fa fa-desktop"></i>
                        Software Issue
                    </button>

                    <button class="triage-option" data-issue="Hardware Issue">
                        <i class="fa fa-laptop"></i>
                        Hardware Issue
                    </button>

                    <button class="triage-option" data-issue="Security Issue">
                        <i class="fa fa-shield"></i>
                        Security Issue
                    </button>

                    <button class="triage-option" data-issue="Printer / Peripheral">
                        <i class="fa fa-print"></i>
                        Printer / Peripheral
                    </button>

                    <button class="triage-option" data-issue="Other IT Support">
                        <i class="fa fa-question-circle"></i>
                        Other IT Support
                    </button>
                </div>
            </div>
        `;
    }

    async function startTriage(issueType) {
        clearMessages();

        currentTicketId = null;
        currentTicketNumber = null;
        currentTicketClosed = false;

        triageMode = true;
        aiConversationMode = false;
        triageStep = 0;
        triageData =
            createEmptyTriageData();

        triageData.issue_type =
            issueType;

        triageQuestions =
            triageQuestionBank[issueType] ||
            triageQuestionBank[
            "Other IT Support"
            ];

        const sessionId =
            await createNewSession(
                issueType
            );

        if (!sessionId) {
            addSystemMessage(
                "The chat session could not be created.",
                false
            );

            return;
        }

        supportChatTitle.innerText =
            issueType;

        supportChatSubtitle.innerText =
            "IT triage in progress";

        updateTicketMeta(null);
        setTextInputEnabled(true);

        addMessage(
            issueType,
            "right",
            "You",
            "normal",
            false
        );

        await saveSessionMessage(
            "user",
            `Issue selected: ${issueType}`
        );

        const firstQuestion =
            triageQuestions[0].question;

        addSystemMessage(
            firstQuestion,
            false
        );

        await saveSessionMessage(
            "assistant",
            firstQuestion
        );

        await persistTriageProgress(
            "triage"
        );

        await loadHistory();

        supportInput.focus();
    }

    function removeAiChatActions() {
        const existing = document.getElementById(
            "persistentAiChatActions"
        );

        if (existing) {
            existing.remove();
        }
    }

    function renderAiChatActions() {
        removeAiChatActions();

        if (!currentSessionId || currentTicketId) {
            return;
        }

        const wrap = document.createElement("div");
        wrap.id = "persistentAiChatActions";
        wrap.className = "chat-row chat-left";

        wrap.innerHTML = `
            <div class="chat-bubble system-bubble">
                <div class="support-mini-actions">
                    <button
                        type="button"
                        class="support-mini-btn success"
                        id="aiChatSolvedBtn">
                        Issue solved
                    </button>

                    <button
                        type="button"
                        class="support-mini-btn danger"
                        id="aiChatCreateTicketBtn">
                        Create support ticket
                    </button>
                </div>
            </div>
        `;

        supportMessages.appendChild(wrap);

        wrap.querySelector(
            "#aiChatSolvedBtn"
        ).addEventListener(
            "click",
            async function () {
                const response = await LiveChatCore
                    .updateChatSessionState(
                        currentSessionId,
                        "awaiting_rating"
                    );

                if (
                    !response.ok ||
                    !response.data ||
                    response.data.ok !== true
                ) {
                    addSystemMessage(
                        "The chat could not be completed. Please try again.",
                        false
                    );
                    return;
                }

                aiConversationMode = false;
                removeAiChatActions();
                showRatingBox();
            }
        );

        wrap.querySelector(
            "#aiChatCreateTicketBtn"
        ).addEventListener(
            "click",
            createTriageTicket
        );

        LiveChatCore.scrollBottom(
            supportMessages
        );
    }

    function renderResolutionPrompt() {
        if (
            document.getElementById(
                "triageResolutionPrompt"
            )
        ) {
            return;
        }

        const wrap =
            document.createElement("div");

        wrap.id =
            "triageResolutionPrompt";

        wrap.className =
            "chat-row chat-left";

        wrap.innerHTML = `
            <div class="chat-bubble system-bubble">
                <strong>
                    Did this solve your issue?
                </strong>

                <div style="margin-top:8px;">
                    Choose Yes to rate and complete the chat.
                    Choose No to continue chatting with the AI, or create a support ticket.
                </div>

                <div class="support-mini-actions">
                    <button
                        type="button"
                        class="support-mini-btn success"
                        id="triageSolvedYesBtn">
                        Yes, issue solved
                    </button>

                    <button
                        type="button"
                        class="support-mini-btn secondary"
                        id="continueAiChatBtn">
                        No, continue chatting
                    </button>

                    <button
                        type="button"
                        class="support-mini-btn danger"
                        id="triageSolvedNoBtn">
                        Create support ticket
                    </button>

                    <button
                        type="button"
                        class="support-mini-btn secondary"
                        id="redoTriageBtn">
                        Redo triage
                    </button>
                </div>
            </div>
        `;

        supportMessages.appendChild(
            wrap
        );

        LiveChatCore.scrollBottom(
            supportMessages
        );

        wrap.querySelector(
            "#triageSolvedYesBtn"
        ).addEventListener(
            "click",
            async function () {
                await LiveChatCore
                    .updateChatSessionState(
                        currentSessionId,
                        "awaiting_rating"
                    );

                wrap.remove();
                showRatingBox();
            }
        );

        wrap.querySelector(
            "#continueAiChatBtn"
        ).addEventListener(
            "click",
            async function () {
                const response =
                    await LiveChatCore
                        .updateChatSessionState(
                            currentSessionId,
                            "ai_chat"
                        );

                if (
                    !response.ok ||
                    !response.data ||
                    response.data.ok !== true
                ) {
                    addSystemMessage(
                        "The AI conversation could not be continued. Please try again.",
                        false
                    );
                    return;
                }

                aiConversationMode = true;
                triageMode = false;
                wrap.remove();
                setTextInputEnabled(true);
                supportInput.placeholder =
                    "Ask another question about this issue...";
                renderAiChatActions();
                supportInput.focus();
                await loadHistory();
            }
        );

        wrap.querySelector(
            "#triageSolvedNoBtn"
        ).addEventListener(
            "click",
            createTriageTicket
        );

        wrap.querySelector(
            "#redoTriageBtn"
        ).addEventListener(
            "click",
            async function () {
                renderStartCard();
            }
        );

        setInputDisabled(true);
    }

    async function requestTriageAnswer() {
        const summary =
            buildTriageSummary();

        await persistTriageProgress(
            "processing_answer"
        );

        addSystemMessage(
            summary,
            true
        );

        await saveSessionMessage(
            "system",
            summary
        );

        addSystemMessage(
            "Checking FAQ, Knowledge Base, and AI...",
            false
        );

        const response =
            await LiveChatCore.getTriageAnswer(
                currentSessionId,
                {
                    triage_summary:
                        summary,
                    issue_type:
                        triageData.issue_type
                }
            );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            addSystemMessage(
                "A solution could not be generated. You can create a support ticket.",
                false
            );

            renderResolutionPrompt();
            return;
        }

        addSystemMessage(
            response.data.reply ||
            "No answer was generated.",
            true
        );

        triageMode = false;

        renderResolutionPrompt();
        await loadHistory();
    }

    function showRatingBox() {
        if (
            document.getElementById(
                "chatRatingBox"
            )
        ) {
            return;
        }

        setInputDisabled(true);

        const wrap =
            document.createElement("div");

        wrap.id =
            "chatRatingBox";

        wrap.className =
            "chat-row chat-left";

        wrap.innerHTML = `
            <div class="chat-bubble system-bubble">
                <strong>
                    Please rate this IT support chat.
                </strong>

                <textarea
                    id="aiFeedbackText"
                    rows="3"
                    style="width:100%; margin-top:10px;"
                    placeholder="Optional feedback..."></textarea>

                <div class="support-mini-actions rating-actions">
                    <button type="button" class="support-mini-btn rating-btn" data-rating="1">1</button>
                    <button type="button" class="support-mini-btn rating-btn" data-rating="2">2</button>
                    <button type="button" class="support-mini-btn rating-btn" data-rating="3">3</button>
                    <button type="button" class="support-mini-btn rating-btn" data-rating="4">4</button>
                    <button type="button" class="support-mini-btn rating-btn success" data-rating="5">5</button>
                </div>

                <div
                    id="ratingResultText"
                    style="margin-top:8px;">
                </div>
            </div>
        `;

        supportMessages.appendChild(
            wrap
        );

        wrap.querySelectorAll(
            ".rating-btn"
        ).forEach(function (button) {
            button.addEventListener(
                "click",
                async function () {
                    const rating = Number(
                        button.dataset.rating
                    );

                    const feedback =
                        (
                            wrap.querySelector(
                                "#aiFeedbackText"
                            ).value ||
                            ""
                        ).trim();

                    const result =
                        wrap.querySelector(
                            "#ratingResultText"
                        );

                    const response =
                        await LiveChatCore
                            .rateChatSession(
                                currentSessionId,
                                rating,
                                feedback
                            );

                    if (
                        !response.ok ||
                        !response.data ||
                        response.data.ok !== true
                    ) {
                        result.innerHTML = `
                            <span style="color:#dc3545;">
                                Rating could not be saved.
                            </span>
                        `;

                        return;
                    }

                    result.innerHTML = `
                        <span style="color:#198754;">
                            Thank you. Rating saved: ${rating}/5.
                        </span>
                    `;

                    addSystemMessage(
                        "This chat has been completed and is now read-only.",
                        false
                    );

                    setInputDisabled(true);
                    await loadHistory();
                }
            );
        });

        LiveChatCore.scrollBottom(
            supportMessages
        );
    }

    async function createTriageTicket() {
        const summary =
            buildTriageSummary();

        setInputDisabled(true);

        addSystemMessage(
            "Creating your support ticket...",
            false
        );

        const response =
            await LiveChatCore.escalateSupport(
                summary,
                {
                    subject:
                        triageData.issue_type ||
                        "IT Support Request",
                    category:
                        calculateCategory(
                            triageData.issue_type
                        ),
                    priority:
                        calculatePriority(),
                    session_id:
                        currentSessionId
                }
            );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            addSystemMessage(
                response.data &&
                    response.data.reply
                    ? response.data.reply
                    : "Could not create the support ticket.",
                false
            );

            setInputDisabled(false);
            return;
        }

        currentTicketId =
            response.data.ticket_id;

        currentTicketNumber =
            response.data.ticket_number;

        currentTicketClosed = false;
        triageMode = false;
        aiConversationMode = false;

        LiveChatCore.joinTicketRoom(
            currentTicketId
        );

        supportChatTitle.innerText =
            `Ticket #${currentTicketNumber}`;

        supportChatSubtitle.innerText =
            "A support agent can continue this conversation.";

        updateTicketMeta({
            status:
                response.data.status ||
                "Open",
            priority:
                response.data.priority ||
                calculatePriority(),
            category:
                response.data.category ||
                calculateCategory(
                    triageData.issue_type
                )
        });

        setTextInputEnabled(true);

        await loadChatSession(
            currentSessionId
        );

        await loadHistory();
    }

    async function handleSend() {
        if (messageSendInProgress) {
            return;
        }

        const message = (
            supportInput.value || ""
        ).trim();

        if (!message) {
            return;
        }

        messageSendInProgress = true;

        const previousPlaceholder =
            supportInput.placeholder;

        supportInput.value = "";
        supportSendBtn.disabled = true;

        try {
            if (triageMode) {
                addMessage(
                    message,
                    "right",
                    "You",
                    "normal",
                    false
                );

                const savedMessage =
                    await saveSessionMessage(
                        "user",
                        message
                    );

                if (
                    savedMessage &&
                    savedMessage.ok === false
                ) {
                    addSystemMessage(
                        "Your answer could not be saved. Please try again.",
                        false
                    );

                    return;
                }

                const currentQuestion =
                    triageQuestions[
                    triageStep
                    ];

                if (currentQuestion) {
                    triageData[
                        currentQuestion.key
                    ] = message;
                }

                triageStep += 1;

                await persistTriageProgress(
                    "triage"
                );

                if (
                    triageStep <
                    triageQuestions.length
                ) {
                    const nextQuestion =
                        triageQuestions[
                            triageStep
                        ].question;

                    addSystemMessage(
                        nextQuestion,
                        false
                    );

                    await saveSessionMessage(
                        "assistant",
                        nextQuestion
                    );

                    await persistTriageProgress(
                        "triage"
                    );

                    supportInput.placeholder =
                        "Answer the current triage question...";

                    supportInput.focus();

                } else {
                    triageMode = false;
                    setInputDisabled(true);

                    await requestTriageAnswer();
                }

                return;
            }

            if (aiConversationMode && !currentTicketId) {
                addMessage(
                    message,
                    "right",
                    "You",
                    "normal",
                    false
                );

                setInputDisabled(true);
                addSystemMessage(
                    "AI is preparing a response...",
                    false
                );

                const response =
                    await LiveChatCore.sendAiFollowUp(
                        currentSessionId,
                        message
                    );

                const waitingMessage =
                    supportMessages.lastElementChild;

                if (
                    waitingMessage &&
                    waitingMessage.textContent.includes(
                        "AI is preparing a response..."
                    )
                ) {
                    waitingMessage.remove();
                }

                if (
                    !response.ok ||
                    !response.data ||
                    response.data.ok !== true
                ) {
                    addSystemMessage(
                        response.data && response.data.message
                            ? response.data.message
                            : "AI could not answer. Please try again or create a support ticket.",
                        false
                    );
                    setTextInputEnabled(true);
                    supportInput.placeholder =
                        "Ask another question about this issue...";
                    return;
                }

                addSystemMessage(
                    response.data.reply ||
                    "No answer was generated.",
                    true
                );

                aiConversationMode = true;
                setTextInputEnabled(true);
                supportInput.placeholder =
                    "Ask another question about this issue...";
                renderAiChatActions();
                supportInput.focus();
                await loadHistory();
                return;
            }

            if (!currentTicketId) {
                addSystemMessage(
                    "This chat is not currently connected to a support ticket.",
                    false
                );

                return;
            }

            /*
             * Your final master rule says the chat must not be restricted
             * merely because the ticket was closed. This restriction will
             * be addressed fully in the persistence/chat-ending correction.
             */
            if (currentTicketClosed) {
                addSystemMessage(
                    "Please confirm whether the proposed solution resolved your issue.",
                    false
                );

                showClosedTicketReviewBox();
                return;
            }

            const response =
                await LiveChatCore.sendTicketComment(
                    currentTicketId,
                    message
                );

            if (
                !response.ok ||
                !response.data ||
                response.data.ok !== true
            ) {
                addSystemMessage(
                    "Message failed to send. Please try again.",
                    false
                );
            }

            /*
             * Do not call loadChatSession() here.
             * The new_comment Socket.IO event appends the saved message.
             */

        } catch (error) {
            console.error(
                "Chat message send error:",
                error
            );

            addSystemMessage(
                "Something went wrong while sending your message. Please try again.",
                false
            );

        } finally {
            messageSendInProgress = false;

            if (
                supportSendBtn &&
                !supportInput.disabled
            ) {
                supportSendBtn.disabled = false;
            }

            supportInput.placeholder =
                previousPlaceholder;

            if (!supportInput.disabled) {
                supportInput.focus();
            }
        }
    }

    function renderSavedMessages(messages) {
        messages.forEach(function (message) {
            LiveChatCore.renderChatMessage(
                supportMessages,
                message,
                currentUserId
            );
        });
    }

    function renderSavedComments(comments) {
        comments.forEach(function (comment) {
            LiveChatCore.renderCommentEvent(
                supportMessages,
                {
                    ticket_id:
                        currentTicketId,
                    comment_id:
                        comment.id,
                    message:
                        comment.message,
                    sender_name:
                        comment.author,
                    sender_role:
                        comment.role,
                    author_id:
                        comment.author_id,
                    created_at:
                        comment.created_at,
                    is_attachment:
                        String(
                            comment.message || ""
                        ).includes("<a ")
                },
                currentUserId
            );
        });
    }

    async function loadChatSession(sessionId) {
        if (!sessionId) {
            renderStartCard();
            return;
        }

        const response =
            await LiveChatCore.fetchChatSession(
                sessionId
            );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            renderStartCard();

            addSystemMessage(
                "Could not load this chat.",
                false
            );

            return;
        }

        const session =
            response.data.session;

        const messages =
            response.data.messages || [];

        const comments =
            response.data.comments || [];

        currentSessionId =
            session.id;

        currentTicketId =
            session.ticket_id || null;

        currentTicketNumber =
            session.ticket_number || null;

        currentTicketClosed =
            String(
                session.ticket_status || ""
            ).toLowerCase() === "closed";

        updateUrlSession(
            currentSessionId
        );

        triageData = {
            ...createEmptyTriageData(),
            ...(session.triage_data || {})
        };

        triageData.issue_type =
            session.issue_type ||
            triageData.issue_type;

        triageQuestions =
            triageQuestionBank[
            triageData.issue_type
            ] ||
            triageQuestionBank[
            "Other IT Support"
            ];

        triageStep =
            Number(
                session.triage_step || 0
            );

        clearMessages();

        supportChatTitle.innerText =
            session.ticket_number
                ? `Ticket #${session.ticket_number}`
                : (
                    session.title ||
                    "IT Support Chat"
                );

        supportChatSubtitle.innerText =
            session.status ||
            "Chat History";

        if (currentTicketId) {
            LiveChatCore.joinTicketRoom(
                currentTicketId
            );

            updateTicketMeta({
                status:
                    session.ticket_status ||
                    session.status,
                priority:
                    session.ticket_priority ||
                    "",
                category:
                    session.ticket_category ||
                    session.issue_type ||
                    ""
            });

        } else {
            updateTicketMeta(null);
        }

        renderSavedMessages(
            messages
        );

        renderSavedComments(
            comments
        );

        const stage =
            session.current_stage ||
            "triage";

        triageMode = false;
        aiConversationMode = false;

        if (stage === "triage") {
            triageMode = true;
            setTextInputEnabled(true);

            supportInput.placeholder =
                "Answer the current triage question...";

            supportInput.focus();
        }

        else if (
            stage === "processing_answer"
        ) {
            setInputDisabled(true);

            addSystemMessage(
                "Your answer is being processed. Please wait.",
                false
            );
        }

        else if (
            stage === "ai_chat"
        ) {
            aiConversationMode = true;
            setTextInputEnabled(true);
            supportInput.placeholder =
                "Ask another question about this issue...";
            renderAiChatActions();
            supportInput.focus();
        }

        else if (
            stage === "awaiting_resolution"
        ) {
            setInputDisabled(true);
            renderResolutionPrompt();
        }

        else if (
            stage === "awaiting_rating"
        ) {
            setInputDisabled(true);
            showRatingBox();
        }

        else if (
            stage === "ticket_created"
        ) {
            setTextInputEnabled(
                !currentTicketClosed
            );

            if (currentTicketClosed) {

                if (
                    response.data.already_rated &&
                    response.data.ticket_rating
                ) {
                    showSavedTicketRating(
                        response.data.ticket_rating
                    );
                }
                else {
                    showClosedTicketReviewBox();
                }
            }
        }

        else if (
            stage === "closed"
        ) {
            currentTicketClosed = true;
            setInputDisabled(true);

            if (
                response.data.already_rated &&
                response.data.ticket_rating
            ) {
                showSavedTicketRating(
                    response.data.ticket_rating
                );
            }
            else {
                showClosedTicketReviewBox();
            }
        }

        else if (
            stage === "solved"
        ) {
            setInputDisabled(true);

            addSystemMessage(
                "This chat has been completed and is read-only.",
                false
            );
        }

        document
            .querySelectorAll(
                ".support-history-item"
            )
            .forEach(function (item) {
                item.classList.remove(
                    "active"
                );

                if (
                    String(
                        item.dataset.sessionId
                    ) ===
                    String(session.id)
                ) {
                    item.classList.add(
                        "active"
                    );
                }
            });
    }

    async function loadHistory(
        searchValue = "",
        preserveChatScroll = true
    ) {
        const previousChatScroll =
            supportMessages
                ? supportMessages.scrollTop
                : 0;
        if (!supportRequestHistory) {
            return;
        }

        const response =
            await LiveChatCore.fetchChatSessions(
                searchValue
            );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            supportRequestHistory.innerHTML = `
                <div class="support-history-empty">
                    Could not load chat history.
                </div>
            `;

            return;
        }

        const sessions =
            response.data.sessions || [];

        if (sessions.length === 0) {
            supportRequestHistory.innerHTML = `
                <div class="support-history-empty">
                    No chat history yet.
                </div>
            `;

            return;
        }

        supportRequestHistory.innerHTML =
            sessions.map(function (session) {
                const label =
                    session.ticket_number
                        ? `#${LiveChatCore.escapeHtml(session.ticket_number)}`
                        : `Chat ${session.id}`;

                const status =
                    session.ticket_status ||
                    session.status ||
                    "Active";

                return `
                    <div
                        class="support-history-item"
                        data-session-id="${session.id}"
                        style="
                            display:block;
                            padding:10px;
                            margin-bottom:8px;
                            border:1px solid #ddd;
                            border-radius:8px;
                            cursor:pointer;
                            background:#fff;
                        "
                    >
                        <div class="support-history-title">
                            ${LiveChatCore.escapeHtml(
                    session.title ||
                    "IT Support Chat"
                )}
                        </div>

                        <div class="support-history-meta">
                            <span>${label}</span>
                            <span>
                                ${LiveChatCore.escapeHtml(status)}
                            </span>
                        </div>
                    </div>
                `;
            }).join("");
        if (
            preserveChatScroll &&
            supportMessages
        ) {
            supportMessages.scrollTop =
                previousChatScroll;
        }
    }

    function showSavedTicketRating(ratingData) {
        const ticketId = Number(currentTicketId || 0);

        if (!ticketId || !ratingData) {
            return;
        }

        const existingReviewBox = document.getElementById(
            `closed-ticket-review-${ticketId}`
        );

        if (existingReviewBox) {
            existingReviewBox.remove();
        }

        const existingSavedBox = document.getElementById(
            `saved-ticket-rating-${ticketId}`
        );

        if (existingSavedBox) {
            return;
        }

        const feedback = String(
            ratingData.feedback || ""
        ).trim();

        const wrap = document.createElement("div");

        wrap.id = `saved-ticket-rating-${ticketId}`;
        wrap.className = "chat-row chat-left";

        wrap.innerHTML = `
        <div class="chat-bubble system-bubble">
            <strong>
                Thank you. Your rating has been saved.
            </strong>

            <div style="margin-top:8px;">
                Rating:
                <strong>
                    ${LiveChatCore.escapeHtml(
            ratingData.rating
        )}/5
                </strong>
            </div>

            ${feedback
                ? `
                        <div style="margin-top:8px;">
                            <strong>Feedback:</strong><br>
                            ${LiveChatCore.escapeHtml(feedback)}
                        </div>
                    `
                : ""
            }

            <div style="margin-top:8px; color:#6b7280;">
                This ticket is complete and cannot be edited.
            </div>
        </div>
    `;

        supportMessages.appendChild(wrap);

        LiveChatCore.scrollBottom(
            supportMessages
        );
    }

    function showClosedTicketRatingBox() {
        const ticketId =
            Number(currentTicketId || 0);

        if (!ticketId) {
            return;
        }

        const ratingBoxId =
            `closed-ticket-rating-${ticketId}`;

        const savedBoxId =
            `saved-ticket-rating-${ticketId}`;

        if (
            document.getElementById(
                savedBoxId
            )
        ) {
            return;
        }

        const existingRatingBox =
            document.getElementById(
                ratingBoxId
            );

        if (existingRatingBox) {
            LiveChatCore.scrollBottom(
                supportMessages
            );

            return;
        }

        const oldReviewBox =
            document.getElementById(
                `closed-ticket-review-${ticketId}`
            );

        if (oldReviewBox) {
            oldReviewBox.remove();
        }

        const wrap =
            document.createElement("div");

        wrap.id = ratingBoxId;
        wrap.className =
            "chat-row chat-left";

        wrap.innerHTML = `
        <div class="chat-bubble system-bubble">

            <strong>
                Thank you. Please rate your support experience.
            </strong>

            <div style="margin-top:6px; color:#6b7280;">
                Select a rating from 1 to 5.
            </div>

            <textarea
                class="closed-ticket-feedback"
                rows="3"
                style="width:100%; margin-top:10px;"
                placeholder="Optional feedback..."></textarea>

            <div class="support-mini-actions rating-actions">

                <button
                    type="button"
                    class="support-mini-btn ticket-rating-btn"
                    data-rating="1">
                    1
                </button>

                <button
                    type="button"
                    class="support-mini-btn ticket-rating-btn"
                    data-rating="2">
                    2
                </button>

                <button
                    type="button"
                    class="support-mini-btn ticket-rating-btn"
                    data-rating="3">
                    3
                </button>

                <button
                    type="button"
                    class="support-mini-btn ticket-rating-btn"
                    data-rating="4">
                    4
                </button>

                <button
                    type="button"
                    class="support-mini-btn ticket-rating-btn success"
                    data-rating="5">
                    5
                </button>

            </div>

            <div
                class="ticket-rating-result"
                style="margin-top:8px;">
            </div>

        </div>
    `;

        supportMessages.appendChild(
            wrap
        );

        const feedbackBox =
            wrap.querySelector(
                ".closed-ticket-feedback"
            );

        const result =
            wrap.querySelector(
                ".ticket-rating-result"
            );

        const ratingButtons =
            wrap.querySelectorAll(
                ".ticket-rating-btn"
            );

        ratingButtons.forEach(
            function (button) {
                button.addEventListener(
                    "click",
                    async function () {
                        const rating =
                            Number(
                                button.dataset.rating
                            );

                        const feedback =
                            String(
                                feedbackBox.value || ""
                            ).trim();

                        ratingButtons.forEach(
                            function (item) {
                                item.disabled = true;
                            }
                        );

                        feedbackBox.disabled = true;

                        result.innerHTML = `
                        <span style="color:#6b7280;">
                            Saving your feedback...
                        </span>
                    `;

                        try {
                            const response =
                                await LiveChatCore.rateTicket(
                                    ticketId,
                                    {
                                        rating: rating,
                                        feedback: feedback
                                    }
                                );

                            if (
                                !response.ok ||
                                !response.data ||
                                response.data.ok !== true
                            ) {
                                throw new Error(
                                    response.data &&
                                        response.data.message
                                        ? response.data.message
                                        : (
                                            "Feedback could not "
                                            + "be saved."
                                        )
                                );
                            }

                            wrap.remove();

                            showSavedTicketRating({
                                rating:
                                    response.data.rating
                                    || rating,

                                feedback:
                                    response.data.feedback
                                        !== undefined
                                        ? response.data.feedback
                                        : feedback
                            });

                            setInputDisabled(true);

                            await loadHistory();

                        } catch (error) {
                            console.error(
                                "Ticket rating error:",
                                error
                            );

                            ratingButtons.forEach(
                                function (item) {
                                    item.disabled = false;
                                }
                            );

                            feedbackBox.disabled = false;

                            result.innerHTML = `
                            <span style="color:#dc3545;">
                                ${LiveChatCore.escapeHtml(
                                error.message ||
                                "Feedback could not be saved."
                            )}
                            </span>
                        `;
                        }
                    }
                );
            }
        );

        LiveChatCore.scrollBottom(
            supportMessages
        );
    }
    function showClosedTicketReviewBox() {
        const ticketId =
            Number(currentTicketId || 0);

        if (!ticketId) {
            return;
        }

        const reviewBoxId =
            `closed-ticket-review-${ticketId}`;

        const existingSavedRating =
            document.getElementById(
                `saved-ticket-rating-${ticketId}`
            );

        if (existingSavedRating) {
            return;
        }

        const existingRatingBox =
            document.getElementById(
                `closed-ticket-rating-${ticketId}`
            );

        if (existingRatingBox) {
            return;
        }

        if (
            document.getElementById(
                reviewBoxId
            )
        ) {
            return;
        }

        const wrap =
            document.createElement("div");

        wrap.id = reviewBoxId;
        wrap.className =
            "chat-row chat-left";

        wrap.innerHTML = `
        <div class="chat-bubble system-bubble">

            <strong>
                Did the support provided solve your issue?
            </strong>

            <div style="margin-top:8px;">
                Select Yes to complete the support process
                and provide feedback. Select No to reopen
                the ticket and continue support.
            </div>

            <div class="support-mini-actions">

                <button
                    type="button"
                    class="support-mini-btn success confirm-ticket-solved-btn">
                    Yes, issue solved
                </button>

                <button
                    type="button"
                    class="support-mini-btn danger reopen-ticket-btn">
                    No, reopen ticket
                </button>

            </div>

            <div
                class="ticket-review-result"
                style="margin-top:8px;">
            </div>

        </div>
    `;

        supportMessages.appendChild(
            wrap
        );

        const yesButton =
            wrap.querySelector(
                ".confirm-ticket-solved-btn"
            );

        const noButton =
            wrap.querySelector(
                ".reopen-ticket-btn"
            );

        const result =
            wrap.querySelector(
                ".ticket-review-result"
            );

        // =====================================================
        // YES — SHOW RATING FORM
        // =====================================================

        yesButton.addEventListener(
            "click",
            async function () {
                yesButton.disabled = true;
                noButton.disabled = true;

                yesButton.innerText =
                    "Please wait...";

                result.innerHTML = `
                <span style="color:#6b7280;">
                    Confirming your response...
                </span>
            `;

                try {
                    const response =
                        await LiveChatCore.confirmSolved(
                            ticketId
                        );

                    if (
                        !response.ok ||
                        !response.data ||
                        response.data.ok !== true
                    ) {
                        throw new Error(
                            response.data &&
                                response.data.message
                                ? response.data.message
                                : (
                                    "The ticket could not be "
                                    + "confirmed as solved."
                                )
                        );
                    }

                    // Remove the Yes/No prompt before
                    // rendering the feedback box.
                    wrap.remove();

                    setInputDisabled(true);

                    showClosedTicketRatingBox();

                } catch (error) {
                    console.error(
                        "Confirm solved error:",
                        error
                    );

                    yesButton.disabled = false;
                    noButton.disabled = false;

                    yesButton.innerText =
                        "Yes, issue solved";

                    result.innerHTML = `
                    <span style="color:#dc3545;">
                        ${LiveChatCore.escapeHtml(
                        error.message ||
                        "The response could not be saved."
                    )}
                    </span>
                `;
                }
            }
        );

        // =====================================================
        // NO — REOPEN TICKET
        // =====================================================

        noButton.addEventListener(
            "click",
            async function () {
                yesButton.disabled = true;
                noButton.disabled = true;

                noButton.innerText =
                    "Reopening...";

                result.innerHTML = `
                <span style="color:#6b7280;">
                    Reopening your ticket...
                </span>
            `;

                try {
                    const response =
                        await LiveChatCore.reopenTicket(
                            ticketId
                        );

                    if (
                        !response.ok ||
                        !response.data ||
                        response.data.ok !== true
                    ) {
                        throw new Error(
                            response.data &&
                                response.data.message
                                ? response.data.message
                                : "Ticket could not be reopened."
                        );
                    }

                    currentTicketClosed = false;

                    wrap.remove();

                    setInputDisabled(false);

                    addSystemMessage(
                        response.data.message ||
                        (
                            "Your ticket has been reopened. "
                            + "You may continue the conversation."
                        ),
                        false
                    );

                    await loadHistory();

                    if (supportInput) {
                        supportInput.focus();
                    }

                } catch (error) {
                    console.error(
                        "Reopen ticket error:",
                        error
                    );

                    yesButton.disabled = false;
                    noButton.disabled = false;

                    noButton.innerText =
                        "No, reopen ticket";

                    result.innerHTML = `
                    <span style="color:#dc3545;">
                        ${LiveChatCore.escapeHtml(
                        error.message ||
                        "Ticket could not be reopened."
                    )}
                    </span>
                `;
                }
            }
        );

        LiveChatCore.scrollBottom(
            supportMessages
        );
    }

    async function uploadAttachment(file) {
        if (
            !file ||
            !currentTicketId
        ) {
            return;
        }

        const response =
            await LiveChatCore.uploadAttachment(
                currentTicketId,
                file
            );

        if (
            !response.ok ||
            !response.data ||
            response.data.ok !== true
        ) {
            addSystemMessage(
                "Upload failed.",
                false
            );
        }
    }

    supportMessages.addEventListener(
        "click",
        async function (event) {
            const option =
                event.target.closest(
                    ".triage-option"
                );

            if (option) {
                await startTriage(
                    option.dataset.issue
                );
            }
        }
    );

    if (supportRequestHistory) {
        supportRequestHistory.addEventListener(
            "click",
            async function (event) {
                const item =
                    event.target.closest(
                        ".support-history-item"
                    );

                if (!item) {
                    return;
                }

                await loadChatSession(
                    Number(
                        item.dataset.sessionId
                    )
                );
            }
        );
    }

    if (newSupportRequestBtn) {
        newSupportRequestBtn.addEventListener(
            "click",
            function (event) {
                if (
                    window.location.pathname
                    === "/customer/chat"
                ) {
                    event.preventDefault();
                    renderStartCard();
                }
            }
        );
    }

    supportSendBtn.addEventListener(
        "click",
        handleSend
    );

    supportInput.addEventListener(
        "keydown",
        function (event) {
            if (
                event.key === "Enter" &&
                !event.shiftKey
            ) {
                event.preventDefault();
                handleSend();
            }
        }
    );

    supportAttachmentBtn.addEventListener(
        "click",
        function () {
            supportAttachmentInput.click();
        }
    );

    supportAttachmentInput.addEventListener(
        "change",
        function () {
            const file =
                supportAttachmentInput.files[0];

            if (file) {
                uploadAttachment(file);
            }

            supportAttachmentInput.value =
                "";
        }
    );

    if (supportHistorySearch) {
        let searchTimer = null;

        supportHistorySearch.addEventListener(
            "input",
            function () {
                clearTimeout(
                    searchTimer
                );

                searchTimer = setTimeout(
                    function () {
                        loadHistory(
                            supportHistorySearch
                                .value
                                .trim()
                        );
                    },
                    250
                );
            }
        );
    }

    socket.on(
        "connect",
        function () {
            if (currentUserId) {
                LiveChatCore
                    .joinNotificationRoom(
                        currentUserId
                    );
            }

            if (currentTicketId) {
                LiveChatCore.joinTicketRoom(
                    currentTicketId
                );
            }
        }
    );

    socket.on(
        "new_comment",
        function (data) {
            if (
                !data ||
                !data.message
            ) {
                return;
            }

            if (
                currentTicketId &&
                data.ticket_id &&
                Number(data.ticket_id) !==
                Number(currentTicketId)
            ) {
                return;
            }

            LiveChatCore.renderCommentEvent(
                supportMessages,
                data,
                currentUserId
            );
        }
    );

    async function handleCustomerTicketClosed(
        data
    ) {
        if (
            !data ||
            !data.ticket_id ||
            Number(data.ticket_id) !==
            Number(currentTicketId)
        ) {
            return;
        }

        currentTicketClosed = true;
        setInputDisabled(true);

        if (currentSessionId) {
            await LiveChatCore
                .updateChatSessionState(
                    currentSessionId,
                    "closed"
                );
        }

        const closureMessage =
            String(
                data.message || ""
            ).trim();

        if (closureMessage) {
            addSystemMessage(
                closureMessage,
                false
            );
        }

        showClosedTicketReviewBox();

        await loadHistory();
    }

    socket.on(
        "ticket_closed",
        handleCustomerTicketClosed
    );

    socket.on(
        "customer_ticket_closed",
        handleCustomerTicketClosed
    );

    socket.on(
        "ticket_reopened",
        async function (data) {
            if (
                !data ||
                Number(data.ticket_id) !==
                Number(currentTicketId)
            ) {
                return;
            }

            currentTicketClosed = false;

            await LiveChatCore
                .updateChatSessionState(
                    currentSessionId,
                    "ticket_created"
                );

            await loadChatSession(
                currentSessionId
            );
        }
    );

    socket.on(
        "customer_live_refresh",
        async function (data) {
            if (
                data &&
                data.user_id &&
                Number(data.user_id) !==
                Number(currentUserId)
            ) {
                return;
            }

            const reason = String(
                data && data.reason
                    ? data.reason
                    : ""
            ).toLowerCase();

            /*
             * These updates were created by this chat page itself.
             *
             * The current page has already updated the messages and
             * interface. Reloading the entire session would clear and
             * rebuild the chat, causing the visible top-to-bottom jump.
             */
            const localUpdateReasons = new Set([
                "triage_progress_updated",
                "chat_session_state_updated",
                "ticket_rated"
            ]);

            if (
                localUpdateReasons.has(reason)
            ) {
                /*
                 * Only refresh the left-side history list.
                 * Do not rebuild the open conversation.
                 */
                await loadHistory();
                return;
            }

            /*
             * These events can genuinely change the active conversation
             * from another page, agent, administrator, or browser tab.
             */
            const conversationReloadReasons =
                new Set([
                    "ticket_created",
                    "ticket_closed",
                    "ticket_reopened",
                    "ticket_confirmed_solved",
                    "ticket_deleted",
                    "ticket_updated",
                    "session_updated"
                ]);

            await loadHistory();

            if (
                currentSessionId &&
                conversationReloadReasons.has(
                    reason
                )
            ) {
                await loadChatSession(
                    currentSessionId
                );
            }
        }
    );

    async function start() {
        const me =
            await LiveChatCore.fetchMe();

        if (
            !me.ok ||
            !me.data ||
            me.data.is_authenticated !== true
        ) {
            window.location.href =
                "/login";

            return;
        }

        currentUserId =
            me.data.user_id;

        LiveChatCore.joinNotificationRoom(
            currentUserId
        );

        await loadHistory();

        const requestedSessionId =
            getRequestedSessionId();

        if (requestedSessionId) {
            await loadChatSession(
                requestedSessionId
            );

        } else {
            renderStartCard();
        }
    }

    start();
})();