import React, { useState } from 'react';

import type { Actor, Caption, EmbeddedRecord, ExternalLink, HashtagFacet, TimelineItem } from './api';
import type { Language } from './i18n';
import {
  actorName,
  blueskyPostUrl,
  formatDateTime,
  formatPostAge,
  safeHttpUrl,
  safeMediaUrl,
  uriTail,
} from './archive';

type TimelineCardProps = {
  item: TimelineItem;
  showRecordIds: boolean;
  linkActorNames: boolean;
  blurSensitiveMedia: boolean;
  language: Language;
  nowMs: number;
  onHashtag: (tag: string) => void;
};

function LinkedPostImage({ src, alt, postUri, language }: { src: string; alt: string; postUri: string; language: Language }) {
  const postUrl = blueskyPostUrl(postUri);
  const image = <img src={src} alt={alt} />;
  return postUrl ? (
    <a className="media-link" href={postUrl} target="_blank" rel="noreferrer" title={language === 'ja' ? 'Blueskyで元ポストを開く' : 'Open the original post on Bluesky'}>
      {image}
    </a>
  ) : image;
}

function colorIndex(value: string) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) hash = (hash * 31 + value.charCodeAt(i)) >>> 0;
  return (hash % 8) + 1;
}

function RecordChip({ uri }: { uri: string }) {
  return <span className={`record-chip tone-${colorIndex(uri)}`}>{uriTail(uri)}</span>;
}

function actorDisplayText(actor?: Actor | null) {
  if (!actor) return null;
  const identifier = actor.handle || actor.did;
  if (actor.display_name && identifier) return `${actor.display_name} (@${identifier})`;
  if (actor.display_name) return actor.display_name;
  return identifier ? `@${identifier}` : null;
}

function actorInitial(actor?: Actor | null) {
  return (actorName(actor) || '?').replace(/^@/, '').slice(0, 1).toUpperCase();
}

function ActorLabel({
  actor,
  fallback = 'unknown',
  suffix,
  linkNames,
  language,
}: {
  actor?: Actor | null;
  fallback?: string;
  suffix?: React.ReactNode;
  linkNames: boolean;
  language: Language;
}) {
  const identifier = actor?.handle || actor?.did || fallback;
  const displayName = actor?.display_name?.trim();
  const profile = actor?.handle || actor?.did;
  const profileUrl = profile ? `https://bsky.app/profile/${profile}` : undefined;
  const avatarUrl = safeMediaUrl(actor?.avatar_cid);
  const avatar = avatarUrl ? (
    <img className="actor-avatar" src={avatarUrl} alt="" loading="lazy" />
  ) : (
    <span className="actor-avatar actor-avatar-fallback">{actorInitial(actor)}</span>
  );
  const names = (
    <>
      {displayName && <span className="actor-display-name">{displayName}</span>}
      <span className="actor-name">@{identifier}</span>
      {actor?.is_followed && <span className="follow-badge" title={language === 'ja' ? 'フォロー中' : 'following'} aria-label={language === 'ja' ? 'フォロー中' : 'following'}>✓</span>}
    </>
  );
  return (
    <span className="actor-label">
      {profileUrl ? (
        <a className="actor-avatar-link" href={profileUrl} target="_blank" rel="noreferrer" title={actorDisplayText(actor) || `@${identifier}`}>
          {avatar}
        </a>
      ) : avatar}
      {profileUrl && linkNames ? (
        <a className="actor-name-row actor-name-link" href={profileUrl} target="_blank" rel="noreferrer">
          {names}
        </a>
      ) : (
        <span className="actor-name-row">{names}</span>
      )}
      {suffix}
    </span>
  );
}

function renderUrls(text: string, keyPrefix: string) {
  return text.split(/(https?:\/\/[^\s]+)/g).map((part, index) => {
    const href = safeHttpUrl(part);
    if (href && /^https?:\/\//.test(part)) {
      return <a key={`${keyPrefix}-url-${index}`} href={href} target="_blank" rel="noreferrer">{part}</a>;
    }
    return <React.Fragment key={`${keyPrefix}-text-${index}`}>{part}</React.Fragment>;
  });
}

function byteOffsetToStringIndex(text: string, byteOffset: number) {
  if (byteOffset <= 0) return 0;
  let bytes = 0;
  let stringIndex = 0;
  const encoder = new TextEncoder();
  for (const character of text) {
    if (bytes >= byteOffset) return stringIndex;
    bytes += encoder.encode(character).length;
    stringIndex += character.length;
  }
  return text.length;
}

function renderText(text: string, hashtags: HashtagFacet[] = [], onHashtag?: (tag: string) => void) {
  const spans = hashtags
    .filter((facet) => Number.isInteger(facet.start_byte) && Number.isInteger(facet.end_byte))
    .map((facet) => ({
      ...facet,
      start: byteOffsetToStringIndex(text, facet.start_byte!),
      end: byteOffsetToStringIndex(text, facet.end_byte!),
    }))
    .filter((facet) => facet.start >= 0 && facet.end > facet.start && facet.end <= text.length)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const rendered: React.ReactNode[] = [];
  let cursor = 0;
  spans.forEach((facet, index) => {
    if (facet.start < cursor) return;
    rendered.push(...renderUrls(text.slice(cursor, facet.start), `before-tag-${index}`));
    rendered.push(
      <a
        className="hashtag-link"
        href={`/?tag=${encodeURIComponent(facet.tag)}`}
        key={`tag-${facet.start}-${facet.end}`}
        onClick={(event) => {
          if (!onHashtag) return;
          event.preventDefault();
          onHashtag(facet.tag);
        }}
      >
        {text.slice(facet.start, facet.end)}
      </a>,
    );
    cursor = facet.end;
  });
  rendered.push(...renderUrls(text.slice(cursor), 'after-tags'));
  return rendered;
}

function StandaloneHashtags({
  hashtags,
  onHashtag,
}: {
  hashtags: HashtagFacet[];
  onHashtag: (tag: string) => void;
}) {
  const tags = hashtags.filter(
    (facet) => !Number.isInteger(facet.start_byte) || !Number.isInteger(facet.end_byte),
  );
  if (tags.length === 0) return null;
  return (
    <div className="post-tags">
      {tags.map((facet) => (
        <a
          href={`/?tag=${encodeURIComponent(facet.tag)}`}
          key={facet.tag.toLocaleLowerCase()}
          onClick={(event) => {
            event.preventDefault();
            onHashtag(facet.tag);
          }}
        >
          #{facet.tag}
        </a>
      ))}
    </div>
  );
}

function LinkCard({ link, language }: { link: ExternalLink; language: Language }) {
  const href = safeHttpUrl(link.uri);
  const details = [
    link.source?.title,
    link.reading_time ? (language === 'ja' ? `読了 ${link.reading_time}分` : `${link.reading_time} min read`) : null,
    link.created_at ? formatDateTime(link.created_at, language) : null,
  ].filter(Boolean).join(' · ');
  const content = (
    <>
      <strong>{link.title || link.uri}</strong>
      {link.description && <span>{link.description}</span>}
      {details && <small>{details}</small>}
      <small>{link.uri}</small>
    </>
  );
  return href ? (
    <a className="link-card" href={href} target="_blank" rel="noreferrer">{content}</a>
  ) : (
    <div className="link-card">{content}</div>
  );
}

function EmbeddedRecordCard({ record }: { record: EmbeddedRecord }) {
  const parts = record.uri.split('/');
  const did = parts[2];
  const rkey = parts[4];
  const href = record.collection === 'app.bsky.graph.list'
    ? `https://bsky.app/profile/${did}/lists/${rkey}`
    : record.collection === 'app.bsky.feed.generator'
      ? `https://bsky.app/profile/${did}/feed/${rkey}`
      : record.collection === 'app.bsky.graph.starterpack'
        ? `https://bsky.app/starter-pack/${did}/${rkey}`
        : `https://bsky.app/profile/${did}`;
  return (
    <a className="link-card embedded-record-card" href={href} target="_blank" rel="noreferrer">
      <strong>{record.title || record.collection}</strong>
      {record.description && <span>{record.description}</span>}
      <small>{record.collection}</small>
    </a>
  );
}

function VideoMedia({
  src,
  poster,
  presentation,
  captions = [],
}: {
  src: string;
  poster?: string;
  presentation?: string;
  captions?: Caption[];
}) {
  const gif = presentation === 'gif';
  return (
    <video
      controls={!gif}
      autoPlay={gif}
      loop={gif}
      muted={gif}
      playsInline
      src={src}
      poster={poster}
    >
      {captions.map((caption) => {
        const track = safeMediaUrl(caption.path);
        return track ? <track key={`${caption.lang}-${caption.cid}`} kind="captions" src={track} srcLang={caption.lang} label={caption.lang} /> : null;
      })}
    </video>
  );
}

const SENSITIVE_LABELS = new Set(['porn', 'sexual', 'nudity', 'graphic-media']);

function hasSensitiveLabel(labels: string[] | undefined) {
  return (labels || []).some((label) => SENSITIVE_LABELS.has(label));
}

function SensitiveMedia({
  blurred,
  onReveal,
  children,
  language,
}: {
  blurred: boolean;
  onReveal: () => void;
  children: React.ReactNode;
  language: Language;
}) {
  return (
    <div className={blurred ? 'sensitive-media is-blurred' : 'sensitive-media'}>
      {children}
      {blurred && <button className="sensitive-reveal" onClick={onReveal}>{language === 'ja' ? 'センシティブなメディアを表示' : 'Show sensitive media'}</button>}
    </div>
  );
}

export function TimelineCard({ item, showRecordIds, linkActorNames, blurSensitiveMedia, language, nowMs, onHashtag }: TimelineCardProps) {
  const [sensitiveRevealed, setSensitiveRevealed] = useState(false);
  if (item.kind === 'repost') {
    const repost = item.repost;
    const subjectUrl = blueskyPostUrl(repost.subject_uri);
    const subjectAuthor = actorName(repost.subject_author);
    const displayTime = repost.subject_created_at || repost.record_created_at;
    const blurMedia = blurSensitiveMedia && hasSensitiveLabel(repost.subject_labels) && !sensitiveRevealed;
    return (
      <article className={repost.deleted ? 'post repost deleted' : 'post repost'}>
        <div className="post-context">
          <span className="post-context-arrow" aria-hidden="true">{'↻\uFE0E'}</span>
          <span className="post-context-label">{language === 'ja' ? 'リポスト' : 'repost'}</span>
        </div>
        <div className="post-meta">
          <ActorLabel actor={repost.subject_author} fallback={subjectAuthor || (language === 'ja' ? '不明' : 'unknown')} linkNames={linkActorNames} language={language} />
          <time className="post-age" dateTime={displayTime || undefined} title={formatDateTime(displayTime, language)}>
            {formatPostAge(displayTime, nowMs, language)}
          </time>
        </div>
        {repost.subject_text && <p>{renderText(repost.subject_text, repost.subject_hashtags, onHashtag)}</p>}
        <StandaloneHashtags hashtags={repost.subject_hashtags} onHashtag={onHashtag} />
        {repost.subject_external_links?.length > 0 && (
          <div className="link-cards">
            {repost.subject_external_links.map((link) => <LinkCard key={link.uri} link={link} language={language} />)}
          </div>
        )}
        {repost.subject_embedded_records?.length > 0 && (
          <div className="link-cards">
            {repost.subject_embedded_records.map((record) => <EmbeddedRecordCard key={record.uri} record={record} />)}
          </div>
        )}
        {repost.subject_media?.length > 0 && (
          <SensitiveMedia blurred={blurMedia} onReveal={() => setSensitiveRevealed(true)} language={language}>
            <div className="media">
              {repost.subject_media.map((media) => {
                const mediaUrl = safeMediaUrl(media.url);
                const thumbUrl = safeMediaUrl(media.thumb);
                if (!mediaUrl) return null;
                return media.media_type === 'video'
                  ? <VideoMedia key={media.url} src={mediaUrl} poster={thumbUrl} presentation={media.presentation} captions={media.captions} />
                  : <LinkedPostImage key={media.url} src={mediaUrl} alt={media.alt_text || ''} postUri={repost.subject_uri} language={language} />;
              })}
            </div>
          </SensitiveMedia>
        )}
        {showRecordIds && (
          <div className="post-links">
            <RecordChip uri={repost.uri} />
            <RecordChip uri={repost.subject_uri} />
          </div>
        )}
        <div className="post-timestamp">
          {subjectUrl
            ? <a href={subjectUrl} target="_blank" rel="noreferrer">{formatDateTime(displayTime, language)}</a>
            : <time>{formatDateTime(displayTime, language)}</time>}
        </div>
      </article>
    );
  }

  const post = item.post;
  const postUrl = blueskyPostUrl(post.uri);
  const blurMedia = blurSensitiveMedia && hasSensitiveLabel(post.labels) && !sensitiveRevealed;
  return (
    <article className={post.deleted ? 'post deleted' : 'post'}>
      {post.reply_parent_uri && (
        <div className="post-context">
          <span className="post-context-arrow" aria-hidden="true">{'↶\uFE0E'}</span>
          <span className="post-context-label">{language === 'ja' ? '返信' : 'reply'} @{actorName(post.reply_parent_author) || uriTail(post.reply_parent_uri)}</span>
        </div>
      )}
      <div className="post-meta">
        <ActorLabel
          actor={post.author}
          linkNames={linkActorNames}
          language={language}
          suffix={post.deleted ? <span className="deleted-badge">{language === 'ja' ? '削除済' : 'deleted'}</span> : undefined}
        />
        <time className="post-age" dateTime={post.record_created_at || undefined} title={formatDateTime(post.record_created_at, language)}>
          {formatPostAge(post.record_created_at, nowMs, language)}
        </time>
      </div>
      <p>{renderText(post.text, post.hashtags, onHashtag)}</p>
      <StandaloneHashtags hashtags={post.hashtags} onHashtag={onHashtag} />
      {post.external_links?.length > 0 && (
        <div className="link-cards">
          {post.external_links.map((link) => <LinkCard key={link.uri} link={link} language={language} />)}
        </div>
      )}
      {post.embedded_records?.length > 0 && (
        <div className="link-cards">
          {post.embedded_records.map((record) => <EmbeddedRecordCard key={record.uri} record={record} />)}
        </div>
      )}
      {post.media.length > 0 && (
        <SensitiveMedia blurred={blurMedia} onReveal={() => setSensitiveRevealed(true)} language={language}>
          <div className="media">
            {post.media.map((media) => {
              const mediaUrl = safeMediaUrl(media.path);
              if (!mediaUrl) return null;
              return media.media_type === 'video'
                ? <VideoMedia key={media.cid} src={mediaUrl} presentation={media.presentation} captions={media.captions} />
                : <LinkedPostImage key={media.cid} src={mediaUrl} alt={media.alt_text || ''} postUri={post.uri} language={language} />;
            })}
          </div>
        </SensitiveMedia>
      )}
      {(post.quote_uri || showRecordIds) && (
        <div className="post-links">
          {post.quote_uri && <span>{language === 'ja' ? '引用' : 'quote'} @{actorName(post.quote_author) || uriTail(post.quote_uri)}</span>}
          {showRecordIds && <RecordChip uri={post.uri} />}
        </div>
      )}
      <div className="post-timestamp">
        {postUrl
          ? <a href={postUrl} target="_blank" rel="noreferrer">{formatDateTime(post.record_created_at, language)}</a>
          : <time>{formatDateTime(post.record_created_at, language)}</time>}
      </div>
    </article>
  );
}
