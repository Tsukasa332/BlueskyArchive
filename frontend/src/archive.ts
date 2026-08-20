import type { Actor } from './api';
import { localeFor } from './i18n';
import type { Language } from './i18n';

export type YearItem = { year: number; count: number };
export type MonthItem = { year: number; month: number; count: number };
export type DayItem = { date: string; count: number };
export type Selection = { year?: number; month?: number; day?: number };
export type RouteState =
  | { kind: 'latest'; page?: number }
  | { kind: 'month'; year: number; month: number; page?: number }
  | { kind: 'day'; year: number; month: number; day: number; page?: number }
  | { kind: 'search'; q: string; page?: number }
  | { kind: 'tag'; tag: string; page?: number }
  | { kind: 'friend'; did: string; page?: number };

export const UNDATED_KEY = '__undated__';
export const WEEKDAYS: Record<Language, string[]> = {
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  ja: ['日', '月', '火', '水', '木', '金', '土'],
};
export const PAGE_SIZE = 300;
export const LATEST_PAGE_SIZE = 50;

export function formatDateTime(value?: string | null, language: Language = 'en') {
  if (!value) return '';
  return new Intl.DateTimeFormat(localeFor(language), {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  }).format(new Date(value));
}

export function formatPostAge(value?: string | null, nowMs = Date.now(), language: Language = 'en') {
  if (!value) return '';
  const postedAt = new Date(value);
  const postedAtMs = postedAt.getTime();
  if (!Number.isFinite(postedAtMs)) return '';

  const elapsedMinutes = Math.max(0, Math.floor((nowMs - postedAtMs) / 60_000));
  if (elapsedMinutes < 60) return language === 'ja' ? `${elapsedMinutes}分前` : `${elapsedMinutes}m ago`;
  if (elapsedMinutes < 24 * 60) {
    const hours = Math.floor(elapsedMinutes / 60);
    return language === 'ja' ? `${hours}時間前` : `${hours}h ago`;
  }
  return new Intl.DateTimeFormat(localeFor(language), {
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Tokyo',
  }).format(postedAt);
}

export function localDateKey(value?: string | null) {
  if (!value) return UNDATED_KEY;
  const parts = new Intl.DateTimeFormat('sv-SE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    timeZone: 'Asia/Tokyo',
  }).formatToParts(new Date(value));
  const byType = new Map(parts.map((part) => [part.type, part.value]));
  return `${byType.get('year')}-${byType.get('month')}-${byType.get('day')}`;
}

export function formatDayLabel(dateText: string, language: Language = 'en', includeYear = true) {
  const date = new Date(dateText + 'T00:00:00+09:00');
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  if (language === 'ja') {
    return `${includeYear ? `${year}年` : ''}${month}月${day}日(${WEEKDAYS.ja[date.getDay()]})`;
  }
  return new Intl.DateTimeFormat('en-US', {
    ...(includeYear ? { year: 'numeric' as const } : {}),
    month: 'short',
    day: '2-digit',
    weekday: 'short',
    timeZone: 'Asia/Tokyo',
  }).format(date);
}

export function formatMonthLabel(year: number, month: number, language: Language = 'en') {
  return language === 'ja'
    ? `${year}年${String(month).padStart(2, '0')}月`
    : new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', timeZone: 'Asia/Tokyo' })
      .format(new Date(`${year}-${String(month).padStart(2, '0')}-01T00:00:00+09:00`));
}

export function selectedLabel(selected: Selection, language: Language = 'en') {
  if (selected.year && selected.month && selected.day) {
    return formatDayLabel(`${selected.year}-${String(selected.month).padStart(2, '0')}-${String(selected.day).padStart(2, '0')}`, language);
  }
  if (selected.year && selected.month) return formatMonthLabel(selected.year, selected.month, language);
  if (selected.year) return language === 'ja' ? `${selected.year}年` : String(selected.year);
  return language === 'ja' ? '最新の投稿' : 'Latest posts';
}

export function uriTail(uri: string) {
  return uri.split('/').slice(-1)[0] || uri;
}

export function blueskyPostUrl(uri: string) {
  const did = uri.startsWith('at://') ? uri.split('/')[2] : '';
  const rkey = uriTail(uri);
  return did && rkey ? `https://bsky.app/profile/${did}/post/${rkey}` : undefined;
}

export function safeHttpUrl(value?: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value, window.location.origin);
    if (url.protocol === 'http:' || url.protocol === 'https:') return url.href;
  } catch {
    return undefined;
  }
  return undefined;
}

export function safeMediaUrl(value?: string | null) {
  const url = safeHttpUrl(value);
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    if (parsed.origin === window.location.origin || parsed.hostname === 'cdn.bsky.app') return url;
  } catch {
    return undefined;
  }
  return undefined;
}

export function actorName(actor?: Actor | null) {
  if (!actor) return null;
  return actor.handle || actor.display_name || actor.did;
}

export function dateTextFromSelection(selected: Selection) {
  if (!selected.year || !selected.month || !selected.day) return null;
  return `${selected.year}-${String(selected.month).padStart(2, '0')}-${String(selected.day).padStart(2, '0')}`;
}

export function shiftDate(dateText: string, amount: number) {
  const date = new Date(dateText + 'T00:00:00+09:00');
  date.setDate(date.getDate() + amount);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function shiftMonth(year: number, month: number, amount: number) {
  const date = new Date(year, month - 1 + amount, 1);
  return { year: date.getFullYear(), month: date.getMonth() + 1 };
}

export function sameSelection(a: Selection, b: Selection) {
  return a.year === b.year && a.month === b.month && a.day === b.day;
}

export function monthGrid(year?: number, month?: number, days: DayItem[] = []) {
  if (!year || !month) return [];
  const first = new Date(year, month - 1, 1);
  const last = new Date(year, month, 0);
  const countByDay = new Map(days.map((item) => [Number(item.date.slice(8, 10)), item.count]));
  const cells: ({ day: number; count: number } | null)[] = [];
  for (let i = 0; i < first.getDay(); i += 1) cells.push(null);
  for (let day = 1; day <= last.getDate(); day += 1) {
    cells.push({ day, count: countByDay.get(day) || 0 });
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export function parseRoute(search = window.location.search): RouteState {
  const params = new URLSearchParams(search);
  const replyTo = params.get('reply_to')?.trim();
  const tag = params.get('tag')?.trim().replace(/^#/, '');
  const q = params.get('q')?.trim();
  const year = Number(params.get('year'));
  const month = Number(params.get('month'));
  const day = Number(params.get('day'));
  const page = Math.max(1, Number(params.get('page')) || 1);
  if (replyTo) return { kind: 'friend', did: replyTo, page };
  if (tag) return { kind: 'tag', tag, page };
  if (q) return { kind: 'search', q, page };
  if (year && month && day) return { kind: 'day', year, month, day, page };
  if (year && month) return { kind: 'month', year, month, page };
  return { kind: 'latest', page };
}

export function routeUrl(route: RouteState) {
  const params = new URLSearchParams();
  if (route.kind === 'search') params.set('q', route.q);
  if (route.kind === 'tag') params.set('tag', route.tag);
  if (route.kind === 'friend') params.set('reply_to', route.did);
  if (route.kind === 'month' || route.kind === 'day') {
    params.set('year', String(route.year));
    params.set('month', String(route.month));
  }
  if (route.kind === 'day') params.set('day', String(route.day));
  if ((route.page || 1) > 1) params.set('page', String(route.page));
  const query = params.toString();
  return query ? `/?${query}` : '/';
}

export function scrollToTop(enabled = true) {
  if (enabled) window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
}
