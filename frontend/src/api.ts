export type Calendar = {
  years?: { year: number; count: number }[];
  months?: { year: number; month: number; count: number }[];
  days?: { date: string; count: number }[];
};

export type Post = {
  id: number;
  uri: string;
  cid?: string | null;
  text: string;
  record_created_at?: string | null;
  indexed_at?: string | null;
  reply_root_uri?: string | null;
  reply_parent_uri?: string | null;
  quote_uri?: string | null;
  deleted: boolean;
  author: Actor;
  reply_root_author?: Actor | null;
  reply_parent_author?: Actor | null;
  quote_author?: Actor | null;
  media: Media[];
  external_links: ExternalLink[];
  hashtags: HashtagFacet[];
  labels: string[];
  embedded_records: EmbeddedRecord[];
};

export type Repost = {
  id: number;
  uri: string;
  cid?: string | null;
  subject_uri: string;
  subject_cid?: string | null;
  record_created_at?: string | null;
  indexed_at?: string | null;
  deleted: boolean;
  actor?: Actor | null;
  subject_author?: Actor | null;
  subject_text?: string | null;
  subject_created_at?: string | null;
  subject_media: RemoteMedia[];
  subject_external_links: ExternalLink[];
  subject_hashtags: HashtagFacet[];
  subject_labels: string[];
  subject_embedded_records: EmbeddedRecord[];
};

export type Caption = {
  lang: string;
  cid: string;
  path: string;
  mime_type?: string | null;
};

export type Media = {
  cid: string;
  path: string;
  mime_type?: string | null;
  alt_text?: string | null;
  media_type: string;
  presentation?: string;
  captions?: Caption[];
};

export type RemoteMedia = {
  url: string;
  thumb?: string | null;
  alt_text?: string | null;
  media_type: string;
  presentation?: string;
  captions?: Caption[];
};

export type ExternalLink = {
  uri: string;
  title?: string | null;
  description?: string | null;
  thumb_cid?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  reading_time?: number | null;
  source?: { title?: string | null; uri?: string | null } | null;
  labels?: Record<string, unknown>[];
  associated_refs?: Record<string, unknown>[];
  associated_profiles?: Actor[];
};

export type EmbeddedRecord = {
  uri: string;
  cid?: string | null;
  collection: string;
  record_type?: string | null;
  title?: string | null;
  description?: string | null;
};

export type HashtagFacet = {
  tag: string;
  start_byte?: number | null;
  end_byte?: number | null;
};

export type Actor = {
  did: string;
  handle?: string | null;
  display_name?: string | null;
  avatar_cid?: string | null;
  is_followed?: boolean;
};

export type TimelineOrder = 'desc' | 'day_asc' | 'asc';

export type PostQuery = {
  year?: number;
  month?: number;
  day?: number;
  q?: string;
  limit?: number;
  offset?: number;
  includeDeleted?: boolean;
  order?: TimelineOrder;
};

export type TimelineItem = { kind: 'post'; post: Post } | { kind: 'repost'; repost: Repost };
export type TimelineResponse = { items: TimelineItem[]; total: number; limit: number; offset: number };
export type FriendSummary = { actor: Actor; count: number; is_self: boolean };
export type HashtagSummary = { tag: string; count: number };
export type SidebarNavigation = { friends: FriendSummary[]; hashtags: HashtagSummary[] };
export type AnalyticsPeriod = 'all' | 'year' | 'month' | 'week';
export type AnalyticsResponse = {
  period: AnalyticsPeriod;
  start_at?: string | null;
  counts: {
    own_posts: number;
    replies: number;
    reposts: number;
    total: number;
  };
  heatmap: { weekday: number; hour: number; count: number }[];
};

export async function getAnalytics(period: AnalyticsPeriod): Promise<AnalyticsResponse> {
  const qs = new URLSearchParams({ period });
  const res = await fetch('/api/analytics?' + qs.toString());
  if (!res.ok) throw new Error('analytics request failed');
  return res.json();
}

export async function getTimeline(params: Omit<PostQuery, 'q'>): Promise<TimelineResponse> {
  const qs = new URLSearchParams();
  if (params.year) qs.set('year', String(params.year));
  if (params.month) qs.set('month', String(params.month));
  if (params.day) qs.set('day', String(params.day));
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.includeDeleted) qs.set('include_deleted', 'true');
  if (params.order) qs.set('order', params.order);
  const res = await fetch('/api/timeline?' + qs.toString());
  if (!res.ok) throw new Error('timeline request failed');
  return res.json();
}

export async function getTagTimeline(tag: string, params: Omit<PostQuery, 'q'>): Promise<TimelineResponse> {
  const qs = new URLSearchParams({ tag });
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.includeDeleted) qs.set('include_deleted', 'true');
  if (params.order) qs.set('order', params.order);
  const res = await fetch('/api/timeline/search?' + qs.toString());
  if (!res.ok) throw new Error('tag timeline request failed');
  return res.json();
}

export async function getReplyTimeline(replyTo: string, params: Omit<PostQuery, 'q'>): Promise<TimelineResponse> {
  const qs = new URLSearchParams({ reply_to: replyTo });
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.includeDeleted) qs.set('include_deleted', 'true');
  if (params.order) qs.set('order', params.order);
  const res = await fetch('/api/timeline/replies?' + qs.toString());
  if (!res.ok) throw new Error('reply timeline request failed');
  return res.json();
}

export async function getSidebarNavigation(): Promise<SidebarNavigation> {
  const res = await fetch('/api/navigation?limit=20');
  if (!res.ok) throw new Error('sidebar navigation request failed');
  return res.json();
}

export async function getCalendar(year?: number, month?: number): Promise<Calendar> {
  const params = new URLSearchParams();
  if (year) params.set('year', String(year));
  if (month) params.set('month', String(month));
  const res = await fetch('/api/calendar?' + params.toString());
  if (!res.ok) throw new Error('calendar request failed');
  return res.json();
}

export async function getPosts(params: PostQuery): Promise<{ items: Post[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.year) qs.set('year', String(params.year));
  if (params.month) qs.set('month', String(params.month));
  if (params.day) qs.set('day', String(params.day));
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.includeDeleted) qs.set('include_deleted', 'true');
  if (params.order) qs.set('order', params.order);
  const path = params.q ? '/api/search' : '/api/posts';
  if (params.q) qs.set('q', params.q);
  const res = await fetch(path + '?' + qs.toString());
  if (!res.ok) throw new Error('posts request failed');
  return res.json();
}

export async function requestSync(): Promise<{ requested: boolean; requested_at: string }> {
  const res = await fetch('/api/sync', { method: 'POST', headers: { 'X-Requested-With': 'BlueskyArchive' } });
  if (!res.ok) throw new Error('sync request failed');
  return res.json();
}

export async function getSyncStatus(): Promise<{ requested_at?: string | null; consumed_at?: string | null; latest_run?: { status: string; started_at?: string | null; finished_at?: string | null; error_message?: string | null } | null }> {
  const res = await fetch('/api/sync');
  if (!res.ok) throw new Error('sync status request failed');
  return res.json();
}
