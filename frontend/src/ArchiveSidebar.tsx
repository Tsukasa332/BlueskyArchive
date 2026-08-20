import type { FriendSummary, HashtagSummary } from './api';
import type { DayItem, MonthItem, Selection } from './archive';
import { formatDayLabel, sameSelection, WEEKDAYS } from './archive';

type ArchiveSidebarProps = {
  selected: Selection;
  selectedMonth?: { year: number; month: number };
  grid: ({ day: number; count: number } | null)[];
  recentDays: DayItem[];
  archives: MonthItem[];
  friends: FriendSummary[];
  hashtags: HashtagSummary[];
  selectedFriendDid?: string;
  selectedTag?: string;
  showRecent: boolean;
  showArchives: boolean;
  showFriends: boolean;
  showHashtags: boolean;
  showSelfInFriends: boolean;
  showAllArchives: boolean;
  hasMoreArchives: boolean;
  onChooseDay: (dateText: string) => void;
  onChooseMonth: (year: number, month: number) => void;
  onChooseFriend: (did: string) => void;
  onChooseHashtag: (tag: string) => void;
  onToggleAllArchives: () => void;
};

export function ArchiveSidebar(props: ArchiveSidebarProps) {
  const {
    selected,
    selectedMonth,
    grid,
    recentDays,
    archives,
    friends,
    hashtags,
    selectedFriendDid,
    selectedTag,
    showRecent,
    showArchives,
    showFriends,
    showHashtags,
    showSelfInFriends,
    showAllArchives,
    hasMoreArchives,
    onChooseDay,
    onChooseMonth,
    onChooseFriend,
    onChooseHashtag,
    onToggleAllArchives,
  } = props;
  return (
    <aside className="sidebar">
      <section className="panel calendar-panel">
        <div className="panel-title">
          <button disabled={!selectedMonth} onClick={() => selectedMonth && onChooseMonth(selectedMonth.month === 1 ? selectedMonth.year - 1 : selectedMonth.year, selectedMonth.month === 1 ? 12 : selectedMonth.month - 1)}>‹</button>
          {selectedMonth ? (
            <button className="calendar-month-link" onClick={() => onChooseMonth(selectedMonth.year, selectedMonth.month)}>
              {selectedMonth.year}年{String(selectedMonth.month).padStart(2, '0')}月
            </button>
          ) : <strong>Calendar</strong>}
          <button disabled={!selectedMonth} onClick={() => selectedMonth && onChooseMonth(selectedMonth.month === 12 ? selectedMonth.year + 1 : selectedMonth.year, selectedMonth.month === 12 ? 1 : selectedMonth.month + 1)}>›</button>
        </div>
        <div className="weekdays">{WEEKDAYS.map((item) => <span key={item}>{item}</span>)}</div>
        <div className="calendar-grid">
          {grid.map((cell, index) => cell ? (
            <button
              key={index}
              className={sameSelection(selected, { year: selectedMonth?.year, month: selectedMonth?.month, day: cell.day }) ? 'selected' : ''}
              disabled={!cell.count}
              onClick={() => selectedMonth && onChooseDay(`${selectedMonth.year}-${String(selectedMonth.month).padStart(2, '0')}-${String(cell.day).padStart(2, '0')}`)}
            >
              {cell.day}<small>{cell.count || ''}</small>
            </button>
          ) : <span key={index} />)}
        </div>
      </section>

      {showRecent && <section className="panel">
        <h2>Recent</h2>
        {recentDays.map((item) => (
          <button className="row-link" key={item.date} onClick={() => onChooseDay(item.date)}>
            <span>{formatDayLabel(item.date).replace(/^\d{4}年/, '')}</span>
            <strong>{item.count}</strong>
          </button>
        ))}
      </section>}

      {showFriends && <section className="panel">
        <h2>Friends</h2>
        {friends.filter((item) => showSelfInFriends || !item.is_self).map(({ actor, count }) => {
          const name = actor.display_name || (actor.handle ? `@${actor.handle}` : actor.did);
          const handle = actor.display_name && actor.handle ? `@${actor.handle}` : undefined;
          return (
            <button
              className={selectedFriendDid === actor.did ? 'row-link selected' : 'row-link'}
              key={actor.did}
              onClick={() => onChooseFriend(actor.did)}
            >
              <span className="sidebar-entity"><span>{name}</span>{handle && <small>{handle}</small>}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </section>}

      {showHashtags && <section className="panel">
        <h2>Hashtags</h2>
        {hashtags.map((item) => (
          <button
            className={selectedTag?.toLowerCase() === item.tag.toLowerCase() ? 'row-link selected' : 'row-link'}
            key={item.tag}
            onClick={() => onChooseHashtag(item.tag)}
          >
            <span>#{item.tag}</span>
            <strong>{item.count}</strong>
          </button>
        ))}
      </section>}

      {showArchives && <section className="panel">
        <h2>Archives</h2>
        {archives.map((item) => (
          <button className="row-link" key={`${item.year}-${item.month}`} onClick={() => onChooseMonth(item.year, item.month)}>
            <span>{item.year}年{String(item.month).padStart(2, '0')}月</span>
            <strong>{item.count}</strong>
          </button>
        ))}
        {hasMoreArchives && (
          <button className="row-link more-link" onClick={onToggleAllArchives}>
            <span>{showAllArchives ? '折りたたむ' : '全て表示 »'}</span>
          </button>
        )}
      </section>}
    </aside>
  );
}
