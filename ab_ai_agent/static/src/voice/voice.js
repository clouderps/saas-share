/** @odoo-module **/
/**
 * Voice adapters for Ghaima AI — an interface to the same assistant.
 *
 *   SttProvider: start({ lang, onPartial }) → Promise<void>
 *                stop() → Promise<{ text }>     (throws VoiceError)
 *                cancel()
 *   TtsProvider: speak(text, lang) → Promise<void>   stop()
 *
 * Providers:
 *   browser — Web Speech API (SpeechRecognition / speechSynthesis).
 *             Free; availability and Arabic quality depend on the browser.
 *   server  — push-to-talk recording → 16 kHz mono WAV → the tenant's
 *             /ai_agent/voice/transcribe (AI provider or central gateway);
 *             /ai_agent/voice/speak for audio answers.
 *
 * pickStt/pickTts honour the company setting and fall back to whichever
 * works in this browser. Nothing listens until the user presses the mic;
 * nothing is recorded continuously; audio is not stored anywhere.
 */
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

const MAX_SECONDS = 60;

export class VoiceError extends Error {
    constructor(code) {
        super(code);
        this.code = code;
    }
}

/** User-facing text for every failure; never a technical message. */
export function voiceErrorMessage(code) {
    return {
        denied: _t("Microphone access is blocked. Allow it for this site in your browser, then try again."),
        no_mic: _t("No microphone was found."),
        unsupported: _t("Voice is not supported in this browser. You can type your question instead."),
        network: _t("Voice needs a network connection. Please try again."),
        empty: _t("I didn't catch that. Try again, a little closer to the microphone."),
        language: _t("This language is not supported for voice. Please type instead."),
        timeout: _t("That took too long. Please try again."),
        disabled: _t("Voice is turned off for this company."),
        no_voice: _t("No voice is available for this language."),
    }[code] || _t("Voice is unavailable right now. You can type your question instead.");
}

// ── Speech to text: browser ────────────────────────────────────────

const Recognition = typeof window !== "undefined"
    && (window.SpeechRecognition || window.webkitSpeechRecognition);

class BrowserStt {
    static id = "browser";
    static supported() {
        return !!Recognition;
    }
    start({ lang, onPartial } = {}) {
        return new Promise((resolve, reject) => {
            this._text = "";
            this._error = null;
            this._done = new Promise((res) => (this._finish = res));
            const r = new Recognition();
            r.lang = lang;
            r.continuous = false;
            r.interimResults = true;
            r.onresult = (ev) => {
                let t = "";
                for (let i = 0; i < ev.results.length; i++) {
                    t += ev.results[i][0].transcript;
                }
                this._text = t;
                onPartial?.(t);
            };
            r.onerror = (ev) => {
                this._error = {
                    "not-allowed": "denied", "service-not-allowed": "denied",
                    "audio-capture": "no_mic", network: "network",
                    "no-speech": "empty", "language-not-supported": "language",
                    aborted: "aborted",
                }[ev.error] || "failed";
            };
            r.onend = () => this._finish();
            r.onstart = () => resolve();
            try {
                r.start();
            } catch {
                reject(new VoiceError("failed"));
            }
            this._r = r;
        });
    }
    async stop() {
        try {
            this._r?.stop();
        } catch {
            // already stopped
        }
        await this._done;
        if (this._error && this._error !== "aborted") {
            throw new VoiceError(this._error);
        }
        const text = (this._text || "").trim();
        if (!text) {
            throw new VoiceError("empty");
        }
        return { text };
    }
    /** Resolves when recognition ended by itself (the user paused). */
    ended() {
        return this._done;
    }
    cancel() {
        this._error = "aborted";
        try {
            this._r?.abort();
        } catch {
            // nothing to abort
        }
    }
}

// ── Speech to text: server (record → WAV → transcribe) ─────────────

async function toWav16k(blob) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    let decoded;
    try {
        decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    } finally {
        ctx.close?.();
    }
    const rate = 16000;
    const frames = Math.max(1, Math.ceil(decoded.duration * rate));
    const off = new OfflineAudioContext(1, frames, rate);
    const src = off.createBufferSource();
    src.buffer = decoded;
    src.connect(off.destination);
    src.start();
    const pcm = (await off.startRendering()).getChannelData(0);
    const bytes = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const str = (o, s) => [...s].forEach((c, i) => bytes.setUint8(o + i, c.charCodeAt(0)));
    str(0, "RIFF");
    bytes.setUint32(4, 36 + pcm.length * 2, true);
    str(8, "WAVEfmt ");
    bytes.setUint32(16, 16, true);
    bytes.setUint16(20, 1, true);          // PCM
    bytes.setUint16(22, 1, true);          // mono
    bytes.setUint32(24, rate, true);
    bytes.setUint32(28, rate * 2, true);
    bytes.setUint16(32, 2, true);
    bytes.setUint16(34, 16, true);
    str(36, "data");
    bytes.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i++) {
        const v = Math.max(-1, Math.min(1, pcm[i]));
        bytes.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
    }
    let bin = "";
    const u8 = new Uint8Array(bytes.buffer);
    for (let i = 0; i < u8.length; i += 0x8000) {
        bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
    }
    return { b64: btoa(bin), seconds: decoded.duration };
}

class ServerStt {
    static id = "server";
    static supported() {
        return !!(navigator.mediaDevices?.getUserMedia && window.MediaRecorder
            && window.OfflineAudioContext);
    }
    async start({ lang } = {}) {
        this._lang = lang;
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (e) {
            throw new VoiceError(e?.name === "NotFoundError" ? "no_mic" : "denied");
        }
        this._stream = stream;
        this._chunks = [];
        this._rec = new MediaRecorder(stream);
        this._rec.ondataavailable = (ev) => ev.data.size && this._chunks.push(ev.data);
        this._stopped = new Promise((res) => (this._rec.onstop = res));
        this._rec.start();
        // Hard cap, a safety limit rather than a delay: a forgotten
        // recording must not run (and upload) forever.
        this._cap = setTimeout(() => this._rec?.state === "recording" && this._rec.stop(), MAX_SECONDS * 1000);
    }
    _release() {
        clearTimeout(this._cap);
        this._stream?.getTracks().forEach((t) => t.stop());
    }
    async stop() {
        if (this._rec?.state === "recording") {
            this._rec.stop();
        }
        await this._stopped;
        this._release();
        const blob = new Blob(this._chunks, { type: this._rec.mimeType || "audio/webm" });
        this._chunks = [];
        if (!blob.size) {
            throw new VoiceError("empty");
        }
        let wav;
        try {
            wav = await toWav16k(blob);
        } catch {
            throw new VoiceError("failed");
        }
        let res;
        try {
            res = await rpc("/ai_agent/voice/transcribe", {
                audio: wav.b64, mimetype: "audio/wav",
                lang: (this._lang || "").slice(0, 2), seconds: wav.seconds,
            }, { silent: true });
        } catch {
            throw new VoiceError("network");
        }
        if (!res?.ok) {
            throw new VoiceError(res?.error === "voice_disabled" ? "disabled"
                : res?.error === "empty" ? "empty" : "failed");
        }
        return { text: res.text };
    }
    cancel() {
        try {
            if (this._rec?.state === "recording") {
                this._rec.stop();
            }
        } catch {
            // ignore
        }
        this._chunks = [];
        this._release();
    }
}

export function pickStt(preferred) {
    const order = preferred === "server" ? [ServerStt, BrowserStt] : [BrowserStt, ServerStt];
    const Cls = order.find((C) => C.supported());
    return Cls ? new Cls() : null;
}

// ── Text to speech ─────────────────────────────────────────────────
//
// Desktop Chrome ships no Arabic voice: speechSynthesis "speaks" Arabic
// with nothing, silently. So the browser is used only when it really has
// a voice for the language; otherwise the answer is spoken by the AI
// service (/ai_agent/voice/speak — Gemini or OpenAI speech).

function browserVoiceFor(lang) {
    if (typeof window === "undefined" || !window.speechSynthesis) {
        return null;
    }
    const want = (lang || "").slice(0, 2).toLowerCase();
    return window.speechSynthesis.getVoices()
        .find((v) => (v.lang || "").toLowerCase().startsWith(want)) || null;
}

class BrowserTts {
    static supported() {
        return typeof window !== "undefined" && !!window.speechSynthesis;
    }
    canSpeak(lang) {
        return !!browserVoiceFor(lang);
    }
    speak(text, lang) {
        const voice = browserVoiceFor(lang);
        if (!voice) {
            return Promise.reject(new VoiceError("no_voice"));
        }
        return new Promise((resolve) => {
            const u = new SpeechSynthesisUtterance(text.slice(0, 1500));
            u.voice = voice;
            u.lang = voice.lang;
            u.onend = u.onerror = () => resolve();
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(u);
        });
    }
    stop() {
        window.speechSynthesis?.cancel();
    }
}

class ServerTts {
    async speak(text, lang) {
        let res;
        try {
            res = await rpc("/ai_agent/voice/speak",
                { text, lang: (lang || "").slice(0, 2) }, { silent: true });
        } catch {
            throw new VoiceError("network");
        }
        if (!res?.ok) {
            throw new VoiceError(res?.error === "voice_disabled" ? "disabled" : "failed");
        }
        this._audio = new Audio(`data:${res.mimetype};base64,${res.audio}`);
        return new Promise((resolve) => {
            this._audio.onended = this._audio.onerror = () => resolve();
            this._audio.play().catch(() => resolve());
        });
    }
    stop() {
        this._audio?.pause();
    }
}

/** Browser voice when it has one for the language, else the AI service. */
class AutoTts {
    constructor(preferServer) {
        this.preferServer = preferServer;
        this.browser = BrowserTts.supported() ? new BrowserTts() : null;
        this.server = new ServerTts();
    }
    async speak(text, lang) {
        const browserOk = this.browser && this.browser.canSpeak(lang);
        if (browserOk && !this.preferServer) {
            return this.browser.speak(text, lang);
        }
        try {
            return await this.server.speak(text, lang);
        } catch (e) {
            if (browserOk) {
                return this.browser.speak(text, lang);
            }
            throw e;
        }
    }
    stop() {
        this.browser?.stop();
        this.server.stop();
    }
}

export function pickTts(preferred) {
    // Warm the voice list: Chrome fills getVoices() asynchronously.
    if (BrowserTts.supported()) {
        window.speechSynthesis.getVoices();
    }
    return new AutoTts(preferred === "server");
}

/** Speakable text of an answer: prose only, no tables, markdown stripped. */
export function speakableText(text) {
    return String(text || "")
        .replace(/```[\s\S]*?```/g, " ")
        .replace(/^\s*\|.*\|\s*$/gm, " ")
        .replace(/[*_`#>]+/g, "")
        .replace(/\[(.*?)\]\(.*?\)/g, "$1")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 1500);
}
