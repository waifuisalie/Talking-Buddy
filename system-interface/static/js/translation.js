// ========== TRANSLATION MODE (Phase 9) ==========
// Two-panel, two-speaker, real-time translator. Always anonymous; never
// touches user history. State lives entirely in memory and is wiped when
// the user toggles the mode off.

(function () {
    'use strict';

    // ----- Static config -----
    const PAIR_MAP = {
        'pt-en': { left: 'pt', right: 'en', leftFlag: '🇧🇷', rightFlag: '🇺🇸' },
        'pt-es': { left: 'pt', right: 'es', leftFlag: '🇧🇷', rightFlag: '🇪🇸' },
        'en-es': { left: 'en', right: 'es', leftFlag: '🇺🇸', rightFlag: '🇪🇸' }
    };

    const LANG_LABEL = { pt: 'PT', en: 'EN', es: 'ES' };

    const LANG_TO_USER_LANG = {
        pt: 'pt-BR',
        en: 'en-US',
        es: 'es-ES'
    };

    // ----- State -----
    const state = {
        active: false,         // is translation mode currently on?
        pair: null,            // 'pt-en' | 'pt-es' | 'en-es' | null
        pairCfg: null,         // resolved PAIR_MAP[pair]
        activeSide: null,      // 'left' | 'right' | null — side currently engaging input
        inputMode: 'idle',     // 'idle' | 'mic' | 'keyboard'
        turns: [],             // [{ side, original, translation, sessionId, originalEl, translationEl }]
        inFlight: false,       // a turn is mid-stream
        inFlightSessionId: null,
        chatWasVisible: false  // restore chat-interface on deactivate if it was up before
    };

    // ----- DOM (filled on init) -----
    let els = null;

    function $(sel, root) { return (root || document).querySelector(sel); }
    function $all(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

    function otherSide(side) { return side === 'left' ? 'right' : 'left'; }

    function langOfSide(side) {
        if (!state.pairCfg) return null;
        return state.pairCfg[side];
    }

    function flagOfSide(side) {
        if (!state.pairCfg) return '?';
        return side === 'left' ? state.pairCfg.leftFlag : state.pairCfg.rightFlag;
    }

    // ============================================================
    //  Init / wire DOM
    // ============================================================

    function init() {
        els = {
            toggle: $('#translation-toggle'),
            iface: $('#translation-interface'),
            closeBtn: $('#translation-close-btn'),
            chip: $('#translation-pair-chip'),
            chipLabel: $('.pair-chip-label'),
            modal: $('#translation-pair-modal'),
            chatIface: $('#chat-interface'),
            robotDisplay: $('.robot-display'),
            panels: {
                left: $('.translation-panel[data-side="left"]'),
                right: $('.translation-panel[data-side="right"]')
            },
            flags: {
                left: $('[data-side-flag="left"]'),
                right: $('[data-side-flag="right"]')
            },
            langLabels: {
                left: $('[data-side-lang="left"]'),
                right: $('[data-side-lang="right"]')
            },
            bubbles: {
                left: $('[data-side-bubbles="left"]'),
                right: $('[data-side-bubbles="right"]')
            },
            micBtns: {
                left: $('[data-side-mic="left"]'),
                right: $('[data-side-mic="right"]')
            },
            inputs: {
                left: $('[data-side-input="left"]'),
                right: $('[data-side-input="right"]')
            },
            sendBtns: {
                left: $('[data-side-send="left"]'),
                right: $('[data-side-send="right"]')
            }
        };

        if (!els.toggle || !els.iface) {
            console.warn('[Translation] DOM not present, skipping init');
            return;
        }

        els.toggle.addEventListener('click', onToggleClick);
        els.closeBtn.addEventListener('click', deactivate);
        els.chip.addEventListener('click', openPairModal);

        // Pair option buttons
        $all('.translation-pair-option', els.modal).forEach(btn => {
            btn.addEventListener('click', () => {
                const pair = btn.getAttribute('data-pair');
                pickPair(pair);
            });
        });

        // Click outside modal content closes if a pair is already set
        els.modal.addEventListener('click', (e) => {
            if (e.target === els.modal && state.pair) {
                els.modal.classList.add('hidden');
            }
        });

        ['left', 'right'].forEach(side => {
            els.micBtns[side].addEventListener('click', () => onMicTap(side));
            els.sendBtns[side].addEventListener('click', () => onSendTap(side));
            // The keyboard fires a 'change' event on the input after confirm.
            els.inputs[side].addEventListener('change', () => onKeyboardConfirm(side));
            // Tapping the input itself implies keyboard intent → switch modes
            els.inputs[side].addEventListener('click', () => onKeyboardEngaged(side));
        });

        // i18n: refresh static texts on language change
        window.addEventListener('languageChanged', updateI18nTexts);

        window.translationMode = {
            isActive: () => state.active
        };
    }

    function updateI18nTexts() {
        if (!window.i18n) return;
        // The mic button tooltips & input placeholders depend on the active
        // panel languages, not the UI language, so we refresh them when a
        // pair is set rather than on UI language changes.
        if (state.pair) refreshPanelLabels();
    }

    // ============================================================
    //  Activation / deactivation
    // ============================================================

    function onToggleClick() {
        if (state.active) {
            deactivate();
        } else {
            activate();
        }
    }

    function activate() {
        state.active = true;
        state.chatWasVisible = !!(els.chatIface && !els.chatIface.classList.contains('hidden'));
        els.toggle.classList.add('active');

        // Hide chat + robot, show translation interface
        if (els.chatIface) els.chatIface.classList.add('hidden');
        if (els.robotDisplay) els.robotDisplay.style.visibility = 'hidden';
        els.iface.classList.remove('hidden');

        if (!state.pair) {
            openPairModal();
        } else {
            refreshPanelLabels();
        }
    }

    function deactivate() {
        // Cancel any in-flight session
        if (state.inFlightSessionId) {
            cancelSession(state.inFlightSessionId);
        }
        state.active = false;
        state.activeSide = null;
        state.inputMode = 'idle';
        state.turns = [];
        state.inFlight = false;
        state.inFlightSessionId = null;

        els.toggle.classList.remove('active');
        els.iface.classList.add('hidden');
        els.modal.classList.add('hidden');

        if (els.robotDisplay) els.robotDisplay.style.visibility = '';
        // Restore chat-interface if it had been visible before activation
        if (state.chatWasVisible && els.chatIface) {
            els.chatIface.classList.remove('hidden');
        }
        state.chatWasVisible = false;

        clearBubbleLists();
    }

    // ============================================================
    //  Pair picker
    // ============================================================

    function openPairModal() {
        els.modal.classList.remove('hidden');
    }

    function pickPair(pairKey) {
        if (!PAIR_MAP[pairKey]) return;
        state.pair = pairKey;
        state.pairCfg = PAIR_MAP[pairKey];
        els.modal.classList.add('hidden');
        // New pair → wipe history (mixing pairs makes no sense)
        state.turns = [];
        clearBubbleLists();
        refreshPanelLabels();
        // No active speaker until someone taps
        setActiveSide(null);
    }

    // Look up an i18n string in a SPECIFIC panel's language (not the UI
    // language). Used for per-panel hints so the EN panel shows English
    // text even when the user's UI is in Portuguese.
    function tInLang(key, lang) {
        const userLang = LANG_TO_USER_LANG[lang] || 'pt-BR';
        if (!window.i18n) return null;
        const val = window.i18n.t(key, {}, userLang);
        return (typeof val === 'string' && !val.startsWith('[')) ? val : null;
    }

    function panelIdleText(side) {
        const lang = langOfSide(side);
        return tInLang('translation.panel_idle', lang) || 'Tap mic to speak';
    }

    function refreshPanelLabels() {
        if (!state.pairCfg) return;
        const lf = state.pairCfg.left;
        const rf = state.pairCfg.right;
        els.flags.left.textContent = state.pairCfg.leftFlag;
        els.flags.right.textContent = state.pairCfg.rightFlag;
        els.langLabels.left.textContent = LANG_LABEL[lf];
        els.langLabels.right.textContent = LANG_LABEL[rf];

        // Mic tooltips — use each panel's own language
        els.micBtns.left.title = tInLang(`translation.speak_${lf}`, lf) || `Speak ${LANG_LABEL[lf]}`;
        els.micBtns.right.title = tInLang(`translation.speak_${rf}`, rf) || `Speak ${LANG_LABEL[rf]}`;

        // Input placeholders — use each panel's own language
        els.inputs.left.placeholder = tInLang(`translation.type_${lf}`, lf) || `Type in ${LANG_LABEL[lf]}...`;
        els.inputs.right.placeholder = tInLang(`translation.type_${rf}`, rf) || `Type in ${LANG_LABEL[rf]}...`;

        // Empty-state hint per panel, in that panel's language
        ['left', 'right'].forEach(side => {
            const empty = els.bubbles[side].querySelector('.translation-empty');
            if (empty) {
                empty.textContent = panelIdleText(side);
                // Stop the global i18n updater from overwriting this on UI
                // language change — the panel language is what governs the
                // hint, not the UI language.
                empty.removeAttribute('data-i18n-text');
            }
        });

        // Update the pair chip label
        const pretty = `${state.pairCfg.leftFlag} ${LANG_LABEL[lf]} ⇄ ${LANG_LABEL[rf]} ${state.pairCfg.rightFlag}`;
        if (els.chipLabel) els.chipLabel.textContent = pretty;
    }

    function setActiveSide(side) {
        // side === null  → both panels neutral (no .active, no .idle)
        // side === 'left' → left .active, right .idle (dimmed)
        // side === 'right' → right .active, left .idle (dimmed)
        state.activeSide = side;
        ['left', 'right'].forEach(s => {
            if (els.panels[s]) {
                const isActive = (s === side);
                const isIdle = (side !== null && !isActive);
                els.panels[s].classList.toggle('active', isActive);
                els.panels[s].classList.toggle('idle', isIdle);
            }
        });
    }

    function clearBubbleLists() {
        ['left', 'right'].forEach(s => {
            els.bubbles[s].innerHTML = '';
            const empty = document.createElement('div');
            empty.className = 'translation-empty';
            empty.textContent = state.pairCfg ? panelIdleText(s) : 'Tap mic to speak';
            els.bubbles[s].appendChild(empty);
        });
    }

    function removeEmptyHint(side) {
        const empty = els.bubbles[side].querySelector('.translation-empty');
        if (empty) empty.remove();
    }

    // ============================================================
    //  Mic / Keyboard mutual exclusion
    // ============================================================

    async function onMicTap(side) {
        if (!state.pair) { openPairModal(); return; }
        if (state.inFlight) return;  // ignore taps during a live stream

        // Cancel any current keyboard editing in this panel
        if (state.inputMode === 'keyboard') {
            try { window.closeKeyboard && window.closeKeyboard(); } catch (_) {}
        }

        state.inputMode = 'mic';
        setActiveSide(side);

        await recordAndTranscribe(side);
    }

    function onKeyboardEngaged(side) {
        if (!state.pair) { openPairModal(); return; }
        if (state.inFlight) return;

        // Cancel mic if open on the same panel
        if (state.inputMode === 'mic') {
            // The /api/voice/record_and_transcribe call is server-side and
            // not cancellable, but we can at least drop the result by
            // resetting the input mode. The VAD will time out on its own.
            // Visually we toggle the mic out of "recording" state.
            ['left', 'right'].forEach(s => els.micBtns[s].classList.remove('recording'));
        }

        state.inputMode = 'keyboard';
        setActiveSide(side);
    }

    function onSendTap(side) {
        const text = (els.inputs[side].value || '').trim();
        if (!text) return;
        els.inputs[side].value = '';
        submitTurn(side, text);
    }

    function onKeyboardConfirm(side) {
        // The virtual keyboard fires a 'change' event after confirm — but
        // the user may also use the Enviar button. We only auto-submit
        // here if the input has text AND the user hasn't already tapped
        // the send button (no easy distinguisher; we just trust the value).
        const text = (els.inputs[side].value || '').trim();
        if (!text) return;
        els.inputs[side].value = '';
        submitTurn(side, text);
    }

    // ============================================================
    //  Voice recording
    // ============================================================

    async function recordAndTranscribe(side) {
        const lang = langOfSide(side);
        const userLang = LANG_TO_USER_LANG[lang] || 'pt-BR';
        const micBtn = els.micBtns[side];

        micBtn.classList.add('recording');

        try {
            const resp = await fetch('/api/voice/record_and_transcribe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    max_duration: 15,
                    language: userLang
                })
            });
            const data = await resp.json();
            micBtn.classList.remove('recording');

            // If keyboard took over while we were waiting, drop the result
            if (state.inputMode !== 'mic') return;

            if (data.success && data.text) {
                submitTurn(side, data.text.trim());
            } else {
                console.warn('[Translation] STT returned no text:', data.error);
            }
        } catch (e) {
            micBtn.classList.remove('recording');
            console.error('[Translation] STT error:', e);
        }
    }

    // ============================================================
    //  Turn submission + SSE
    // ============================================================

    function lastTurnForOther(side) {
        // The most recent committed turn from the OTHER side, used by the
        // LLM as pronoun-resolution context. We pass the *translation*
        // (what the current speaker heard), not the other speaker's
        // original.
        for (let i = state.turns.length - 1; i >= 0; i--) {
            if (state.turns[i].side === otherSide(side)) {
                return state.turns[i].translation || null;
            }
        }
        return null;
    }

    function submitTurn(side, text) {
        if (!state.pair || !text) return;
        if (state.inFlight) return;

        const listenerSide = otherSide(side);
        const src = langOfSide(side);
        const tgt = langOfSide(listenerSide);
        const lastTurn = lastTurnForOther(side);

        // Seal previous retryable bubble — new submission means the prior
        // one is now committed.
        sealRetryable();

        // Render speaker's original on their panel
        removeEmptyHint(side);
        const originalEl = makeBubble(text, 'original');
        els.bubbles[side].appendChild(originalEl);
        scrollToBottom(side);

        // Render placeholder bubble on the listener's panel
        removeEmptyHint(listenerSide);
        const translationEl = makeBubble('', 'translation thinking');
        translationEl.innerHTML = '<em>…</em>';
        els.bubbles[listenerSide].appendChild(translationEl);
        scrollToBottom(listenerSide);

        // Track the turn (sessionId set once we get it)
        const turn = {
            side,
            original: text,
            translation: '',
            sessionId: null,
            originalEl,
            translationEl
        };
        state.turns.push(turn);

        state.inFlight = true;
        // After submitting, the LISTENER's panel is the active one: their
        // translation arrives there and they are who's expected to reply.
        // The speaker's panel dims to make the turn boundary visible.
        setActiveSide(listenerSide);

        // POST to /api/chat/send
        fetch('/api/chat/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                rfid: 'anonymous',
                mode: 'translation',
                source_lang: src,
                target_lang: tgt,
                last_turn: lastTurn
            })
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success || !data.session_id) {
                throw new Error(data.error || 'No session_id');
            }
            turn.sessionId = data.session_id;
            state.inFlightSessionId = data.session_id;
            openSSE(turn);
        })
        .catch(err => {
            console.error('[Translation] send failed:', err);
            translationEl.textContent = `(error: ${err.message})`;
            state.inFlight = false;
            state.inFlightSessionId = null;
        });
    }

    function openSSE(turn) {
        const es = new EventSource(`/api/chat/stream/${turn.sessionId}`);
        let started = false;
        let acc = '';

        es.addEventListener('sentence_playing', (e) => {
            try {
                const { text } = JSON.parse(e.data);
                if (!started) {
                    turn.translationEl.classList.remove('tr-bubble--thinking');
                    turn.translationEl.innerHTML = '';
                    started = true;
                }
                acc += (acc ? ' ' : '') + text;
                turn.translationEl.textContent = acc;
                scrollToBottom(otherSide(turn.side));
            } catch (err) {
                console.warn('[Translation] sentence_playing parse error', err);
            }
        });

        es.addEventListener('response_done', () => {
            es.close();
            turn.translation = acc;
            state.inFlight = false;
            state.inFlightSessionId = null;
            markRetryable(turn);
        });

        es.addEventListener('error', (e) => {
            console.warn('[Translation] SSE error', e);
            es.close();
            state.inFlight = false;
            state.inFlightSessionId = null;
            // Don't mark retryable if the stream failed — the original
            // bubble stays plain.
        });
    }

    // ============================================================
    //  Retry
    // ============================================================

    function sealRetryable() {
        // Remove retryable affordance from every existing bubble + drop
        // any associated retry button.
        $all('.tr-bubble--retryable').forEach(el => {
            el.classList.remove('tr-bubble--retryable');
            if (el._retryHandler) {
                el.removeEventListener('click', el._retryHandler);
                el._retryHandler = null;
            }
        });
        $all('.tr-retry-btn').forEach(b => b.remove());
    }

    function markRetryable(turn) {
        // Highlight the bubble — visual cue that it's the active turn
        turn.originalEl.classList.add('tr-bubble--retryable');

        // Build a real DOM button (sibling of the bubble), label in the
        // speaker's own language so it reads naturally to them.
        const label = tInLang('translation.retry_hint', langOfSide(turn.side)) || 'Tap to retry';
        const btn = document.createElement('button');
        btn.className = 'tr-retry-btn';
        btn.type = 'button';
        btn.innerHTML =
            '<span class="tr-retry-icon" aria-hidden="true">↻</span>' +
            '<span class="tr-retry-label"></span>';
        btn.querySelector('.tr-retry-label').textContent = label;
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            retryTurn(turn);
        });
        // Insert immediately after the original bubble so it sits below
        // it in the column-flex bubbles list.
        const parent = turn.originalEl.parentNode;
        if (parent) {
            parent.insertBefore(btn, turn.originalEl.nextSibling);
        }
        turn._retryBtn = btn;

        // The bubble itself is also tappable — preserves the
        // "tap-anywhere" UX.
        const handler = () => retryTurn(turn);
        turn.originalEl._retryHandler = handler;
        turn.originalEl.addEventListener('click', handler);
    }

    function retryTurn(turn) {
        if (state.inFlight) return;
        // Only the most-recent turn is retryable; double-check it's still
        // the last one.
        if (state.turns.length === 0 || state.turns[state.turns.length - 1] !== turn) {
            // No longer the latest — should never happen because we seal,
            // but be defensive.
            return;
        }

        // Cancel any in-flight session (in case retry fires before
        // response_done — e.g. while audio is still playing).
        if (turn.sessionId) {
            cancelSession(turn.sessionId);
        }

        // Drop the turn pair from state and DOM
        state.turns.pop();
        turn.originalEl.remove();
        turn.translationEl.remove();

        // If panels are now empty, restore the idle hint in the panel's
        // own language.
        const restoreEmpty = (s) => {
            if (els.bubbles[s].children.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'translation-empty';
                empty.textContent = panelIdleText(s);
                els.bubbles[s].appendChild(empty);
            }
        };
        restoreEmpty(turn.side);
        restoreEmpty(otherSide(turn.side));

        // Re-make the previous turn (if any) retryable again
        if (state.turns.length > 0) {
            markRetryable(state.turns[state.turns.length - 1]);
        }

        // Auto-reopen mic on the same side
        onMicTap(turn.side);
    }

    function cancelSession(sessionId) {
        if (!sessionId) return;
        fetch('/api/chat/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        }).catch(err => console.warn('[Translation] cancel error', err));
    }

    // ============================================================
    //  Bubble helpers
    // ============================================================

    function makeBubble(text, kind) {
        const el = document.createElement('div');
        el.className = 'tr-bubble tr-bubble--' + kind.split(' ').join(' tr-bubble--');
        el.textContent = text;
        return el;
    }

    function scrollToBottom(side) {
        const list = els.bubbles[side];
        list.scrollTop = list.scrollHeight;
    }

    // ============================================================
    //  Boot
    // ============================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose minimal API for the chat manager / debugging
    window.translationMode = window.translationMode || {};
    window.translationMode.isActive = () => state.active;
})();
