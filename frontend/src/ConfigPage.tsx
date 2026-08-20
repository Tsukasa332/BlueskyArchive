import type { AppSettings } from './settings';

type ConfigPageProps = {
  settings: AppSettings;
  onChange: (settings: AppSettings) => void;
};

export function ConfigPage({ settings, onChange }: ConfigPageProps) {
  const ja = settings.language === 'ja';
  function update<Key extends keyof AppSettings>(key: Key, value: AppSettings[Key]) {
    onChange({ ...settings, [key]: value });
  }

  return (
    <section className="config-page" aria-labelledby="config-title">
      <div className="config-heading">
        <h1 id="config-title">{ja ? '設定' : 'Settings'}</h1>
        <p>{ja ? 'このブラウザだけに保存されます。別の端末やブラウザとは共有されません。' : 'These settings are stored only in this browser and are not shared with other devices or browsers.'}</p>
      </div>

      <div className="config-options">
        <label className="config-option">
          <span>
            <strong>{ja ? '表示言語' : 'Display language'}</strong>
            <small>{ja ? '画面の表示言語を英語または日本語から選択します。' : 'Choose English or Japanese for the user interface.'}</small>
          </span>
          <select value={settings.language} onChange={(event) => update('language', event.target.value as AppSettings['language'])}>
            <option value="en">English</option>
            <option value="ja">日本語</option>
          </select>
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'ページ切り替え時に先頭へ移動' : 'Scroll to top after navigation'}</strong>
            <small>{ja ? '前の日・次の日、月、検索結果、ページ番号を切り替えた時に画面上部へ戻ります。' : 'Return to the top after changing the day, month, search result, or page.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.scrollToTopOnNavigation}
            onChange={(event) => update('scrollToTopOnNavigation', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'レコードIDを表示' : 'Show record IDs'}</strong>
            <small>{ja ? 'ポストとリポストにAT Protocolレコードの末尾IDを表示します。' : 'Show the final AT Protocol record ID on posts and reposts.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showRecordIds}
            onChange={(event) => update('showRecordIds', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? '名前とIDからプロフィールを開く' : 'Link names and IDs to profiles'}</strong>
            <small>{ja ? 'アイコンに加えて、表示名と@handleまたは@DIDもBlueskyプロフィールへのリンクにします。' : 'Link the display name and @handle or @DID to the Bluesky profile, in addition to the avatar.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.linkActorNames}
            onChange={(event) => update('linkActorNames', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? '削除済みを表示' : 'Show deleted records'}</strong>
            <small>{ja ? '削除済みとして保存されているポストとリポストも一覧へ含めます。' : 'Include posts and reposts that are stored as deleted.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showDeleted}
            onChange={(event) => update('showDeleted', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'Recentを表示' : 'Show Recent'}</strong>
            <small>{ja ? '右ペインに最近の日付一覧を表示します。' : 'Show recent archive dates in the sidebar.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showRecent}
            onChange={(event) => update('showRecent', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'Archivesを表示' : 'Show Archives'}</strong>
            <small>{ja ? '右ペインに月別アーカイブ一覧を表示します。' : 'Show the monthly archive list in the sidebar.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showArchives}
            onChange={(event) => update('showArchives', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'Friendsを表示' : 'Show Friends'}</strong>
            <small>{ja ? '右ペインに返信先一覧を表示します。' : 'Show the list of reply recipients in the sidebar.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showFriends}
            onChange={(event) => update('showFriends', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? '自分をFriendsに表示' : 'Include yourself in Friends'}</strong>
            <small>{ja ? '自分の投稿へ返信して続けたポストもFriendsへ含めます。' : 'Include follow-up posts that reply to your own posts in Friends.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showSelfInFriends}
            disabled={!settings.showFriends}
            onChange={(event) => update('showSelfInFriends', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'Hashtagsを表示' : 'Show Hashtags'}</strong>
            <small>{ja ? '右ペインにハッシュタグ一覧を表示します。' : 'Show the hashtag list in the sidebar.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.showHashtags}
            onChange={(event) => update('showHashtags', event.target.checked)}
          />
        </label>

        <label className="config-option">
          <span>
            <strong>{ja ? 'センシティブなメディアをぼかす' : 'Blur sensitive media'}</strong>
            <small>{ja ? 'センシティブ指定された投稿の画像と動画をぼかします。投稿ごとに解除できます。' : 'Blur images and videos on posts marked as sensitive. You can reveal each post individually.'}</small>
          </span>
          <input
            type="checkbox"
            checked={settings.blurSensitiveMedia}
            onChange={(event) => update('blurSensitiveMedia', event.target.checked)}
          />
        </label>
      </div>
    </section>
  );
}
