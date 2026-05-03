// ==================================================================
// 共通ヘルパー
// ==================================================================
window.Dash = {
  fmtNum(x, d = 2) {
    if (x === null || x === undefined || (typeof x === 'number' && !isFinite(x))) return '—';
    if (Math.abs(x) >= 1000) return x.toLocaleString(undefined, { maximumFractionDigits: 0 });
    return x.toLocaleString(undefined, { maximumFractionDigits: d });
  },
  fmtPct(x, d = 2) {
    if (x === null || x === undefined) return '—';
    const sign = x >= 0 ? '+' : '';
    return `${sign}${x.toFixed(d)}%`;
  },
  fmtSigned(x, d = 2) {
    if (x === null || x === undefined) return '—';
    const sign = x >= 0 ? '+' : '';
    return `${sign}${x.toLocaleString(undefined, { maximumFractionDigits: d })}`;
  },
  fmtMcap(x, currency = 'USD') {
    if (!x) return '—';
    const unit = currency === 'JPY' ? '円' : '$';
    if (currency === 'JPY') {
      if (x >= 1e12) return `${(x / 1e12).toFixed(2)}兆${unit}`;
      if (x >= 1e8) return `${(x / 1e8).toFixed(0)}億${unit}`;
      return `${x.toLocaleString()}${unit}`;
    } else {
      if (x >= 1e12) return `${unit}${(x / 1e12).toFixed(2)}T`;
      if (x >= 1e9) return `${unit}${(x / 1e9).toFixed(2)}B`;
      if (x >= 1e6) return `${unit}${(x / 1e6).toFixed(0)}M`;
      return `${unit}${x.toLocaleString()}`;
    }
  },
  klass(x) {
    if (x === null || x === undefined || isNaN(x)) return 'flat';
    return x > 0 ? 'up' : x < 0 ? 'down' : 'flat';
  },
  // ヒートマップ用カラー（緑↔赤、白を中心）
  heatColor(value, max = 3) {
    if (value === null || value === undefined || isNaN(value)) return '#e0e0d8';
    const x = Math.max(-max, Math.min(max, value));
    if (x >= 0) {
      const t = x / max;
      const r = Math.round(255 - (255 - 17) * t);
      const g = Math.round(255 - (255 - 122) * t);
      const b = Math.round(255 - (255 - 61) * t);
      return `rgb(${r},${g},${b})`;
    } else {
      const t = -x / max;
      const r = Math.round(255 - (255 - 179) * t);
      const g = Math.round(255 - (255 - 38) * t);
      const b = Math.round(255 - (255 - 30) * t);
      return `rgb(${r},${g},${b})`;
    }
  },
  scoreBadge(score, max = 9) {
    if (score === null || score === undefined) return '<span class="score-badge score-mid">—</span>';
    const cls = score >= max * 0.7 ? 'score-good' : score >= max * 0.4 ? 'score-mid' : 'score-bad';
    return `<span class="score-badge ${cls}">${score}</span>`;
  },
  async loadJSON(path) {
    try {
      const r = await fetch(path, { cache: 'no-store' });
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return await r.json();
    } catch (e) {
      console.error('loadJSON failed', path, e);
      return null;
    }
  },
  qs(name) {
    return new URLSearchParams(location.search).get(name);
  },
};
