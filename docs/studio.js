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
function getPosts(mode, evergreenDays) {
  const days = mode === 'recent' ? 21 : evergreenDays;
  const cutoff = new Date();
  if (days) cutoff.setDate(cutoff.getDate() - days);
  const posts = [];
  (window.rawData || []).forEach(acc => (acc.posts || []).forEach(p => {
    if (!days || new Date(p.date) >= cutoff) posts.push({ ...p, _a: acc.username });
  }));
  return posts;
}

function analyze(mode, evergreenDays) {
  const posts = getPosts(mode, evergreenDays);
  if (!posts.length) return null;

  // Top quartile by engagement rate = "winners"
  const byEr = [...posts].sort((a, b) => b.engagement_rate - a.engagement_rate);
  const winners = byEr.slice(0, Math.max(8, Math.ceil(byEr.length / 4)));

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
    avgEr: (winners.reduce((s, p) => s + p.engagement_rate, 0) / winners.length).toFixed(2),
  };
}

// ─── Vocabulary for the niche (blended with mined keywords) ──────────
const ROOMS  = ['living room', 'bedroom', 'kitchen', 'hallway', 'bathroom', 'home office', 'balcony', 'dining nook', 'reading corner'];
const ADJ    = ['cozy', 'calm', 'warm-minimal', 'moody', 'timeless', 'organic modern', 'quiet-luxury', 'scandi', 'japandi', 'lived-in'];
const THINGS = ['lighting', 'curtains', 'a vintage find', 'textured walls', 'layered textiles', 'a statement lamp', 'wall paneling', 'fresh flowers', 'open shelving', 'a rug that fits'];
const NUMS   = [3, 4, 5, 6, 7];

const pick = arr => arr[Math.floor(Math.random() * arr.length)];
const pickKw = a => (a.keywords.length > 2 ? pick(a.keywords.slice(0, 12)) : pick(ROOMS));

// ─── Template banks ───────────────────────────────────────────────────
// Each: { t: template fn, type: hook-type label, pot: base potential }
const REEL_TEMPLATES = [
  { type: 'Curiosity',    pot: 'High', t: a => `The one thing that made our ${pick(ROOMS)} finally feel finished` },
  { type: 'Curiosity',    pot: 'High', t: a => `Nobody talks about this when styling a ${pick(ROOMS)}…` },
  { type: 'Curiosity',    pot: 'Medium', t: a => `Why your ${pick(ROOMS)} feels off — and it's not the furniture` },
  { type: 'List',         pot: 'High', t: a => `${pick(NUMS)} ${pick(ADJ)} details that instantly upgrade any ${pick(ROOMS)}` },
  { type: 'List',         pot: 'High', t: a => `${pick(NUMS)} things I'd never buy again for our home` },
  { type: 'Mistake',      pot: 'High', t: a => `Stop doing this in your ${pick(ROOMS)} (it makes it look smaller)` },
  { type: 'Mistake',      pot: 'Medium', t: a => `The ${pickKw(a)} mistake almost everyone makes` },
  { type: 'Before/After', pot: 'High', t: a => `We gave our ${pick(ROOMS)} a weekend makeover — watch till the end` },
  { type: 'Before/After', pot: 'High', t: a => `POV: the landlord said "no changes" — we did this instead` },
  { type: 'Secret',       pot: 'Medium', t: a => `The most underrated ${pickKw(a)} trick in interior design` },
  { type: 'Secret',       pot: 'Medium', t: a => `IKEA won't tell you this, but…` },
  { type: 'How-to',       pot: 'Medium', t: a => `How we made our ${pick(ROOMS)} look expensive with ${pick(THINGS)}` },
  { type: 'Budget',       pot: 'High', t: a => `This cost us under 50€ and changed the whole ${pick(ROOMS)}` },
  { type: 'POV/Relatable', pot: 'Medium', t: a => `POV: you finally found your interior style after ${pick(NUMS)} tries` },
  { type: 'Aesthetic/Mood', pot: 'Experimental', t: a => `A ${pick(ADJ)} morning in our ${pick(ROOMS)} — sound on` },
];

const SLIDE_TEMPLATES = [
  { type: 'List',         pot: 'High', t: a => `${pick(NUMS)} ${pickKw(a)} ideas you'll want to save →` },
  { type: 'List',         pot: 'High', t: a => `${pick(NUMS)} ways to make a ${pick(ROOMS)} feel ${pick(ADJ)} (swipe)` },
  { type: 'Mistake',      pot: 'High', t: a => `${pick(NUMS)} decor mistakes that cheapen your home →` },
  { type: 'Curiosity',    pot: 'High', t: a => `The ${pick(ROOMS)} formula top creators keep using →` },
  { type: 'Curiosity',    pot: 'Medium', t: a => `What I'd do differently if I styled our ${pick(ROOMS)} again` },
  { type: 'Before/After', pot: 'High', t: a => `From bare to ${pick(ADJ)}: our ${pick(ROOMS)} in ${pick(NUMS)} steps →` },
  { type: 'Secret',       pot: 'Medium', t: a => `Underrated ${pickKw(a)} finds nobody gatekeeps enough →` },
  { type: 'Budget',       pot: 'High', t: a => `High-end look, small budget: ${pick(NUMS)} swaps that work →` },
  { type: 'How-to',       pot: 'Medium', t: a => `Save this: the exact steps to a ${pick(ADJ)} ${pick(ROOMS)} →` },
  { type: 'POV/Relatable', pot: 'Experimental', t: a => `Signs you're becoming an interior person → (slide 4 is too real)` },
];

const CTAS = [
  'Save this for your next room refresh 📌',
  'Which one would you try first? Tell me below ↓',
  'Follow for more slow, liveable interior ideas',
  'Send this to someone redecorating right now',
  'Comment "HOME" and I\'ll share the source list',
  'Save now, thank yourself on moving day',
];

const HASHTAG_POOL = ['#interiorinspo', '#homedecor', '#cozyhome', '#interiorstyling', '#apartmenttherapy', '#myhomevibe', '#scandinavianhome', '#japandistyle', '#homemakeover', '#slowliving', '#interiordesignideas', '#altbauliebe', '#interior4all', '#solebich'];

const CAPTION_BODIES = [
  a => `It took us way too long to figure this out: a ${pick(ROOMS)} doesn't need more furniture, it needs ${pick(THINGS)}.\n\nWe kept adding pieces and it still felt unfinished — until we focused on ${pickKw(a)} instead. One change, completely different room.`,
  a => `Honest take: most "${pick(ADJ)}" rooms you see online come down to ${pick(NUMS)} repeatable things — ${pick(THINGS)}, ${pick(THINGS)}, and light you can dim.\n\nNone of them are expensive. All of them are intentional.`,
  a => `We asked ourselves what actually makes a home feel calm — not photogenic, calm.\n\nThe answer kept coming back to ${pickKw(a)}. So this week we changed exactly that, and honestly? Best decision of the whole makeover.`,
  a => `Small confession: our ${pick(ROOMS)} used to be the room we closed the door on.\n\nWhat changed it wasn't a renovation — it was ${pick(THINGS)} plus finally committing to a ${pick(ADJ)} palette. Proof that you don't need a big budget, just a clear direction.`,
];

// ─── Generation ───────────────────────────────────────────────────────
function why(item, a) {
  const inTop = a.topHooks.slice(0, 3).includes(item.type);
  const kwNote = a.keywords.length ? `Trending words in winning captions: ${a.keywords.slice(0, 4).map(k => `"${k}"`).join(', ')}.` : '';
  return `${item.type} hooks ${inTop ? 'are among the top-performing patterns' : 'appear'} in the ${a.winners.length} best posts analyzed (avg ${a.avgEr}% ER, led by ${a.topAccounts.join(', ')}). ${kwNote}`;
}

function adjustPotential(item, a) {
  const rank = a.topHooks.indexOf(item.type);
  if (rank === 0) return 'High';
  if (rank > 3 || rank === -1) return item.pot === 'High' ? 'Medium' : item.pot;
  return item.pot;
}

function generate(kind) {
  const a = window._studioAnalysis;
  if (!a) return [];
  const bank = kind === 'reel' ? REEL_TEMPLATES : kind === 'slide' ? SLIDE_TEMPLATES : null;

  if (bank) {
    const shuffled = [...bank].sort(() => Math.random() - 0.5).slice(0, 7);
    return shuffled.map(tpl => {
      const text = tpl.t(a);
      return { text, type: tpl.type, pot: adjustPotential(tpl, a), why: why(tpl, a) };
    });
  }

  // Captions
  return Array.from({ length: 5 }, () => {
    const hookTpl = pick([...REEL_TEMPLATES.filter(t => t.pot === 'High')]);
    const hook = hookTpl.t(a);
    const body = pick(CAPTION_BODIES)(a);
    const cta = pick(CTAS);
    const useEmoji = a.emojiRate > 0.4;
    const tags = document.getElementById('st-hashtags').checked
      ? '\n\n' + [...HASHTAG_POOL].sort(() => Math.random() - 0.5).slice(0, 6).join(' ') : '';
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
  return `<div class="st-card">
    <div class="st-card-head">
      <span class="st-pot" style="color:${POT_COLORS[item.pot]};border-color:${POT_COLORS[item.pot]}40;background:${POT_COLORS[item.pot]}12">${item.pot}</span>
      <span class="st-type">${item.type}</span>
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
  const days = parseInt(document.getElementById('st-window').value);
  window._studioAnalysis = analyze(mode, mode === 'recent' ? null : days);
  const target = document.getElementById(`st-out-${kind}`);
  if (!window._studioAnalysis) {
    target.innerHTML = '<p class="st-empty">Not enough competitor data in this window. Try a longer timeframe or refresh the data.</p>';
    return;
  }
  const a = window._studioAnalysis;
  document.getElementById('st-insight').innerHTML =
    `Analyzed <strong>${a.posts} posts</strong> (${mode === 'recent' ? 'last 21 days' : days ? `last ${days} days` : 'all time'}) · top pattern: <strong>${a.topHooks[0] || '—'}</strong> · winners avg <strong>${a.avgEr}% ER</strong> · ${Math.round(a.videoShare * 100)}% of winners are Reels · emoji used in ${Math.round(a.emojiRate * 100)}% of top captions`;
  target.innerHTML = generate(kind).map(i => card(i, kind)).join('');
};

window.studioSetSrc = (btn) => {
  document.querySelectorAll('.st-src-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('st-window-wrap').style.display = btn.dataset.src === 'evergreen' ? 'inline-flex' : 'none';
};

// ─── Tab switching (Dashboard ↔ Studio) ──────────────────────────────
window.showTab = (tab) => {
  document.getElementById('dash-view').style.display = tab === 'dash' ? 'block' : 'none';
  document.getElementById('studio-view').style.display = tab === 'studio' ? 'block' : 'none';
  document.querySelectorAll('.nav-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
};

})();
