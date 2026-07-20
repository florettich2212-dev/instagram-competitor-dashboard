// ─── Content Studio — competitor-driven hook & caption generator ──────
// Mines patterns from data.json (hooks, keywords, CTAs, emoji usage) and
// blends them into original template-based generations. No external API.

(() => {

// ─── Analysis: stopwords (EN + DE) ────────────────────────────────────
const STOP = new Set(('the a an and or but if of to in on for with at by from up is are was were be been it its this that these those you your i my we our us me he she they them his her their as so not no do does did done have has had will would can could should just more most very really about into over after before out only own same than too s t don now am pm der die das ein eine einer eines einem einen und oder aber wenn von zu im in auf für mit bei aus ist sind war waren sein bin bist es sie er wir ihr ich mein meine mein dein deine unser unsere euch mich dich ihn wie so nicht kein keine noch mehr sehr auch nur schon mal man hat habe haben hatte wird werden kann können soll sollen muss müssen dann denn doch da hier dort was wer wo wann warum welche welcher welches euch uns als bis durch gegen ohne um an dem den des zur zum').split(' '));

const EMOJI_RE   = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu;   // for replace()
const EMOJI_TEST = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/u;    // for test() — no /g (stateful lastIndex)

// ─── Hook-type classifiers (run against competitor captions) ─────────
const HOOK_TYPES = [
  { id: 'question',  label: 'Curiosity',      re: /\?|would you|könntest du|wusstest du|did you know|have you ever|hättest du/i },
  { id: 'list',      label: 'List',           re: /\b\d+\s+(things|ways|ideas|tips|tricks|hacks|mistakes|dinge|tipps|ideen|fehler|tricks)\b|\btop\s*\d+/i },
  { id: 'beforeafter', label: 'Before/After', re: /before.*after|vorher.*nachher|transformation|makeover|glow.?up/i },
  { id: 'secret',    label: 'Secret',         re: /secret|niemand|nobody (tells|talks)|geheim|hidden|underrated|unterschätzt/i },
  { id: 'mistake',   label: 'Mistake',        re: /mistake|fehler|stop doing|wrong|falsch|avoid|vermeide/i },
  { id: 'pov',       label: 'POV/Relatable',  re: /\bpov\b|when you|wenn du|that feeling|dieses gefühl|me when/i },
  { id: 'howto',     label: 'How-to',         re: /how (i|we|to)|wie (ich|wir|du)|so (habe|haben|geht)|step by step|schritt für schritt|tutorial|diy/i },
  { id: 'budget',    label: 'Budget',         re: /budget|cheap|günstig|affordable|under \d+|unter \d+|€|ikea hack|for less/i },
];

function classifyHook(text) {
  for (const h of HOOK_TYPES) if (h.re.test(text)) return h;
  return { id: 'aesthetic', label: 'Aesthetic/Mood' };
}

// ─── Corpus analysis ──────────────────────────────────────────────────
function getPosts(mode) {
  const days = mode === 'recent' ? 21 : null; // Trending = 21 days, Proven Concepts = all time
  const cutoff = new Date();
  if (days) cutoff.setDate(cutoff.getDate() - days);
  const posts = [];
  (window.rawData || []).forEach(acc => (acc.posts || []).forEach(p => {
    if (!days || new Date(p.date) >= cutoff) posts.push({ ...p, _a: acc.username });
  }));
  return posts;
}

// Winner score = views + likes (views only exist for Reels; 0 until first scrape with views)
const score = p => (p.views || 0) + (p.likes || 0);

function analyze(mode) {
  const posts = getPosts(mode);
  if (!posts.length) return null;

  // Top quartile by views + likes = "winners"
  const ranked = [...posts].sort((a, b) => score(b) - score(a));
  const winners = ranked.slice(0, Math.max(8, Math.ceil(ranked.length / 4)));

  // Keyword frequency from winner captions
  const freq = {};
  let emojiPosts = 0;
  const hookCounts = {};
  winners.forEach(p => {
    const cap = p.caption || '';
    if (EMOJI_TEST.test(cap)) emojiPosts++;
    const h = classifyHook(cap);
    hookCounts[h.label] = (hookCounts[h.label] || 0) + 1;
    cap.toLowerCase().replace(EMOJI_RE, ' ').replace(/[#@][\w.]+/g, ' ')
      .split(/[^a-zäöüß]+/i).forEach(w => {
        if (w.length > 3 && !STOP.has(w)) freq[w] = (freq[w] || 0) + 1;
      });
  });
  const keywords = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 25).map(e => e[0]);
  const topHooks = Object.entries(hookCounts).sort((a, b) => b[1] - a[1]).map(e => e[0]);
  const videoShare = winners.filter(p => p.is_video).length / winners.length;

  return {
    posts: posts.length,
    winners,
    keywords,
    topHooks,
    emojiRate: emojiPosts / winners.length,
    videoShare,
    topAccounts: [...new Set(winners.slice(0, 10).map(p => '@' + p._a))].slice(0, 4),
    avgLikes: Math.round(winners.reduce((s, p) => s + (p.likes || 0), 0) / winners.length),
    avgViews: Math.round(winners.reduce((s, p) => s + (p.views || 0), 0) / winners.length),
  };
}

const fmtN = n => !n ? '0' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1000 ? (n / 1000).toFixed(1) + 'K' : '' + n;

// ─── Base vocabulary (blended with mined keywords, style can override) ─
const ROOMS  = ['living room', 'bedroom', 'kitchen', 'hallway', 'bathroom', 'home office', 'balcony', 'dining nook', 'reading corner'];
const ADJ    = ['cozy', 'calm', 'warm-minimal', 'moody', 'timeless', 'organic modern', 'quiet-luxury', 'scandi', 'japandi', 'lived-in'];
const THINGS = ['lighting', 'curtains', 'a vintage find', 'textured walls', 'layered textiles', 'a statement lamp', 'wall paneling', 'fresh flowers', 'open shelving', 'a rug that fits'];
const NUMS   = [3, 4, 5, 6, 7];

const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const S = () => STYLES[currentStyle];
const room  = () => pick(S().rooms  || ROOMS);
const adj   = () => pick(S().adj    || ADJ);
const thing = () => pick(S().things || THINGS);
const num   = () => pick(NUMS);
const pickKw = a => (a.keywords.length > 2 ? pick(a.keywords.slice(0, 12)) : room());

// ─── Style layer ──────────────────────────────────────────────────────
const CTAS = [
  'Save this for your next room refresh 📌',
  'Which one would you try first? Tell me below ↓',
  'Follow for more slow, liveable interior ideas',
  'Send this to someone redecorating right now',
  'Comment "HOME" and I\'ll share the source list',
  'Save now, thank yourself on moving day',
];

function shortenHook(t) {
  let s = t.replace(/\s*[—(].*$/, '').trim();
  let words = s.split(' ');
  if (words.length > 9) {
    words = words.slice(0, 9);
    // don't end on a dangling connector word
    while (words.length && /^(with|for|of|to|a|an|the|and|in|on|any|our|your|my)$/i.test(words[words.length - 1])) words.pop();
    s = words.join(' ') + '…';
  }
  return s;
}

const STYLES = {
  default: {
    label: 'Default', desc: 'Balanced, engaging — pure competitor patterns.',
  },
  shorter: {
    label: 'Shorter', desc: 'Cuts length ~40% while keeping the key message.',
    post: shortenHook, captionParas: 1, hashtagCount: 3,
  },
  hooky: {
    label: 'More Hooky', desc: 'Opening impossible to ignore — curiosity in the first line.',
    preferTypes: ['Curiosity', 'Secret', 'Mistake'],
    prefixes: ['Wait —', 'Be honest:', 'No one tells you this:', 'Read this before you decorate:'],
  },
  viral: {
    label: 'More Viral', desc: 'More emotional impact, curiosity and pattern interrupts — no clickbait.',
    preferTypes: ['Before/After', 'Mistake', 'Curiosity', 'Budget'],
    suffixes: [' — watch till the end', ' (nobody talks about this)', ' — I wish I\'d known this sooner', ' …and it took one afternoon'],
    ctas: ['Comment "HOME" and I\'ll send you the full list', 'Tag someone who needs to see this', 'Save this before your next room refresh — you\'ll forget otherwise', 'Share this with your group chat, someone is redecorating'],
  },
  story: {
    label: 'More Storytelling', desc: 'Setup, conflict, resolution — content that reads like a story.',
    preferTypes: ['Before/After', 'POV/Relatable', 'How-to'],
    extraHooks: [
      { type: 'Before/After', pot: 'High',   t: a => `We almost gave up on our ${room()} — here's what saved it` },
      { type: 'POV/Relatable', pot: 'Medium', t: a => `A year ago this ${room()} made us want to move. Today it's our favorite room.` },
      { type: 'Before/After', pot: 'High',   t: a => `From "we'll fix it someday" to this — the ${room()} story` },
    ],
    bodies: [
      a => `When we moved in, the ${room()} was the room we apologized for. Bad light, no plan, furniture that never belonged together.\n\nThe turning point wasn't a big budget — it was admitting the layout was the problem. We stripped it back, started with ${thing()}, and let the room tell us what it needed.\n\nNow it's where every evening ends. Sometimes the ugliest room becomes the best one — it just needs a story arc.`,
      a => `Six months ago I stood in this ${room()} close to tears. Everything we tried made it worse, and every saved inspo photo felt out of reach.\n\nThen one small thing changed: we stopped copying and started with ${pickKw(a)}. One honest decision led to the next.\n\nThe room you're seeing is the resolution of that fight. If you're mid-makeover and tired — keep going. The turning point is usually one decision away.`,
      a => `Every home has one room that resists you. Ours was the ${room()}.\n\nWe tried three layouts, returned more than we kept, and nearly settled for "good enough". The fix was embarrassingly simple: ${thing()}, and the patience to wait for the right pieces.\n\nMoral of the story: rooms aren't finished when they're full. They're finished when they feel inevitable.`,
    ],
    ctas: ['The full story doesn\'t fit in a caption — ask me anything below ↓', 'Save this if you\'re mid-makeover and tired', 'Follow along — the next room is already in progress'],
  },
  casual: {
    label: 'More Casual', desc: 'Like talking to a friend — relaxed, natural, real.',
    prefixes: ['Okay so —', 'Honestly?', 'Real talk:', 'Not me saying this out loud but —'],
    forceEmoji: true,
    ctas: ['lmk which one you\'d actually try 👇', 'save this for later, future you says thanks 🫶', 'send this to your redecorating bestie', 'anyway. follow for more of our chaos-to-cozy journey ✌️'],
  },
  direct: {
    label: 'More Direct', desc: 'No fluff — straight to the point.',
    preferTypes: ['List', 'Mistake', 'How-to', 'Budget'],
    post: t => shortenHook(t.replace(/\b(finally|actually|honestly|literally|really)\s/gi, '')),
    captionParas: 1, noEmoji: true, hashtagCount: 4,
    bodies: [
      a => `The fix for a ${room()} that feels off: ${thing()}. Not more furniture. Not a bigger budget. That one change.`,
      a => `${num()} rules that work in every ${room()}:\n\n1. Fewer, bigger pieces.\n2. Warm light only.\n3. ${thing().charAt(0).toUpperCase() + thing().slice(1)} before decor.\n\nDo these first. Everything else is detail.`,
      a => `Most rooms don't need a makeover. They need ${pickKw(a)} fixed.\n\nStart there. Takes one afternoon.`,
    ],
    ctas: ['Save this. You\'ll need it.', 'Try it this weekend, then tell me I was wrong.', 'Follow for interior advice without the fluff.'],
  },
  emotional: {
    label: 'More Emotional', desc: 'Feelings and relatable moments front and center.',
    preferTypes: ['POV/Relatable', 'Aesthetic/Mood', 'Before/After'],
    extraHooks: [
      { type: 'POV/Relatable', pot: 'High', t: a => `The moment our ${room()} finally felt like *home* — I didn't expect it to hit this hard` },
      { type: 'POV/Relatable', pot: 'Medium', t: a => `Nobody warns you how emotional finishing a ${room()} actually is` },
    ],
    bodies: [
      a => `There's a specific feeling when a room finally holds you instead of just housing you.\n\nFor us it happened in the ${room()} — the first evening the light was warm, the ${thing()} was in place, and nobody wanted to leave. That's the whole point of all of this, isn't it?\n\nNot a perfect home. A home that feels like the people in it.`,
      a => `I used to scroll past ${adj()} homes thinking that feeling was for other people.\n\nThen we changed one thing — ${pickKw(a)} — and suddenly our ${room()} was the place where the good moments happen. The Sunday coffees. The late talks. The quiet.\n\nYour home is allowed to be a feeling, not a checklist.`,
    ],
    ctas: ['Tell me I\'m not the only one 🥹', 'Save this if your home is your safe place', 'Send this to someone building their first real home ♡'],
  },
};

let currentStyle = 'default';

// ─── Template banks ───────────────────────────────────────────────────
const REEL_TEMPLATES = [
  { type: 'Curiosity',    pot: 'High', t: a => `The one thing that made our ${room()} finally feel finished` },
  { type: 'Curiosity',    pot: 'High', t: a => `Nobody talks about this when styling a ${room()}…` },
  { type: 'Curiosity',    pot: 'Medium', t: a => `Why your ${room()} feels off — and it's not the furniture` },
  { type: 'List',         pot: 'High', t: a => `${num()} ${adj()} details that instantly upgrade any ${room()}` },
  { type: 'List',         pot: 'High', t: a => `${num()} things I'd never buy again for our home` },
  { type: 'Mistake',      pot: 'High', t: a => `Stop doing this in your ${room()} (it makes it look smaller)` },
  { type: 'Mistake',      pot: 'Medium', t: a => `The ${pickKw(a)} mistake almost everyone makes` },
  { type: 'Before/After', pot: 'High', t: a => `We gave our ${room()} a weekend makeover — watch till the end` },
  { type: 'Before/After', pot: 'High', t: a => `POV: the landlord said "no changes" — we did this instead` },
  { type: 'Secret',       pot: 'Medium', t: a => `The most underrated ${pickKw(a)} trick in interior design` },
  { type: 'Secret',       pot: 'Medium', t: a => `IKEA won't tell you this, but…` },
  { type: 'How-to',       pot: 'Medium', t: a => `How we made our ${room()} look expensive with ${thing()}` },
  { type: 'Budget',       pot: 'High', t: a => `This cost us under 50€ and changed the whole ${room()}` },
  { type: 'POV/Relatable', pot: 'Medium', t: a => `POV: you finally found your interior style after ${num()} tries` },
  { type: 'Aesthetic/Mood', pot: 'Experimental', t: a => `A ${adj()} morning in our ${room()} — sound on` },
];

const SLIDE_TEMPLATES = [
  { type: 'List',         pot: 'High', t: a => `${num()} ${pickKw(a)} ideas you'll want to save →` },
  { type: 'List',         pot: 'High', t: a => `${num()} ways to make a ${room()} feel ${adj()} (swipe)` },
  { type: 'Mistake',      pot: 'High', t: a => `${num()} decor mistakes that cheapen your home →` },
  { type: 'Curiosity',    pot: 'High', t: a => `The ${room()} formula top creators keep using →` },
  { type: 'Curiosity',    pot: 'Medium', t: a => `What I'd do differently if I styled our ${room()} again` },
  { type: 'Before/After', pot: 'High', t: a => `From bare to ${adj()}: our ${room()} in ${num()} steps →` },
  { type: 'Secret',       pot: 'Medium', t: a => `Underrated ${pickKw(a)} finds nobody gatekeeps enough →` },
  { type: 'Budget',       pot: 'High', t: a => `High-end look, small budget: ${num()} swaps that work →` },
  { type: 'How-to',       pot: 'Medium', t: a => `Save this: the exact steps to a ${adj()} ${room()} →` },
  { type: 'POV/Relatable', pot: 'Experimental', t: a => `Signs you're becoming an interior person → (slide 4 is too real)` },
];

const HASHTAG_POOL = ['#interiorinspo', '#homedecor', '#cozyhome', '#interiorstyling', '#apartmenttherapy', '#myhomevibe', '#scandinavianhome', '#japandistyle', '#homemakeover', '#slowliving', '#interiordesignideas', '#altbauliebe', '#interior4all', '#solebich'];

const CAPTION_BODIES = [
  a => `It took us way too long to figure this out: a ${room()} doesn't need more furniture, it needs ${thing()}.\n\nWe kept adding pieces and it still felt unfinished — until we focused on ${pickKw(a)} instead. One change, completely different room.`,
  a => `Honest take: most "${adj()}" rooms you see online come down to ${num()} repeatable things — ${thing()}, ${thing()}, and light you can dim.\n\nNone of them are expensive. All of them are intentional.`,
  a => `We asked ourselves what actually makes a home feel calm — not photogenic, calm.\n\nThe answer kept coming back to ${pickKw(a)}. So this week we changed exactly that, and honestly? Best decision of the whole makeover.`,
  a => `Small confession: our ${room()} used to be the room we closed the door on.\n\nWhat changed it wasn't a renovation — it was ${thing()} plus finally committing to a ${adj()} palette. Proof that you don't need a big budget, just a clear direction.`,
];

// ─── Generation ───────────────────────────────────────────────────────
function why(item, a) {
  const inTop = a.topHooks.slice(0, 3).includes(item.type);
  const reach = a.avgViews ? `avg ${fmtN(a.avgViews)} views · ${fmtN(a.avgLikes)} likes` : `avg ${fmtN(a.avgLikes)} likes`;
  const kwNote = a.keywords.length ? `Trending words in winning captions: ${a.keywords.slice(0, 4).map(k => `"${k}"`).join(', ')}.` : '';
  return `${item.type} hooks ${inTop ? 'are among the top-performing patterns' : 'appear'} in the ${a.winners.length} best posts analyzed (${reach}, led by ${a.topAccounts.join(', ')}). ${kwNote}`;
}

function adjustPotential(item, a) {
  const rank = a.topHooks.indexOf(item.type);
  if (rank === 0) return 'High';
  if (rank > 3 || rank === -1) return item.pot === 'High' ? 'Medium' : item.pot;
  return item.pot;
}

function styleBank(bank, kind) {
  const st = S();
  let b = [...bank, ...(st.extraHooks || [])];
  if (st.banTypes) b = b.filter(t => !st.banTypes.includes(t.type));
  const shuffled = b.sort(() => Math.random() - 0.5);
  if (!st.preferTypes) return shuffled.slice(0, 7);
  // ~5 preferred + 2 wildcards so preferred patterns dominate without being monotone
  const pref = shuffled.filter(t => st.preferTypes.includes(t.type));
  const rest = shuffled.filter(t => !st.preferTypes.includes(t.type));
  return [...pref.slice(0, 5), ...rest.slice(0, 7 - Math.min(5, pref.length))];
}

function styleHookText(text) {
  const st = S();
  let t = text;
  if (st.post) t = st.post(t);
  if (st.prefixes && Math.random() < 0.6) t = `${pick(st.prefixes)} ${t.charAt(0).toLowerCase() + t.slice(1)}`;
  if (st.suffixes && Math.random() < 0.5 && !/[—…→)]$/.test(t.trim())) t = t + pick(st.suffixes);
  return t;
}

function generate(kind) {
  const a = window._studioAnalysis;
  if (!a) return [];
  const st = S();
  const bank = kind === 'reel' ? REEL_TEMPLATES : kind === 'slide' ? SLIDE_TEMPLATES : null;

  if (bank) {
    return styleBank(bank, kind).map(tpl => ({
      text: styleHookText(tpl.t(a)),
      type: tpl.type,
      pot: adjustPotential(tpl, a),
      why: why(tpl, a),
    }));
  }

  // Captions
  const bodies = st.bodies || CAPTION_BODIES;
  const ctas = st.ctas || CTAS;
  const hookPool = styleBank(REEL_TEMPLATES, 'reel').filter(t => t.pot !== 'Experimental');
  return Array.from({ length: 5 }, () => {
    const hookTpl = pick(hookPool.length ? hookPool : REEL_TEMPLATES);
    const hook = styleHookText(hookTpl.t(a));
    let body = pick(bodies)(a);
    if (st.captionParas) body = body.split('\n\n').slice(0, st.captionParas).join('\n\n');
    const cta = pick(ctas);
    const useEmoji = st.noEmoji ? false : (st.forceEmoji || a.emojiRate > 0.4);
    const tagCount = st.hashtagCount || 6;
    const tags = document.getElementById('st-hashtags').checked
      ? '\n\n' + [...HASHTAG_POOL].sort(() => Math.random() - 0.5).slice(0, tagCount).join(' ') : '';
    const text = `${useEmoji ? '✨ ' : ''}${hook}\n\n${body}\n\n${cta}${tags}`;
    return { text, type: hookTpl.type, pot: adjustPotential(hookTpl, a), why: why(hookTpl, a) };
  });
}

// ─── Favorites / export ───────────────────────────────────────────────
const favs = () => JSON.parse(localStorage.getItem('studio_favs') || '[]');
window.studioFav = (btn, encoded) => {
  const text = decodeURIComponent(encoded);
  const f = favs();
  if (!f.includes(text)) { f.push(text); localStorage.setItem('studio_favs', JSON.stringify(f)); }
  btn.textContent = '★ Saved';
};
window.studioCopy = (btn, encoded) => {
  navigator.clipboard.writeText(decodeURIComponent(encoded));
  const old = btn.textContent; btn.textContent = '✓ Copied';
  setTimeout(() => btn.textContent = old, 1500);
};
window.studioExport = () => {
  const f = favs();
  const blob = new Blob([f.length ? f.join('\n\n———\n\n') : 'No favorites saved yet.'], { type: 'text/plain' });
  const aEl = document.createElement('a');
  aEl.href = URL.createObjectURL(blob);
  aEl.download = 'content-studio-favorites.txt';
  aEl.click();
};

// ─── UI ───────────────────────────────────────────────────────────────
const POT_COLORS = { High: '#34c759', Medium: '#ff9500', Experimental: '#af52de' };

function card(item, kind) {
  const enc = encodeURIComponent(item.text);
  const styleChip = currentStyle !== 'default' ? ` · ${S().label}` : '';
  return `<div class="st-card">
    <div class="st-card-head">
      <span class="st-pot" style="color:${POT_COLORS[item.pot]};border-color:${POT_COLORS[item.pot]}40;background:${POT_COLORS[item.pot]}12">${item.pot}</span>
      <span class="st-type">${item.type}${styleChip}</span>
    </div>
    <div class="st-text${kind === 'caption' ? ' st-text-multi' : ''}">${item.text.replace(/\n/g, '<br>')}</div>
    <div class="st-why">${item.why}</div>
    <div class="st-actions">
      <button onclick="studioCopy(this,'${enc}')">Copy</button>
      <button onclick="studioFav(this,'${enc}')">☆ Save</button>
    </div>
  </div>`;
}

window.studioRun = (kind) => {
  const mode = document.querySelector('.st-src-btn.active')?.dataset.src || 'recent';
  window._studioAnalysis = analyze(mode);
  const target = document.getElementById(`st-out-${kind}`);
  if (!window._studioAnalysis) {
    target.innerHTML = '<p class="st-empty">Not enough competitor data yet. Refresh the data and try again.</p>';
    return;
  }
  const a = window._studioAnalysis;
  const reach = a.avgViews ? `<strong>${fmtN(a.avgViews)} views · ${fmtN(a.avgLikes)} likes</strong>` : `<strong>${fmtN(a.avgLikes)} likes</strong>`;
  document.getElementById('st-insight').innerHTML =
    `Analyzed <strong>${a.posts} posts</strong> (${mode === 'recent' ? 'trending — last 21 days' : 'proven concepts — all time'}) · top pattern: <strong>${a.topHooks[0] || '—'}</strong> · winners avg ${reach} · ${Math.round(a.videoShare * 100)}% of winners are Reels · emoji used in ${Math.round(a.emojiRate * 100)}% of top captions`;
  target.innerHTML = generate(kind).map(i => card(i, kind)).join('');
};

window.studioSetSrc = (btn) => {
  document.querySelectorAll('.st-src-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Re-generate any sections that already have output
  ['reel', 'slide', 'caption'].forEach(kind => {
    if (document.querySelector(`#st-out-${kind} .st-card`)) window.studioRun(kind);
  });
};

window.studioSetStyle = (btn) => {
  currentStyle = btn.dataset.style;
  document.querySelectorAll('.st-style-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('st-style-desc').textContent = S().desc;
  // Re-generate any sections that already have output, so the style applies instantly
  ['reel', 'slide', 'caption'].forEach(kind => {
    if (document.querySelector(`#st-out-${kind} .st-card`)) window.studioRun(kind);
  });
};

// Build style buttons
document.addEventListener('DOMContentLoaded', () => {
  const wrap = document.getElementById('st-styles');
  if (!wrap) return;
  wrap.innerHTML = Object.entries(STYLES).map(([id, st]) =>
    `<button class="st-style-btn${id === 'default' ? ' active' : ''}" data-style="${id}" title="${st.desc}" onclick="studioSetStyle(this)">${st.label}</button>`
  ).join('');
  document.getElementById('st-style-desc').textContent = STYLES.default.desc;
});

// ─── Tab switching (Dashboard ↔ Studio) ──────────────────────────────
window.showTab = (tab) => {
  document.getElementById('dash-view').style.display = tab === 'dash' ? 'block' : 'none';
  document.getElementById('studio-view').style.display = tab === 'studio' ? 'block' : 'none';
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
};

})();
