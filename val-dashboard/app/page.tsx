'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { AudioLines, Bot, Cpu, ExternalLink, Globe2, History, LoaderCircle, Mic, Mic2, Newspaper, RefreshCw, Search, Send, Settings, Square, Volume2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverDescription, PopoverHeader, PopoverTitle, PopoverTrigger } from '@/components/ui/popover';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const services = [
  { name: 'Language model', detail: 'Qwen3 4B', icon: Cpu },
  { name: 'Speech recognition', detail: 'Whisper Base English', icon: AudioLines },
  { name: 'Voice synthesis', detail: 'Piper · Alba · en-GB', icon: Volume2 },
];

type Message = { role: 'user' | 'assistant'; content: string };
type Conversation = { timestamp: string; source: 'voice' | 'web'; user: string; assistant: string };
type ExploreResult = { title: string; url: string; excerpt: string; source: string; published_at?: number | null };
type ResultSet = { kind: 'news' | 'search'; query: string; updated_at: number; count: number; results: ExploreResult[] };
type ExploreData = { news: ResultSet | null; search: ResultSet | null };
type DictationState = 'idle' | 'requesting' | 'recording' | 'transcribing';

export default function Home() {
  const [view, setView] = useState<'chat' | 'explore'>('chat');
  const [exploreMode, setExploreMode] = useState<'news' | 'search'>('news');
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  const [volume, setVolume] = useState(90);
  const [messages, setMessages] = useState<Message[]>([]);
  const [history, setHistory] = useState<Conversation[]>([]);
  const [explore, setExplore] = useState<ExploreData>({ news: null, search: null });
  const [waiting, setWaiting] = useState(false);
  const [exploreWaiting, setExploreWaiting] = useState(false);
  const [exploreError, setExploreError] = useState('');
  const [voiceState, setVoiceState] = useState<'awake' | 'sleeping' | 'unknown'>('unknown');
  const [dictationState, setDictationState] = useState<DictationState>('idle');
  const [dictationError, setDictationError] = useState('');
  const [dictationSupported, setDictationSupported] = useState(true);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const volumeTimer = useRef<number | null>(null);
  const sessionId = useRef('');
  const chatScroll = useRef<HTMLDivElement>(null);
  const newsAttempted = useRef(false);
  const messageInput = useRef<HTMLInputElement>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const mediaStream = useRef<MediaStream | null>(null);
  const audioChunks = useRef<Blob[]>([]);
  const recordingTimer = useRef<number | null>(null);

  useEffect(() => {
    const chat = chatScroll.current;
    if (chat) chat.scrollTop = chat.scrollHeight;
  }, [messages, waiting]);

  useEffect(() => {
    setDictationSupported(Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia));
    sessionId.current = `web-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
    void fetch('/api/history').then((response) => response.json() as Promise<{ conversations?: Conversation[] }>).then((data) => setHistory(data.conversations ?? []));
    void fetch('/api/volume').then((response) => response.json() as Promise<{ volume?: number }>).then((data) => {
      if (typeof data.volume === 'number') setVolume(data.volume);
    });
    const refreshVoice = () => void fetch('/api/voice-state').then((response) => response.json() as Promise<{ state?: 'awake' | 'sleeping' | 'unknown' }>).then((data) => setVoiceState(data.state ?? 'unknown')).catch(() => setVoiceState('unknown'));
    const refreshExplore = () => void fetch('/api/explore').then((response) => response.json() as Promise<ExploreData>).then((data) => {
      setExplore({ news: data.news ?? null, search: data.search ?? null });
      if (!data.news && !newsAttempted.current) {
        newsAttempted.current = true;
        void loadNews();
      }
    }).catch(() => setExploreError('Explore is currently unavailable.'));
    refreshVoice();
    refreshExplore();
    const voiceTimer = window.setInterval(refreshVoice, 3000);
    const exploreTimer = window.setInterval(refreshExplore, 8000);
    return () => {
      window.clearInterval(voiceTimer);
      window.clearInterval(exploreTimer);
      if (recordingTimer.current !== null) window.clearInterval(recordingTimer.current);
      if (mediaRecorder.current?.state === 'recording') mediaRecorder.current.stop();
      mediaStream.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function transcribeRecording(audio: Blob) {
    setDictationState('transcribing');
    setDictationError('');
    try {
      const extension = audio.type.includes('ogg') ? 'ogg' : audio.type.includes('mp4') ? 'm4a' : 'webm';
      const form = new FormData();
      form.append('file', audio, `val-dictation.${extension}`);
      const response = await fetch('/api/transcribe', { method: 'POST', body: form });
      const data = await response.json() as { text?: string; error?: string };
      if (!response.ok || !data.text) throw new Error(data.error || 'Transcription failed.');
      setMessage((current) => current.trim() ? `${current.trim()} ${data.text}` : data.text as string);
      window.setTimeout(() => messageInput.current?.focus(), 0);
    } catch (error) {
      setDictationError(error instanceof Error && error.message ? error.message : 'Speech recognition is currently unavailable.');
    } finally {
      setDictationState('idle');
    }
  }

  async function startDictation() {
    if (dictationState !== 'idle') return;
    setDictationError('');
    setDictationState('requesting');
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error('Browser microphone access requires a secure HTTPS connection.');
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      mediaStream.current = stream;
      audioChunks.current = [];
      const preferredTypes = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
      const mimeType = preferredTypes.find((type) => MediaRecorder.isTypeSupported(type));
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorder.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) audioChunks.current.push(event.data); };
      recorder.onerror = () => setDictationError('The browser could not record from this microphone.');
      recorder.onstop = () => {
        if (recordingTimer.current !== null) window.clearInterval(recordingTimer.current);
        recordingTimer.current = null;
        mediaStream.current?.getTracks().forEach((track) => track.stop());
        mediaStream.current = null;
        const audio = new Blob(audioChunks.current, { type: recorder.mimeType || 'audio/webm' });
        audioChunks.current = [];
        if (audio.size > 0) void transcribeRecording(audio);
        else {
          setDictationState('idle');
          setDictationError('No audio was recorded.');
        }
      };
      setRecordingSeconds(0);
      recorder.start(250);
      setDictationState('recording');
      recordingTimer.current = window.setInterval(() => {
        setRecordingSeconds((seconds) => {
          if (seconds >= 29 && mediaRecorder.current?.state === 'recording') mediaRecorder.current.stop();
          return seconds + 1;
        });
      }, 1000);
    } catch (error) {
      mediaStream.current?.getTracks().forEach((track) => track.stop());
      mediaStream.current = null;
      setDictationState('idle');
      if (error instanceof DOMException && error.name === 'NotAllowedError') {
        setDictationError('Microphone permission was denied. Allow it in your browser and try again.');
      } else {
        setDictationError(error instanceof Error && error.message ? error.message : 'The microphone is unavailable.');
      }
    }
  }

  function stopDictation() {
    if (mediaRecorder.current?.state === 'recording') mediaRecorder.current.stop();
  }

  async function sendMessage(event: FormEvent) {
    event.preventDefault();
    const content = message.trim();
    if (!content || waiting) return;
    const next: Message[] = [...messages, { role: 'user', content }];
    setMessages(next);
    setMessage('');
    setWaiting(true);
    try {
      const response = await fetch('/api/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ message: content, session_id: sessionId.current }) });
      const data = await response.json() as { response?: string; error?: string; conversation?: Conversation };
      setMessages([...next, { role: 'assistant', content: data.response ?? data.error ?? 'Val is unavailable.' }]);
      if (data.conversation) setHistory((items) => [...items, data.conversation as Conversation]);
    } catch {
      setMessages([...next, { role: 'assistant', content: 'Val is currently unreachable.' }]);
    } finally {
      setWaiting(false);
    }
  }

  async function loadNews() {
    setExploreWaiting(true);
    setExploreError('');
    try {
      const response = await fetch('/api/explore/news', { method: 'POST' });
      const data = await response.json() as ResultSet & { error?: string };
      if (!response.ok) throw new Error(data.error);
      setExplore((current) => ({ ...current, news: data }));
    } catch (error) {
      setExploreError(error instanceof Error && error.message ? error.message : 'News is currently unavailable.');
    } finally {
      setExploreWaiting(false);
    }
  }

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    const cleanQuery = query.trim();
    if (!cleanQuery || exploreWaiting) return;
    setExploreWaiting(true);
    setExploreError('');
    try {
      const response = await fetch('/api/explore/search', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ query: cleanQuery }) });
      const data = await response.json() as ResultSet & { error?: string };
      if (!response.ok) throw new Error(data.error);
      setExplore((current) => ({ ...current, search: data }));
    } catch (error) {
      setExploreError(error instanceof Error && error.message ? error.message : 'Web search is currently unavailable.');
    } finally {
      setExploreWaiting(false);
    }
  }

  function changeVolume(value: number | readonly number[]) {
    const nextVolume = Array.isArray(value) ? value[0] : value;
    if (typeof nextVolume !== 'number') return;
    setVolume(nextVolume);
    if (volumeTimer.current !== null) window.clearTimeout(volumeTimer.current);
    volumeTimer.current = window.setTimeout(() => {
      void fetch('/api/volume', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ volume: nextVolume }) });
    }, 250);
  }

  const currentResults = exploreMode === 'news' ? explore.news : explore.search;

  return (
    <Tabs value={view} onValueChange={(value) => setView(value as 'chat' | 'explore')} className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-white/8 bg-[#0d131c]">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-3 px-4 sm:px-7">
          <div className="mr-2 flex items-center gap-3 sm:mr-6"><div className="val-mark"><Bot size={19} /></div><div className="hidden sm:block"><p className="text-[15px] font-semibold tracking-[0.22em] text-white">VAL</p><p className="text-xs text-slate-400">Virtual AI Liaison</p></div></div>
          <TabsList variant="line" className="h-16 gap-2"><TabsTrigger value="chat" className="h-16 px-3 sm:px-5"><Bot />Chat</TabsTrigger><TabsTrigger value="explore" className="h-16 px-3 sm:px-5"><Globe2 />Explore</TabsTrigger></TabsList>
          <div className="ml-auto flex items-center gap-1">
            <div className={`sleep-state state-${voiceState} hidden sm:flex`}><span className={`h-1.5 w-1.5 rounded-full ${voiceState === 'awake' ? 'bg-emerald-400' : voiceState === 'sleeping' ? 'bg-violet-400' : 'bg-slate-500'}`} /> Voice: {voiceState === 'unknown' ? 'reconnecting' : voiceState}</div>
            <Popover><PopoverTrigger render={<Button variant="ghost" size="icon" className="text-slate-300 hover:bg-white/5 hover:text-white" aria-label={`Speaker volume ${volume} percent`} />}><Volume2 size={19} /></PopoverTrigger><PopoverContent align="end" className="border-[#314157] bg-[#111a27] p-4"><PopoverHeader><PopoverTitle>Speaker volume</PopoverTitle><PopoverDescription>Controls the server’s physical speakers.</PopoverDescription></PopoverHeader><div className="mt-2 flex items-center justify-between text-sm"><span className="text-slate-300">Output</span><strong className="text-sky-300">{volume}%</strong></div><Slider value={[volume]} onValueChange={changeVolume} max={100} step={1} className="mt-2" aria-label="Speaker volume" /></PopoverContent></Popover>
            <Dialog><DialogTrigger render={<Button variant="ghost" size="icon" className="text-slate-300 hover:bg-white/5 hover:text-white" aria-label="Conversation history" />}><History size={19} /></DialogTrigger><DialogContent className="max-h-[82vh] overflow-hidden border-white/10 bg-[#0b1119] sm:max-w-2xl"><DialogHeader><DialogTitle>Conversation history</DialogTitle><DialogDescription>Saved locally for voice and web conversations.</DialogDescription></DialogHeader><div className="history-list">{history.length === 0 ? <p className="py-12 text-center text-sm text-slate-400">No saved conversations yet.</p> : [...history].reverse().map((item, index) => <article className="history-entry" key={`${item.timestamp}-${index}`}><div className="history-meta"><span>{item.source}</span><time>{new Date(item.timestamp).toLocaleString()}</time></div><p><strong>User</strong>{item.user}</p><p><strong>Val</strong>{item.assistant}</p></article>)}</div></DialogContent></Dialog>
            <Dialog><DialogTrigger render={<Button variant="ghost" size="icon" className="text-slate-300 hover:bg-white/5 hover:text-white" aria-label="Val configuration" />}><Settings size={19} /></DialogTrigger><DialogContent className="border-white/10 bg-[#0b1119] sm:max-w-md"><DialogHeader><DialogTitle>Val configuration</DialogTitle><DialogDescription>Current local voice and model setup.</DialogDescription></DialogHeader><div className="space-y-1">{services.map(({ name, detail, icon: Icon }) => <div className="service-row" key={name}><div className="grid h-9 w-9 place-items-center rounded-lg bg-white/[.04] text-sky-300"><Icon size={17} /></div><div><p className="text-sm font-medium text-slate-200">{name}</p><p className="text-sm text-slate-400">{detail}</p></div></div>)}</div><div className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[.025] p-3"><Mic2 className="text-violet-300" size={18} /><div><p className="text-sm text-slate-200">HyperX microphone</p><p className="text-xs text-slate-400">Configured · 12× input gain</p></div></div></DialogContent></Dialog>
          </div>
        </div>
      </header>

      <TabsContent value="chat" className="m-0">
        <main className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-5xl flex-col px-4 py-5 sm:px-7 sm:py-7">
          <section className="panel flex min-h-[calc(100vh-8.5rem)] flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b border-white/7 px-5 py-4">
              <div><h1 className="text-lg font-semibold text-slate-100">Chat with Val</h1><p className="mt-1 text-sm text-slate-400">Local conversation</p></div>
              <span className="text-sm text-slate-400 sm:hidden">Voice: {voiceState}</span>
            </div>
            <div className="flex flex-1 flex-col justify-end p-4 sm:p-7">
              {messages.length === 0 ? <div className="mx-auto mb-auto mt-14 max-w-md text-center"><div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-2xl border border-sky-400/25 bg-[#14273b] text-sky-300"><Bot size={30} /></div><p className="text-2xl font-semibold tracking-tight text-slate-100">What’s on your mind?</p><p className="mt-2 text-base leading-7 text-slate-400">Say “Hey Val” near the room microphone, type, or dictate below.</p></div> : <div ref={chatScroll} className="mb-auto max-h-[62vh] space-y-4 overflow-y-auto pr-2">{messages.map((item, index) => <div key={`${item.role}-${index}`} className={`message ${item.role}`}><span className="message-label">{item.role === 'user' ? 'USER' : 'VAL'}</span><p>{item.content}</p></div>)}{waiting && <div className="message assistant"><span className="message-label">VAL</span><p className="thinking">Processing request<span>.</span><span>.</span><span>.</span></p></div>}</div>}
              <form className={`chat-composer mt-5 ${dictationState === 'recording' ? 'is-recording' : ''}`} onSubmit={sendMessage}>
                <Input ref={messageInput} aria-label="Message Val" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Message Val..." className="h-12 border-0 bg-transparent px-1 text-base text-slate-100 shadow-none placeholder:text-slate-400 focus-visible:ring-0" />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  disabled={!dictationSupported || dictationState === 'requesting' || dictationState === 'transcribing'}
                  onClick={dictationState === 'recording' ? stopDictation : () => void startDictation()}
                  className={`h-10 w-10 shrink-0 text-slate-300 hover:bg-white/6 hover:text-white ${dictationState === 'recording' ? 'dictation-active' : ''}`}
                  aria-label={dictationState === 'recording' ? 'Stop recording' : dictationState === 'transcribing' ? 'Transcribing speech' : 'Dictate message'}
                  title={dictationState === 'recording' ? 'Stop recording' : 'Dictate message'}
                >
                  {dictationState === 'recording' ? <Square size={15} fill="currentColor" /> : dictationState === 'requesting' || dictationState === 'transcribing' ? <LoaderCircle className="animate-spin" size={18} /> : <Mic size={18} />}
                </Button>
                <Button disabled={waiting || !message.trim()} size="icon" className="h-10 w-10 shrink-0 bg-sky-500 text-slate-950 hover:bg-sky-400" aria-label="Send message"><Send size={17} /></Button>
              </form>
              <div className="dictation-status" aria-live="polite">
                {dictationState === 'recording' ? <span className="text-red-300">Listening · {Math.floor(recordingSeconds / 60)}:{String(recordingSeconds % 60).padStart(2, '0')} · tap stop when finished</span> : dictationState === 'transcribing' ? <span className="text-violet-300">Transcribing locally…</span> : dictationState === 'requesting' ? <span>Waiting for microphone permission…</span> : dictationError ? <span role="alert" className="text-red-300">{dictationError}</span> : <span>{dictationSupported ? 'Microphone fills the text box for review · Enter sends' : 'Browser microphone access is unavailable on this connection'}</span>}
              </div>
            </div>
          </section>
        </main>
      </TabsContent>

      <TabsContent value="explore" className="m-0"><main className="mx-auto min-h-[calc(100vh-4rem)] max-w-[1440px] px-4 py-7 sm:px-7 sm:py-9"><div className="flex flex-col gap-5 border-b border-white/8 pb-6 md:flex-row md:items-end md:justify-between"><div><p className="mb-2 text-sm font-medium text-sky-300">Explore</p><h1 className="text-3xl font-semibold tracking-tight text-slate-100 sm:text-4xl">News and web search</h1><p className="mt-2 max-w-2xl text-base leading-7 text-slate-400">Current headlines and public search results. Val saves voice-requested links here too.</p></div><div className="inline-flex w-fit rounded-xl border border-[#2b3d52] bg-[#111a27] p-1"><Button type="button" variant="ghost" onClick={() => setExploreMode('news')} className={exploreMode === 'news' ? 'bg-[#1e3349] text-white hover:bg-[#1e3349]' : 'text-slate-400 hover:text-white'}><Newspaper />News</Button><Button type="button" variant="ghost" onClick={() => setExploreMode('search')} className={exploreMode === 'search' ? 'bg-[#1e3349] text-white hover:bg-[#1e3349]' : 'text-slate-400 hover:text-white'}><Search />Web search</Button></div></div>
        {exploreMode === 'search' ? <form onSubmit={runSearch} className="explore-search mt-6"><Search size={20} className="text-sky-300" /><Input value={query} onChange={(event) => setQuery(event.target.value)} maxLength={160} aria-label="Search the web" placeholder="Search the web..." className="h-12 flex-1 border-0 bg-transparent px-1 text-base text-white shadow-none placeholder:text-slate-400 focus-visible:ring-0" /><Button disabled={exploreWaiting || !query.trim()} className="bg-sky-500 text-slate-950 hover:bg-sky-400">Search</Button></form> : <div className="mt-6 flex items-center justify-between"><div><h2 className="text-xl font-semibold text-slate-100">Latest headlines</h2><p className="mt-1 text-sm text-slate-400">BBC News, NPR, and Ars Technica</p></div><Button variant="outline" onClick={() => void loadNews()} disabled={exploreWaiting} className="border-[#314157] bg-transparent text-slate-200 hover:bg-white/5"><RefreshCw className={exploreWaiting ? 'animate-spin' : ''} />Refresh</Button></div>}
        {exploreError && <div role="alert" className="mt-6 rounded-xl border border-red-400/25 bg-red-400/8 px-4 py-3 text-sm text-red-200">{exploreError}</div>}
        {exploreWaiting && !currentResults ? <div className="result-grid mt-6">{Array.from({ length: 6 }).map((_, index) => <div className="result-card" key={index}><Skeleton className="h-4 w-24 bg-white/8" /><Skeleton className="mt-4 h-6 w-4/5 bg-white/8" /><Skeleton className="mt-4 h-4 w-full bg-white/8" /><Skeleton className="mt-2 h-4 w-3/4 bg-white/8" /></div>)}</div> : currentResults ? <><div className="mt-6 flex items-center justify-between text-sm text-slate-400"><span>{currentResults.count} results{currentResults.kind === 'search' ? ` for “${currentResults.query}”` : ''}</span><time>Updated {new Date(currentResults.updated_at * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</time></div><div className="result-grid mt-4">{currentResults.results.map((result, index) => <article className="result-card" key={`${result.url}-${index}`}><div className="flex items-center justify-between gap-3"><span className="result-source">{result.source}</span>{result.published_at ? <time className="text-xs text-slate-400">{new Date(result.published_at * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time> : null}</div><h2 className="mt-4 text-xl font-semibold leading-7 text-slate-100"><a href={result.url} target="_blank" rel="noreferrer" className="hover:text-sky-300">{result.title}</a></h2>{result.excerpt ? <p className="mt-3 text-sm leading-6 text-slate-300">{result.excerpt}</p> : null}<a href={result.url} target="_blank" rel="noreferrer" className="mt-auto flex items-center gap-2 pt-5 text-sm font-medium text-sky-300 hover:text-sky-200">Open result <ExternalLink size={15} /></a></article>)}</div></> : <div className="mt-12 rounded-2xl border border-dashed border-[#314157] py-16 text-center"><Globe2 className="mx-auto text-slate-500" size={30} /><p className="mt-4 text-base text-slate-300">Your latest results will appear here.</p></div>}
      </main></TabsContent>
    </Tabs>
  );
}
