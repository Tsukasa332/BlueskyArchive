import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { getCalendar, getPosts, getReplyTimeline, getSidebarNavigation, getSyncStatus, getTagTimeline, getTimeline, requestSync } from './api';
import type { Post, Repost, SidebarNavigation, TimelineItem, TimelineOrder } from './api';
import { AnalyticsPage } from './AnalyticsPage';
import { ArchiveSidebar } from './ArchiveSidebar';
import { ConfigPage } from './ConfigPage';
import { TimelineCard } from './TimelineCard';
import {
  LATEST_PAGE_SIZE,
  PAGE_SIZE,
  dateTextFromSelection,
  formatDayLabel,
  localDateKey,
  monthGrid,
  parseRoute,
  routeUrl,
  scrollToTop,
  selectedLabel,
  shiftDate,
  shiftMonth,
} from './archive';
import type { DayItem, MonthItem, RouteState, Selection, YearItem } from './archive';
import { loadSettings, saveSettings } from './settings';
import type { AppSettings } from './settings';
import './styles.css';

function timelineItemTimes(item: TimelineItem) {
  const event = item.kind === 'post' ? item.post : item.repost;
  const createdAt = event.record_created_at ? new Date(event.record_created_at).getTime() : Number.NaN;
  const indexedAt = event.indexed_at ? new Date(event.indexed_at).getTime() : Number.NaN;
  return {
    createdAt: Number.isFinite(createdAt) ? createdAt : null,
    indexedAt: Number.isFinite(indexedAt) ? indexedAt : null,
    id: event.id,
  };
}

function compareTimelineItems(leftItem: TimelineItem, rightItem: TimelineItem, order: TimelineOrder) {
  const left = timelineItemTimes(leftItem);
  const right = timelineItemTimes(rightItem);
  if (left.createdAt === null || right.createdAt === null) {
    if (left.createdAt === null && right.createdAt !== null) return 1;
    if (left.createdAt !== null && right.createdAt === null) return -1;
  }
  if (order === 'day_asc' && left.createdAt !== null && right.createdAt !== null) {
    const leftDay = localDateKey(new Date(left.createdAt).toISOString());
    const rightDay = localDateKey(new Date(right.createdAt).toISOString());
    const dayComparison = rightDay.localeCompare(leftDay);
    if (dayComparison !== 0) return dayComparison;
  }
  if (left.createdAt !== right.createdAt) {
    const leftTime = left.createdAt ?? 0;
    const rightTime = right.createdAt ?? 0;
    return order === 'desc' ? rightTime - leftTime : leftTime - rightTime;
  }
  if (left.indexedAt !== right.indexedAt) {
    const leftIndexed = left.indexedAt ?? (order === 'desc' ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY);
    const rightIndexed = right.indexedAt ?? (order === 'desc' ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY);
    return order === 'desc' ? rightIndexed - leftIndexed : leftIndexed - rightIndexed;
  }
  const kindComparison = leftItem.kind.localeCompare(rightItem.kind);
  return kindComparison || left.id - right.id;
}

function App() {
  type View = 'archive' | 'analytics' | 'config';
  function viewFromLocation(): View {
    const params = new URLSearchParams(window.location.search);
    if (params.get('analytics') === '1') return 'analytics';
    if (params.get('config') === '1') return 'config';
    return 'archive';
  }
  const [view, setView] = useState<View>(() => viewFromLocation());
  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [years, setYears] = useState<YearItem[]>([]);
  const [archives, setArchives] = useState<MonthItem[]>([]);
  const [days, setDays] = useState<DayItem[]>([]);
  const [navigation, setNavigation] = useState<SidebarNavigation>({ friends: [], hashtags: [] });
  const [posts, setPosts] = useState<Post[]>([]);
  const [reposts, setReposts] = useState<Repost[]>([]);
  const [selected, setSelected] = useState<Selection>({});
  const [query, setQuery] = useState('');
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortOrder, setSortOrder] = useState<TimelineOrder>('desc');
  const [mediaOnly, setMediaOnly] = useState(false);
  const [linkOnly, setLinkOnly] = useState(false);
  const [showReposts, setShowReposts] = useState(true);
  const [showAllArchives, setShowAllArchives] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [page, setPage] = useState(1);
  const [timelineNowMs, setTimelineNowMs] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setTimelineNowMs(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  const settingsRef = useRef(settings);
  const sortOrderRef = useRef(sortOrder);
  const showDeleted = settings.showDeleted;
  const showRecordIds = settings.showRecordIds;

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  useEffect(() => {
    sortOrderRef.current = sortOrder;
  }, [sortOrder]);

  useEffect(() => {
    const previousScrollRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = 'manual';

    async function bootstrap() {
      setLoading(true);
      try {
        const [allMonths] = await Promise.all([reloadArchives(), reloadNavigation()]);
        await loadRoute(parseRoute(), false, allMonths, showDeleted);
      } catch (err) {
        setError(err instanceof Error ? err.message : '読み込みに失敗しました');
      } finally {
        setLoading(false);
      }
    }
    if (view === 'archive') {
      bootstrap();
    } else {
      setLoading(false);
    }

    function handlePopState() {
      const nextView = viewFromLocation();
      if (nextView !== 'archive') {
        setView(nextView);
        setLoading(false);
        scrollToTop();
        return;
      }
      setView('archive');
      scrollToTop(settingsRef.current.scrollToTopOnNavigation);
      setLoading(true);
      reloadArchives()
        .then((allMonths) => loadRoute(parseRoute(), false, allMonths, settingsRef.current.showDeleted, sortOrderRef.current))
        .catch((err) => setError(err instanceof Error ? err.message : '読み込みに失敗しました'))
        .finally(() => setLoading(false));
    }

    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
      window.history.scrollRestoration = previousScrollRestoration;
    };
  }, []);

  function updateRoute(route: RouteState, mode: 'push' | 'replace' = 'push') {
    const url = routeUrl(route);
    if (url === `${window.location.pathname}${window.location.search}`) return;
    if (mode === 'replace') {
      window.history.replaceState(route, '', url);
    } else {
      window.history.pushState(route, '', url);
    }
    scrollToTop(settings.scrollToTopOnNavigation);
  }

  function openSecondary(nextView: Exclude<View, 'archive'>) {
    const archiveUrl = `${window.location.pathname}${window.location.search}`;
    window.history.pushState(
      { view: nextView, archiveUrl },
      '',
      nextView === 'config' ? '/?config=1' : '/?analytics=1',
    );
    setView(nextView);
    scrollToTop();
  }

  function closeSecondary() {
    if (typeof window.history.state?.archiveUrl === 'string') {
      window.history.back();
    } else {
      window.location.assign('/');
    }
  }

  function changeSettings(next: AppSettings) {
    settingsRef.current = next;
    setSettings(next);
    saveSettings(next);
  }

  function activeRoute(pageNumber: number): RouteState {
    const route = parseRoute();
    return { ...route, page: pageNumber };
  }

  async function reloadArchives() {
    const rootCalendar = await getCalendar();
    const yearItems = [...(rootCalendar.years || [])].sort((a, b) => b.year - a.year);
    setYears(yearItems);

    const monthGroups = await Promise.all(yearItems.map((item) => getCalendar(item.year)));
    const allMonths = monthGroups
      .flatMap((group) => group.months || [])
      .sort((a, b) => b.year - a.year || b.month - a.month);
    setArchives(allMonths);
    return allMonths;
  }

  async function reloadNavigation() {
    const data = await getSidebarNavigation();
    setNavigation(data);
    return data;
  }

  async function loadRoute(route: RouteState, updateUrl = true, knownArchives = archives, includeDeleted = showDeleted, order = sortOrder) {
    if (updateUrl) updateRoute(route);
    if (route.kind === 'friend') {
      setQuery('');
      await runFriendSearch(route.did, false, includeDeleted, route.page || 1, order);
      return;
    }
    if (route.kind === 'tag') {
      setQuery(`#${route.tag}`);
      await runTagSearch(route.tag, false, includeDeleted, route.page || 1, order);
      return;
    }
    if (route.kind === 'search') {
      setQuery(route.q);
      await runSearch(route.q, false, includeDeleted, route.page || 1, order);
      return;
    }
    setQuery('');
    if (route.kind === 'day') {
      await chooseDay(`${route.year}-${String(route.month).padStart(2, '0')}-${String(route.day).padStart(2, '0')}`, false, includeDeleted, route.page || 1, order);
      return;
    }
    if (route.kind === 'month') {
      await chooseMonth(route.year, route.month, false, false, includeDeleted, route.page || 1, order);
      return;
    }
    const latestMonth = knownArchives[0];
    const pageNumber = route.page || 1;
    setSelected({});
    setPage(pageNumber);
    const [calendar, timeline] = await Promise.all([
      latestMonth ? getCalendar(latestMonth.year, latestMonth.month) : Promise.resolve({ days: [] }),
      getTimeline({
        limit: LATEST_PAGE_SIZE,
        offset: (pageNumber - 1) * LATEST_PAGE_SIZE,
        includeDeleted,
        order,
      }),
    ]);
    setDays([...(calendar.days || [])].sort((a, b) => b.date.localeCompare(a.date)));
    applyTimeline(timeline.items);
    setTotal(timeline.total);
  }

  function applyTimeline(items: TimelineItem[]) {
    setPosts(items.filter((item): item is Extract<TimelineItem, { kind: 'post' }> => item.kind === 'post').map((item) => item.post));
    setReposts(items.filter((item): item is Extract<TimelineItem, { kind: 'repost' }> => item.kind === 'repost').map((item) => item.repost));
  }

  async function chooseMonth(year: number, month: number, openLatestDay = false, updateUrl = true, includeDeleted = showDeleted, pageNumber = 1, order = sortOrder) {
    setError(null);
    if (updateUrl) setQuery('');
    setSelected({ year, month });
    setPage(pageNumber);
    const data = await getCalendar(year, month);
    const monthDays = [...(data.days || [])].sort((a, b) => b.date.localeCompare(a.date));
    setDays(monthDays);
    if (openLatestDay && monthDays[0]) {
      await chooseDay(monthDays[0].date, updateUrl, includeDeleted, 1, order);
    } else {
      if (updateUrl) updateRoute({ kind: 'month', year, month, page: pageNumber });
      const data = await getTimeline({ year, month, limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE, includeDeleted, order });
      applyTimeline(data.items);
      setTotal(data.total);
    }
  }

  async function chooseDay(dateText: string, updateUrl = true, includeDeleted = showDeleted, pageNumber = 1, order = sortOrder) {
    setError(null);
    const [year, month, day] = dateText.split('-').map(Number);
    if (updateUrl) updateRoute({ kind: 'day', year, month, day, page: pageNumber });
    if (updateUrl) setQuery('');
    setSelected({ year, month, day });
    setPage(pageNumber);
    const data = await getTimeline({ year, month, day, limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE, includeDeleted, order });
    applyTimeline(data.items);
    setTotal(data.total);
  }

  async function runSearch(text: string, updateUrl = true, includeDeleted = showDeleted, pageNumber = 1, order = sortOrder) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setError(null);
    if (updateUrl) updateRoute({ kind: 'search', q: trimmed, page: pageNumber });
    setSelected({});
    setPage(pageNumber);
    const data = await getPosts({ q: trimmed, limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE, includeDeleted, order });
    setPosts(data.items);
    setReposts([]);
    setTotal(data.total);
  }

  async function runTagSearch(tag: string, updateUrl = true, includeDeleted = showDeleted, pageNumber = 1, order = sortOrder) {
    const normalized = tag.trim().replace(/^#/, '');
    if (!normalized) return;
    setError(null);
    if (updateUrl) updateRoute({ kind: 'tag', tag: normalized, page: pageNumber });
    setQuery(`#${normalized}`);
    setSelected({});
    setPage(pageNumber);
    const data = await getTagTimeline(normalized, { limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE, includeDeleted, order });
    applyTimeline(data.items);
    setTotal(data.total);
  }

  async function runFriendSearch(did: string, updateUrl = true, includeDeleted = showDeleted, pageNumber = 1, order = sortOrder) {
    const normalized = did.trim();
    if (!normalized) return;
    setError(null);
    if (updateUrl) updateRoute({ kind: 'friend', did: normalized, page: pageNumber });
    setQuery('');
    setSelected({});
    setPage(pageNumber);
    const data = await getReplyTimeline(normalized, { limit: PAGE_SIZE, offset: (pageNumber - 1) * PAGE_SIZE, includeDeleted, order });
    applyTimeline(data.items);
    setTotal(data.total);
  }

  async function openTag(tag: string) {
    setLoading(true);
    try {
      await runTagSearch(tag);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'tag search failed');
    } finally {
      setLoading(false);
    }
  }

  async function openFriend(did: string) {
    setLoading(true);
    try {
      await runFriendSearch(did);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'reply search failed');
    } finally {
      setLoading(false);
    }
  }

  async function search(event: React.FormEvent) {
    event.preventDefault();
    if (query.trim().startsWith('#')) await runTagSearch(query);
    else await runSearch(query);
  }

  async function changeSortOrder(next: TimelineOrder) {
    if (next === sortOrder) return;
    sortOrderRef.current = next;
    setSortOrder(next);
    setLoading(true);
    try {
      await loadRoute(activeRoute(1), true, archives, showDeleted, next);
    } finally {
      setLoading(false);
    }
  }

  async function goToPage(pageNumber: number) {
    const next = Math.max(1, pageNumber);
    setLoading(true);
    try {
      await loadRoute(activeRoute(next), true, archives, showDeleted);
    } finally {
      setLoading(false);
    }
  }

  async function refreshCurrent() {
    setLoading(true);
    setSyncing(true);
    setError(null);
    try {
      const request = await requestSync();
      let completed = false;
      for (let attempt = 0; attempt < 360; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, attempt === 0 ? 2000 : 5000));
        const status = await getSyncStatus();
        const latestRun = status.latest_run;
        if (latestRun?.status === 'error' && latestRun.started_at && new Date(latestRun.started_at).getTime() >= new Date(request.requested_at).getTime()) {
          throw new Error(latestRun.error_message || '同期に失敗しました');
        }
        const consumed = status.consumed_at === request.requested_at;
        if (consumed && latestRun?.status !== 'running') {
          if (latestRun?.status === 'error') throw new Error(latestRun.error_message || '同期に失敗しました');
          completed = true;
          break;
        }
      }
      if (!completed) throw new Error('同期が30分以内に完了しませんでした。Fetcherのログを確認してください');
      const [allMonths] = await Promise.all([reloadArchives(), reloadNavigation()]);
      await loadRoute(parseRoute(), false, allMonths, showDeleted);
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新に失敗しました');
    } finally {
      setSyncing(false);
      setLoading(false);
    }
  }

  const visibleItems = useMemo(() => {
    const items: TimelineItem[] = [
      ...posts.map((post) => ({ kind: 'post' as const, post })),
      ...(showReposts ? reposts.map((repost) => ({ kind: 'repost' as const, repost })) : []),
    ];
    return items
      .filter((item) => showDeleted || (item.kind === 'post' ? !item.post.deleted : !item.repost.deleted))
      .filter((item) => item.kind === 'post' || (!mediaOnly && !linkOnly))
      .filter((item) => item.kind !== 'post' || !mediaOnly || item.post.media.length > 0)
      .filter((item) => item.kind !== 'post' || !linkOnly || /https?:\/\//.test(item.post.text) || (item.post.external_links?.length || 0) > 0)
      .sort((a, b) => compareTimelineItems(a, b, sortOrder));
  }, [posts, reposts, showReposts, sortOrder, mediaOnly, linkOnly]);

  const groupedPosts = useMemo(() => {
    const groups = new Map<string, TimelineItem[]>();
    for (const item of visibleItems) {
      const value = item.kind === 'post' ? item.post.record_created_at : item.repost.record_created_at;
      const key = localDateKey(value);
      groups.set(key, [...(groups.get(key) || []), item]);
    }
    return Array.from(groups.entries());
  }, [visibleItems]);

  const selectedMonth = selected.year && selected.month ? { year: selected.year, month: selected.month } : archives[0];
  const grid = monthGrid(selectedMonth?.year, selectedMonth?.month, days);
  const recentDays = days.slice(0, 10);
  const itemCount = years.reduce((sum, item) => sum + item.count, 0);
  const currentDateText = dateTextFromSelection(selected);
  const currentRoute = parseRoute();
  const currentFriend = currentRoute.kind === 'friend'
    ? navigation.friends.find((item) => item.actor.did === currentRoute.did)
    : undefined;
  const currentFriendName = currentRoute.kind === 'friend'
    ? currentFriend?.actor.display_name || currentFriend?.actor.handle || currentRoute.did
    : '';
  const currentLabel = currentRoute.kind === 'friend'
    ? `${currentFriendName} へのリプライ`
    : currentRoute.kind === 'tag'
      ? `#${currentRoute.tag} の検索結果`
      : currentRoute.kind === 'search'
        ? `「${currentRoute.q}」の検索結果`
        : selectedLabel(selected);
  const currentPageSize = currentRoute.kind === 'latest' ? LATEST_PAGE_SIZE : PAGE_SIZE;
  const totalPages = Math.max(1, Math.ceil(total / currentPageSize));
  const prevMonth = selected.year && selected.month ? shiftMonth(selected.year, selected.month, -1) : null;
  const nextMonth = selected.year && selected.month ? shiftMonth(selected.year, selected.month, 1) : null;
  const archiveItems = showAllArchives ? archives : archives.slice(0, 18);

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="/">
          BlueskyArchive
        </a>
        {view !== 'archive' ? (
          <button className="back-button" onClick={closeSecondary}>アーカイブに戻る</button>
        ) : (
          <div className="top-actions">
            <button className="analytics-button" onClick={() => openSecondary('analytics')} aria-label="分析を開く">分析</button>
            <button className="settings-button" onClick={() => openSecondary('config')} aria-label="設定を開く">設定</button>
            <form className="top-search" onSubmit={search}>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="投稿を検索" />
              <button>検索</button>
            </form>
            <button className="refresh-button" onClick={refreshCurrent} disabled={loading || syncing}>{syncing ? '同期中' : '更新'}</button>
          </div>
        )}
      </header>

      {view === 'config' ? (
        <ConfigPage settings={settings} onChange={changeSettings} />
      ) : view === 'analytics' ? (
        <AnalyticsPage />
      ) : (
        <section className="shell">
        <section className="content">
          <section className="profile">
            <div>
              <div className="avatar">B</div>
              <h1>Personal BlueskyArchive</h1>
              <p>ローカルに保存した自分用Blueskyログ</p>
            </div>
            <div className="stats">
              <span><strong>{itemCount.toLocaleString()}</strong> items</span>
              <span><strong>{archives.length.toLocaleString()}</strong> months</span>
              <span><strong>{years.length.toLocaleString()}</strong> years</span>
            </div>
          </section>

          <nav className="filters" aria-label="投稿の表示設定">
            <div className="filter-row">
              <span className="filter-label">ポストの並び順：</span>
              <div className="filter-options">
                <button className={sortOrder === 'desc' ? 'active' : ''} onClick={() => changeSortOrder('desc')}>通常</button>
                <button className={sortOrder === 'day_asc' ? 'active' : ''} onClick={() => changeSortOrder('day_asc')}>朝→夜</button>
                <button className={sortOrder === 'asc' ? 'active' : ''} onClick={() => changeSortOrder('asc')}>古→新</button>
              </div>
            </div>
            <div className="filter-row">
              <span className="filter-label">表示するポスト：</span>
              <div className="filter-options">
                <button className={mediaOnly ? 'active' : ''} onClick={() => setMediaOnly((value) => !value)}>画像あり</button>
                <button className={linkOnly ? 'active' : ''} onClick={() => setLinkOnly((value) => !value)}>リンクあり</button>
                <button className={showReposts ? 'active' : ''} onClick={() => setShowReposts((value) => !value)}>リポスト</button>
              </div>
            </div>
          </nav>

          <section className="timeline">
            <div className="summary">
              <strong>{currentLabel}</strong>
              <span>{loading ? '読み込み中' : `${visibleItems.length.toLocaleString()} / ${total.toLocaleString()} items`}</span>
            </div>
            <div className="pager">
              {!currentDateText && selected.year && selected.month && prevMonth && nextMonth ? (
                <>
                  <button onClick={() => chooseMonth(prevMonth.year, prevMonth.month)}>前の月</button>
                  <button onClick={() => chooseMonth(nextMonth.year, nextMonth.month)}>次の月</button>
                </>
              ) : null}
            </div>
            {error && <div className="notice">{error}</div>}
            {!loading && visibleItems.length === 0 && <div className="empty">投稿がありません。</div>}
            {groupedPosts.map(([dateText, items]) => (
              <section className="day-group" key={dateText}>
                <h2>
                  {dateText !== '日付なし' && !selected.day ? (
                    <button className="day-heading-link" onClick={() => chooseDay(dateText)}>
                      {formatDayLabel(dateText)}
                    </button>
                  ) : (
                    dateText === '日付なし' ? dateText : formatDayLabel(dateText)
                  )}
                  <span>{items.length} items</span>
                </h2>
                {items.map((item) => (
                  <TimelineCard
                    key={item.kind === 'post' ? `post-${item.post.id}` : `repost-${item.repost.id}`}
                    item={item}
                    showRecordIds={showRecordIds}
                    linkActorNames={settings.linkActorNames}
                    blurSensitiveMedia={settings.blurSensitiveMedia}
                    nowMs={timelineNowMs}
                    onHashtag={(tag) => void openTag(tag)}
                  />
                ))}
              </section>
            ))}
            {currentDateText && (
              <div className="pager pager-bottom">
                <button onClick={() => chooseDay(shiftDate(currentDateText, -1))}>前の日</button>
                <button onClick={() => chooseDay(shiftDate(currentDateText, 1))}>次の日</button>
              </div>
            )}
            {totalPages > 1 && (
              <div className="pager page-pager">
                <button disabled={page <= 1} onClick={() => goToPage(page - 1)}>前のページ</button>
                <span>{page} / {totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => goToPage(page + 1)}>次のページ</button>
              </div>
            )}
          </section>
        </section>

        <ArchiveSidebar
          selected={selected}
          selectedMonth={selectedMonth}
          grid={grid}
          recentDays={recentDays}
          archives={archiveItems}
          friends={navigation.friends}
          hashtags={navigation.hashtags}
          selectedFriendDid={currentRoute.kind === 'friend' ? currentRoute.did : undefined}
          selectedTag={currentRoute.kind === 'tag' ? currentRoute.tag : undefined}
          showRecent={settings.showRecent}
          showArchives={settings.showArchives}
          showFriends={settings.showFriends}
          showHashtags={settings.showHashtags}
          showSelfInFriends={settings.showSelfInFriends}
          showAllArchives={showAllArchives}
          hasMoreArchives={archives.length > 18}
          onChooseDay={(dateText) => void chooseDay(dateText)}
          onChooseMonth={(year, month) => void chooseMonth(year, month)}
          onChooseFriend={(did) => void openFriend(did)}
          onChooseHashtag={(tag) => void openTag(tag)}
          onToggleAllArchives={() => setShowAllArchives((value) => !value)}
        />
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
