import { useEffect, useMemo, useState } from 'react';
import { getAnalytics } from './api';
import type { AnalyticsPeriod, AnalyticsResponse } from './api';
import type { Language } from './i18n';

const PERIOD_LABELS: Record<Language, Record<AnalyticsPeriod, string>> = {
  en: { all: 'All time', year: 'Past year', month: 'Past month', week: 'Past week' },
  ja: { all: '全期間', year: '直近1年', month: '直近1ヶ月', week: '直近1週間' },
};

const DAYS: Record<Language, string[]> = {
  en: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  ja: ['月', '火', '水', '木', '金', '土', '日'],
};

function percentage(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0;
}

export function AnalyticsPage({ language }: { language: Language }) {
  const [period, setPeriod] = useState<AnalyticsPeriod>('all');
  const [binSize, setBinSize] = useState<3 | 6>(6);
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setData(null);
    getAnalytics(period)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : language === 'ja' ? '分析データの読み込みに失敗しました' : 'Failed to load analytics data');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [period, language]);

  const buckets = useMemo(() => {
    const hourly = Array.from({ length: 7 }, () => Array(24).fill(0) as number[]);
    for (const cell of data?.heatmap || []) {
      hourly[cell.weekday - 1][cell.hour] = cell.count;
    }
    const rows = [];
    for (let start = 0; start < 24; start += binSize) {
      rows.push({
        start,
        values: hourly.map((day) => (
          day.slice(start, start + binSize).reduce((sum, value) => sum + value, 0)
        )),
      });
    }
    return rows;
  }, [data, binSize]);

  const maxHeatmapCount = Math.max(0, ...buckets.flatMap((bucket) => bucket.values));
  const counts = data?.counts || { own_posts: 0, replies: 0, reposts: 0, total: 0 };
  const categories = [
    { key: 'own', label: language === 'ja' ? '自分のポスト' : 'Own posts', count: counts.own_posts, className: 'analytics-own' },
    { key: 'reply', label: language === 'ja' ? '他人へのリプライ' : 'Replies to others', count: counts.replies, className: 'analytics-reply' },
    { key: 'repost', label: language === 'ja' ? 'リポスト' : 'Reposts', count: counts.reposts, className: 'analytics-repost' },
  ];

  return (
    <section className="analytics-page" aria-labelledby="analytics-title">
      <div className="analytics-heading">
        <div>
          <h1 id="analytics-title">{language === 'ja' ? '分析' : 'Analytics'}</h1>
          <p>{language === 'ja' ? '保存済みの投稿・リプライ・リポストを、投稿日時を基準に集計します。' : 'Summarizes archived posts, replies, and reposts by their posting time.'}</p>
        </div>
        <div className="analytics-periods" aria-label={language === 'ja' ? '集計期間' : 'Analytics period'}>
          {(['all', 'year', 'month', 'week'] as AnalyticsPeriod[]).map((value) => (
            <button
              key={value}
              className={period === value ? 'active' : ''}
              aria-pressed={period === value}
              onClick={() => setPeriod(value)}
            >
              {PERIOD_LABELS[language][value]}
            </button>
          ))}
        </div>
      </div>

      {error && <div className="notice">{error}</div>}

      <section className="analytics-section" aria-labelledby="post-type-title">
        <div className="analytics-section-heading">
          <h2 id="post-type-title">{language === 'ja' ? '投稿の内訳' : 'Post breakdown'}</h2>
          <span>{loading ? (language === 'ja' ? '読み込み中' : 'Loading') : `${counts.total.toLocaleString()} items`}</span>
        </div>
        <div
          className="analytics-share-bar"
          role="img"
          aria-label={categories.map((item) => (
            language === 'ja'
              ? `${item.label}${percentage(item.count, counts.total)}パーセント`
              : `${item.label}: ${percentage(item.count, counts.total)} percent`
          )).join(language === 'ja' ? '、' : ', ')}
        >
          {categories.map((item) => (
            <div
              key={item.key}
              className={`analytics-share-segment ${item.className}`}
              style={{ width: `${counts.total > 0 ? (item.count / counts.total) * 100 : 0}%` }}
            >
              {percentage(item.count, counts.total) >= 8
                ? `${percentage(item.count, counts.total)}%`
                : null}
            </div>
          ))}
        </div>
        <div className="analytics-share-details">
          {categories.map((item) => (
            <div className="analytics-share-detail" key={item.key}>
              <span className="analytics-share-label">
                <span className={`analytics-swatch ${item.className}`} aria-hidden="true" />
                {item.label}
              </span>
              <strong>{item.count.toLocaleString()}</strong>
              <span>{percentage(item.count, counts.total)}%</span>
            </div>
          ))}
        </div>
      </section>

      <section className="analytics-section" aria-labelledby="heatmap-title">
        <div className="analytics-section-heading heatmap-heading">
          <h2 id="heatmap-title">{language === 'ja' ? '曜日・時間帯' : 'Day and time'}</h2>
          <div className="heatmap-bin-controls" aria-label={language === 'ja' ? '時間帯の区切り' : 'Time interval'}>
            <label>
              <input
                type="radio"
                name="analytics-bin"
                checked={binSize === 6}
                onChange={() => setBinSize(6)}
              />
              {language === 'ja' ? '6時間ごと' : '6-hour intervals'}
            </label>
            <label>
              <input
                type="radio"
                name="analytics-bin"
                checked={binSize === 3}
                onChange={() => setBinSize(3)}
              />
              {language === 'ja' ? '3時間ごと' : '3-hour intervals'}
            </label>
          </div>
        </div>
        <div className="analytics-heatmap-wrap">
          <div className="analytics-heatmap" role="grid" aria-label={language === 'ja' ? '曜日と投稿時間帯のヒートマップ' : 'Posts by day and time heatmap'}>
            <span aria-hidden="true" />
            {DAYS[language].map((day) => <strong className="heatmap-day" key={day}>{day}</strong>)}
            {buckets.map((bucket) => (
              <div className="heatmap-row" key={bucket.start}>
                <span className="heatmap-time">
                  {bucket.start}–{bucket.start + binSize}
                </span>
                {bucket.values.map((value, dayIndex) => {
                  const level = value === 0 || maxHeatmapCount === 0
                    ? 0
                    : Math.max(1, Math.min(4, Math.ceil((value / maxHeatmapCount) * 4)));
                  return (
                    <span
                      className={`heatmap-cell heatmap-level-${level}`}
                      role="gridcell"
                      aria-label={language === 'ja'
                        ? `${DAYS.ja[dayIndex]}曜日 ${bucket.start}時から${bucket.start + binSize}時、${value}件`
                        : `${DAYS.en[dayIndex]}, ${bucket.start}:00 to ${bucket.start + binSize}:00, ${value} items`}
                      key={DAYS[language][dayIndex]}
                    >
                      {value}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <div className="heatmap-legend" aria-label={language === 'ja' ? '投稿数の凡例' : 'Post count legend'}>
          <span>{language === 'ja' ? '少ない' : 'Fewer'}</span>
          {[0, 1, 2, 3, 4].map((level) => (
            <span className={`heatmap-legend-cell heatmap-level-${level}`} key={level} />
          ))}
          <span>{language === 'ja' ? '多い' : 'More'}</span>
        </div>
      </section>
    </section>
  );
}
